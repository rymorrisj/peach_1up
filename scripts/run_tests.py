"""Run all test suites: backend (pytest via .venv) and frontend (vitest). A script for local testing"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
FRONTEND_DIR = ROOT / "frontend"


def run(label: str, cmd: list, cwd: Path) -> int:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd, cwd=cwd)
    return result.returncode


def main():
    results = {}

    results["backend"] = run(
        "Backend tests (pytest)",
        [str(VENV_PYTHON), "-m", "pytest", "backend/tests", "-v"],
        ROOT,
    )

    results["frontend"] = run(
        "Frontend tests (vitest)",
        ["npx.cmd", "vitest", "run"],
        FRONTEND_DIR,
    )

    print(f"\n{'='*60}")
    print("  Summary")
    print(f"{'='*60}")
    all_passed = True
    for suite, code in results.items():
        status = "PASSED" if code == 0 else "FAILED"
        print(f"  {suite:12} {status}")
        if code != 0:
            all_passed = False

    print()
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
