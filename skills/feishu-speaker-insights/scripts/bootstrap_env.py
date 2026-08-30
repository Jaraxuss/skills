#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
from pathlib import Path


ENV_NAME = "voiceprint-poc"


def target_lock(environment_dir: Path) -> Path:
    system = platform.system()
    machine = platform.machine().lower()
    if system == "Darwin" and machine in {"arm64", "aarch64"}:
        return environment_dir / "requirements-macos-arm64.lock.txt"
    if system == "Linux" and machine in {"x86_64", "amd64"}:
        return environment_dir / "requirements-ubuntu-x86_64-cpu.lock.txt"
    raise RuntimeError(f"Unsupported v1 platform: {system} {machine}")


def env_exists(conda: str) -> bool:
    payload = json.loads(
        subprocess.run(
            [conda, "env", "list", "--json"], check=True, capture_output=True, text=True
        ).stdout
    )
    return any(Path(path).name == ENV_NAME for path in payload.get("envs", []))


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the pinned CPU Conda environment")
    parser.add_argument(
        "--apply", action="store_true", help="Apply changes; otherwise only print commands"
    )
    parser.add_argument(
        "--skip-frontend", action="store_true", help="Skip the optional static review-console build"
    )
    args = parser.parse_args()
    conda = shutil.which("conda")
    if not conda:
        raise SystemExit("Conda is not installed or not on PATH")
    environment_dir = Path(__file__).resolve().parent.parent / "environment"
    environment_file = environment_dir / "environment.yml"
    lock_file = target_lock(environment_dir)
    exists = env_exists(conda)
    conda_command = (
        [conda, "env", "update", "-n", ENV_NAME, "-f", str(environment_file), "--prune"]
        if exists
        else [conda, "env", "create", "-f", str(environment_file)]
    )
    common_command = [
        conda,
        "run",
        "-n",
        ENV_NAME,
        "python",
        "-m",
        "pip",
        "install",
        "-r",
        str(environment_dir / "requirements-common.lock.txt"),
    ]
    platform_command = [
        conda,
        "run",
        "-n",
        ENV_NAME,
        "python",
        "-m",
        "pip",
        "install",
        "--no-deps",
        "-r",
        str(lock_file),
    ]
    frontend_dir = Path(__file__).resolve().parent.parent / "review_app"
    npm = shutil.which("npm")
    frontend_commands = (
        [[npm, "ci"], [npm, "run", "build"]]
        if npm and frontend_dir.is_dir() and not args.skip_frontend
        else []
    )
    print(
        json.dumps(
            {
                "conda": conda_command,
                "common": common_command,
                "platform": platform_command,
                "frontend": frontend_commands,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.apply:
        subprocess.run(conda_command, check=True)
        subprocess.run(common_command, check=True)
        subprocess.run(platform_command, check=True)
        for command in frontend_commands:
            subprocess.run(command, cwd=frontend_dir, check=True)


if __name__ == "__main__":
    main()
