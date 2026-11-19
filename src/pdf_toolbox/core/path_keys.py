from __future__ import annotations

import os
from pathlib import Path


def path_key(path: str | Path) -> str:
    """Identity key for a file path: resolved (without requiring it to exist) and case-normalised.

    Used to detect duplicates in the image, HEIC, PDF->Image and Organizer collections.
    """
    return os.path.normcase(str(Path(path).resolve(strict=False)))
