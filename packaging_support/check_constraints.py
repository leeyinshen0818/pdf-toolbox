"""Exit non-zero unless the active environment matches constraints.txt exactly."""
from __future__ import annotations

import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


CONSTRAINTS = Path(__file__).resolve().parents[1] / "constraints.txt"


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def main() -> int:
    problems = []
    for raw in CONSTRAINTS.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        name, pinned = (part.strip() for part in line.split("=="))
        try:
            installed = version(_normalise(name))
        except PackageNotFoundError:
            problems.append(f"{name}: not installed (need {pinned})")
            continue
        if installed != pinned:
            problems.append(f"{name}: installed {installed}, constraints.txt pins {pinned}")

    if problems:
        print("Build environment does not match constraints.txt:", *problems, sep="\n  ")
        return 1
    print(f"Build environment matches constraints.txt (Python {sys.version.split()[0]}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
