"""Clean only the reviewed VPS leftovers; preview by default, --apply to execute."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
import urllib.request

CURRENT = Path("/srv/dari/releases/https-20260921")
PREVIOUS = Path("/srv/dari/releases/seo-20260921")
OLD_RELEASES = [
    Path("/srv/dari/releases") / name for name in ("first", "email-76d6352", "readiness-20260918")
]
CACHES = [Path("/root/.cache/pip"), Path("/root/.npm/_cacache")]
UPLOADS = [
    Path("/root") / f"dari-{release}-202609{day}.tar.gz{suffix}"
    for release, day in (("readiness", "18"), ("seo", "21"), ("https", "21"))
    for suffix in ("", ".sha256")
]
LEGACY_SCRIPTS = [
    Path("/root") / name
    for name in (
        "nodesource_setup_22.sh",
        "prepare-dari.sh",
        "setup-dari-db.py",
        "setup-dari-nginx.sh",
        "setup-dari-renewal.sh",
        "start-dari.sh",
    )
]
CONFIG_ROOTS = [
    Path(name)
    for name in (
        "/etc/systemd/system",
        "/etc/nginx",
        "/etc/dari",
        "/etc/cron.d",
        "/etc/crontab",
        "/var/spool/cron/crontabs",
        "/etc/rc.local",
        "/etc/letsencrypt/renewal",
        "/etc/letsencrypt/renewal-hooks",
    )
    if Path(name).exists()
]


def require_snapshot():
    if Path("/srv/dari/current").resolve(strict=True) != CURRENT:
        raise RuntimeError("Current release changed; stop and review the cleanup plan.")
    if Path("/srv/dari/previous").resolve(strict=True) != PREVIOUS:
        raise RuntimeError("Previous release changed; stop and review the cleanup plan.")


def validate_path(path):
    # Resolve every exact allowlisted target, including its parents, before deletion.
    if path.is_symlink() or path.resolve(strict=True) != path:
        raise RuntimeError(f"Symlink or unexpected physical path: {path}")
    if not (path.is_file() or path.is_dir()):
        raise RuntimeError(f"Unexpected file type: {path}")
    for keep in (CURRENT, PREVIOUS, Path("/srv/dari/shared"), Path("/srv/dari/backups")):
        if path == keep or path.is_relative_to(keep) or keep.is_relative_to(path):
            raise RuntimeError(f"Protected path: {path}")


def mount_guard(paths):
    import re

    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        name = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), line.split()[4])
        mount = Path(name)
        if any(mount == path or mount.is_relative_to(path) for path in paths):
            raise RuntimeError(f"Mount inside a cleanup target: {mount}")


def release_data_guard(path):
    for name in (
        ".env",
        "db.sqlite3",
        "db.sqlite",
        "database.sqlite3",
        "var",
        "media",
        "private-media",
        "backups",
    ):
        item = path / name
        if item.exists() and not item.is_symlink():
            raise RuntimeError(f"Possible local data in old release; inspect before deleting: {item}")


def references(path, *, script=False):
    needle = path.name if script else str(path)
    result = subprocess.run(
        ["grep", "-rIlF", "--", needle, *map(str, CONFIG_ROOTS)],
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError("Configuration reference scan was incomplete; nothing deleted.")
    return result.stdout.splitlines()


def running_uses(paths):
    used = set()
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            command = (proc / "cmdline").read_bytes()
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        links = []
        for name in ("cwd", "exe"):
            try:
                links.append(os.readlink(proc / name))
            except OSError:
                pass
        for path in paths:
            token = path.name if path in LEGACY_SCRIPTS else str(path)
            if token.encode() in command or any(
                value == str(path) or value.startswith(str(path) + "/") for value in links
            ):
                used.add(path)
    return used


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def archive_scripts(paths, destination):
    expected = {path.name: digest(path) for path in paths}
    with tarfile.open(destination, "x:gz") as archive:
        for path in paths:
            archive.add(path, arcname=path.name, recursive=False)
    with tarfile.open(destination, "r:gz") as archive:
        if archive.getnames() != list(expected):
            raise RuntimeError("Legacy archive member mismatch; original scripts retained.")
        for member in archive:
            if not member.isfile():
                raise RuntimeError("Legacy archive contains a non-file; originals retained.")
            with archive.extractfile(member) as source:
                if hashlib.file_digest(source, "sha256").hexdigest() != expected[member.name]:
                    raise RuntimeError("Legacy archive checksum mismatch; originals retained.")
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if os.name != "posix" or os.geteuid() != 0:
        raise RuntimeError("Run this dated maintenance script with sudo on the VPS.")
    if not shutil.rmtree.avoids_symlink_attacks:
        raise RuntimeError("This Python lacks the required protected directory removal implementation.")
    os.umask(0o077)
    require_snapshot()
    targets = [path for path in OLD_RELEASES + CACHES + UPLOADS if path.exists() or path.is_symlink()]
    scripts = [path for path in LEGACY_SCRIPTS if path.exists() or path.is_symlink()]
    for path in targets + scripts:
        validate_path(path)
    mount_guard(targets + scripts)
    used = running_uses(targets + scripts)
    if used.intersection(targets):
        raise RuntimeError(
            "Running process uses cleanup target: " + ", ".join(map(str, used.intersection(targets)))
        )
    for path in OLD_RELEASES:
        if path in targets:
            release_data_guard(path)
            if references(path):
                raise RuntimeError(f"Configuration refers to old release: {path}; nothing deleted.")
    archivable = []
    for path in scripts:
        if path in used or references(path, script=True):
            print(f"KEEP referenced/running script: {path}", flush=True)
        else:
            archivable.append(path)
    for path in targets:
        print(f"REMOVE: {path}", flush=True)
    for path in archivable:
        print(f"ARCHIVE then remove original: {path}", flush=True)
    print("CLEAN: downloaded APT package cache (no installed packages removed)", flush=True)
    if not args.apply:
        print("PREVIEW_ONLY: no changes; use --apply for this reviewed plan.")
        return

    free_before = shutil.disk_usage("/").free
    if archivable:
        directory = Path("/root/dari-maintenance-20260921")
        directory.mkdir(mode=0o700, exist_ok=True)
        validate_path(directory)
        directory.chmod(0o700)
        destination = directory / f"legacy-setup-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.tar.gz"
        checksums = archive_scripts(archivable, destination)
        print(f"VERIFIED PRIVATE ARCHIVE: {destination}", flush=True)
        for path in archivable:
            require_snapshot()
            validate_path(path)
            if digest(path) != checksums[path.name]:
                raise RuntimeError(f"Script changed since archiving; retained: {path}")
            path.unlink()
    for path in targets:
        require_snapshot()
        validate_path(path)
        mount_guard([path])
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        print(f"REMOVED: {path}", flush=True)
    subprocess.run(["apt-get", "clean"], check=True)
    free_after = shutil.disk_usage("/").free
    print(f"FILES_CLEANED: approximately {(free_after - free_before) / 1048576:.0f} MiB freed", flush=True)
    for host in ("dari-sinergii.ru", "shop.dari-sinergii.ru"):
        with urllib.request.urlopen(f"https://{host}/health/", timeout=15) as response:
            if response.status != 200 or json.load(response).get("status") != "ok":
                raise RuntimeError(f"Files cleaned; health check failed for {host}.")
            print(f"HEALTH_OK: {host}", flush=True)
    print("CLEANUP_OK", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"CLEANUP_STOPPED: {error}") from None
