from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from pdf_toolbox.app import main


if __name__ == "__main__":
    raise SystemExit(main())
