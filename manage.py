#!/usr/bin/env python
import os
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    venv_python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    # Use project dependencies when invoked with system Python; respect an active environment.
    if sys.prefix == sys.base_prefix and venv_python.is_file():
        try:
            result = subprocess.run([str(venv_python), str(root / "manage.py"), *sys.argv[1:]])
        except KeyboardInterrupt:
            raise SystemExit(130) from None
        raise SystemExit(result.returncode)

    # Local commands share runserver's settings and database. Deployments select
    # config.settings in their EnvironmentFile; Django also honors --settings.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_dev")
    try:
        from django.core.management import execute_from_command_line
    except ModuleNotFoundError as exc:
        if exc.name != "django":
            raise
        raise SystemExit(
            "Django is not installed. Prepare the project environment first:\n"
            "  python -m venv .venv\n"
            f'  {"& " if os.name == "nt" else ""}"{venv_python}" -m pip install -r requirements-dev.txt'
        ) from None

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
