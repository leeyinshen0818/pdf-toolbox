"""Reading enum choices back from saved settings."""
from __future__ import annotations

from enum import Enum
from typing import TypeVar

_E = TypeVar("_E", bound=Enum)


def enum_or_default(enum_type: type[_E], raw: object, default: _E) -> _E:
    """The member whose *name* is `raw`, or `default` when it is missing or unrecognised.

    Names are stored rather than labels so renaming a label never breaks a saved setting.
    """
    if not isinstance(raw, str):
        return default
    try:
        return enum_type[raw]
    except KeyError:
        return default
