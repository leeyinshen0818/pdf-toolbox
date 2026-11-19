from __future__ import annotations

import pytest

from pdf_toolbox.core.organizer_preferences import (
    ThumbnailSize,
    thumbnail_size_from_value,
    thumbnail_size_to_value,
)


@pytest.mark.parametrize("size", list(ThumbnailSize))
def test_thumbnail_size_round_trips(size: ThumbnailSize) -> None:
    assert thumbnail_size_from_value(thumbnail_size_to_value(size)) == size


@pytest.mark.parametrize("raw", [None, "", "Huge", "small", "Large ", 2, ["LARGE"]])
def test_invalid_stored_thumbnail_size_falls_back_to_medium(raw: object) -> None:
    assert thumbnail_size_from_value(raw) == ThumbnailSize.MEDIUM
