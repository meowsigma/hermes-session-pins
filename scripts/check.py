#!/usr/bin/env python3
"""Run tests with the installed Hermes runtime, in an empty temporary profile."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    hermes = shutil.which("hermes")
    if not hermes:
        print("Install Hermes first, then rerun this script.", file=sys.stderr)
        return 1
    command = json.loads(subprocess.check_output(
        [hermes, "--print-runtime-command", "--module", "unittest"], text=True,
    ))
    with tempfile.TemporaryDirectory(prefix="hermes-pins-check-") as home:
        return subprocess.call(
            command + ["discover", "-s", "tests", "-t", ".", "-v"],
            cwd=Path(__file__).resolve().parents[1], env=dict(os.environ, HERMES_HOME=home),
        )


if __name__ == "__main__":
    raise SystemExit(main())
