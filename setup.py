#!/usr/bin/env python3
"""Cross-platform automated setup orchestrator for email-doctor.

Creates the Python virtual environment, installs backend dependencies,
installs frontend npm packages, and seeds .env from .env.example.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
VENV_DIR = ROOT_DIR / ".venv"


def log(msg):
    print(f"\n[SETUP] {msg}")


def check_prerequisites():
    log("Checking prerequisites...")
    if sys.version_info < (3, 10):
        sys.exit("Error: Python 3.10 or higher is required.")
    if not shutil.which("npm"):
        sys.exit("Error: Node.js and npm are required. Please install Node.js.")


def create_virtualenv():
    log(f"Configuring Python virtual environment at {VENV_DIR}...")
    if not VENV_DIR.exists():
        import venv

        venv.create(VENV_DIR, with_pip=True)

    if os.name == "nt":
        py_bin = VENV_DIR / "Scripts" / "python.exe"
        pip_bin = VENV_DIR / "Scripts" / "pip.exe"
    else:
        py_bin = VENV_DIR / "bin" / "python"
        pip_bin = VENV_DIR / "bin" / "pip"
    return py_bin, pip_bin


def install_backend(py_bin):
    log("Installing backend dependencies...")
    # `python -m pip` avoids the Windows "cannot modify running pip.exe" error.
    subprocess.check_call([str(py_bin), "-m", "pip", "install", "--upgrade", "pip"])
    req_file = BACKEND_DIR / "requirements.txt"
    if req_file.exists():
        subprocess.check_call(
            [str(py_bin), "-m", "pip", "install", "-r", str(req_file)]
        )


def install_frontend():
    log("Installing frontend dependencies...")
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    subprocess.check_call([npm_cmd, "install"], cwd=str(FRONTEND_DIR))


def setup_env():
    log("Setting up environment configuration...")
    env_example = ROOT_DIR / ".env.example"
    env_target = ROOT_DIR / ".env"
    if env_example.exists() and not env_target.exists():
        shutil.copy(env_example, env_target)
        print("Created .env from .env.example")
        return
    if env_example.exists() and env_target.exists():
        existing = env_target.read_text(encoding="utf-8")
        existing_keys = {
            line.split("=", 1)[0].strip()
            for line in existing.splitlines()
            if line.strip() and not line.lstrip().startswith("#") and "=" in line
        }
        missing = [
            line
            for line in env_example.read_text(encoding="utf-8").splitlines()
            if line.strip()
            and not line.lstrip().startswith("#")
            and "=" in line
            and line.split("=", 1)[0].strip() not in existing_keys
        ]
        if missing:
            with env_target.open("a", encoding="utf-8") as fh:
                fh.write("\n\n# Added by setup.py from the current .env.example\n")
                fh.write("\n".join(missing) + "\n")
            print(f"Added {len(missing)} new setting(s) to the existing .env")


def main():
    check_prerequisites()
    py_bin, _ = create_virtualenv()
    install_backend(py_bin)
    install_frontend()
    setup_env()
    log("Setup completed successfully! Use run.bat (Windows) or ./run.sh (Unix) to start.")


if __name__ == "__main__":
    main()
