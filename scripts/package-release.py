"""Package a reviewed working-tree snapshot, including explicit untracked additions."""

import argparse
import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIRS = {
    "apps",
    "assets",
    "config",
    "deploy",
    "docs",
    "frontend",
    "public",
    "scripts",
    "templates",
    "tests",
}
ROOT_FILES = {
    ".env.example",
    ".gitignore",
    ".prettierrc.json",
    "README.md",
    "manage.py",
    "package.json",
    "package-lock.json",
    "playwright.config.js",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "vite.config.js",
}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8")


def eligible(name):
    path = Path(name)
    return name in ROOT_FILES or (
        path.parts[0] in SOURCE_DIRS and not any(part.startswith(".") for part in path.parts)
    )


def payload(name):
    path = ROOT / name
    if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
        raise ValueError(f"Unsafe source path: {name}")
    if not path.is_file():
        raise ValueError(f"Missing source file: {name}")
    if (
        (path.name.startswith(".env") and name != ".env.example")
        or path.name.endswith(".private.md")
        or path.suffix in {".pem", ".key", ".dump", ".sqlite3", ".pyc", ".log"}
        or path.name in {"pgpass", "pg_service.conf"}
    ):
        raise ValueError(f"Private or generated source path: {name}")
    data = path.read_bytes()
    # A Windows checkout must still produce executable Linux shell scripts.
    return data.replace(b"\r\n", b"\n") if path.suffix == ".sh" else data


def add_file(archive, name, data):
    member = tarfile.TarInfo(name)
    member.size = len(data)
    member.mode = 0o755 if name.endswith(".sh") else 0o644
    archive.addfile(member, io.BytesIO(data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="Archive name without .tar.gz")
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        help="Explicitly reviewed untracked file; repeat for each addition.",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", args.name):
        parser.error("Use lowercase letters, numbers and hyphens for the archive name.")

    tracked = set(filter(None, git("ls-files", "-z").split("\0")))
    additions = set(filter(None, git("ls-files", "--others", "--exclude-standard", "-z").split("\0")))
    approved = set(args.include)
    if approved - additions or any(not eligible(name) for name in approved):
        raise ValueError("Each --include path must be an eligible untracked application file.")
    unexpected = {name for name in additions if eligible(name)} - approved
    if unexpected:
        raise ValueError(f"Review untracked application files before packaging: {sorted(unexpected)}")
    names = sorted({name for name in tracked if eligible(name) and (ROOT / name).is_file()} | approved)
    # Validate all inputs before creating the archive.
    contents = {name: payload(name) for name in names}
    manifest = {
        "base_commit": git("rev-parse", "HEAD").strip(),
        "source": "local working-tree snapshot; includes uncommitted changes",
        "shell_line_endings": "LF",
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()},
    }
    manifest_data = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    contents["RELEASE-MANIFEST.json"] = manifest_data
    contents["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in contents.items()
    ).encode("utf-8")

    destination = ROOT / "var" / "releases"
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / f"{args.name}.tar.gz"
    checksum_path = destination / f"{target.name}.sha256"
    if target.exists() or checksum_path.exists():
        raise FileExistsError("Archive or checksum already exists; choose a new release name.")
    with target.open("xb") as output, tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, data in contents.items():
            add_file(archive, name, data)

    # Reopen the actual deliverable and verify every byte against the inputs.
    with tarfile.open(target, "r:gz") as archive:
        assert archive.getnames() == list(contents)
        for member in archive:
            assert member.isfile()
            with archive.extractfile(member) as source:
                assert source.read() == contents[member.name], member.name
    checksum = hashlib.sha256(target.read_bytes()).hexdigest()
    with checksum_path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(f"{checksum}  {target.name}\n")
    print(f"Archive: {target.relative_to(ROOT)}")
    print(f"Files: {len(contents)}; size: {target.stat().st_size / 1048576:.2f} MiB")
    print(f"SHA256: {checksum}")
    print("Archive contents verified. No upload or deployment performed.")


if __name__ == "__main__":
    main()
