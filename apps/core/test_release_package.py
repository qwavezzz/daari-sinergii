import importlib.util
import io
import json
import tarfile
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase

spec = importlib.util.spec_from_file_location(
    "release_package", Path(__file__).resolve().parents[2] / "scripts" / "package-release.py"
)
release_package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_package)


class ReleasePackageTests(SimpleTestCase):
    def test_deleted_sources_are_omitted_and_new_files_require_explicit_review(self):
        with TemporaryDirectory(prefix="dari-package-test-") as folder:
            root = Path(folder).resolve()
            (root / "frontend").mkdir()
            (root / "manage.py").write_text("# tracked source\n", encoding="utf-8")
            (root / "frontend" / "added.js").write_text("// reviewed addition\n", encoding="utf-8")

            def git(*args):
                if args[0] == "rev-parse":
                    return "a" * 40
                if "--others" in args:
                    return "frontend/added.js\0"
                return "manage.py\0apps/deleted.py\0"

            with patch.object(release_package, "ROOT", root), patch.object(release_package, "git", git):
                with patch("sys.argv", ["package-release.py", "test"]):
                    with self.assertRaisesRegex(ValueError, "Review untracked"):
                        release_package.main()
                self.assertFalse((root / "var").exists())
                with patch("sys.argv", ["package-release.py", "test", "--include", "frontend/added.js"]):
                    with redirect_stdout(io.StringIO()):
                        release_package.main()
                with tarfile.open(root / "var" / "releases" / "test.tar.gz") as archive:
                    self.assertNotIn("apps/deleted.py", archive.getnames())
                    manifest = json.load(archive.extractfile("RELEASE-MANIFEST.json"))
                    self.assertEqual(set(manifest["files"]), {"manage.py", "frontend/added.js"})

    def test_private_and_outside_files_are_rejected(self):
        with TemporaryDirectory(prefix="dari-package-private-") as folder:
            root = Path(folder).resolve()
            (root / "private.key").write_text("test fixture, not a key", encoding="utf-8")
            with patch.object(release_package, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "Private or generated"):
                    release_package.payload("private.key")
                with self.assertRaisesRegex(ValueError, "Unsafe source path"):
                    release_package.payload("../outside.py")
