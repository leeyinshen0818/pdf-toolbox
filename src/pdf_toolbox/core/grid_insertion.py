"""Where a dragged item lands in a wrapping, left-to-right grid of cards.

Pure geometry, shared by the drop indicator and the drop itself so the line the user sees is
exactly where the pages go. Rects are (x0, y0, x1, y1) in one coordinate space, in display order.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

Rect = tuple[float, float, float, float]


@dataclass(frozen=True)
class InsertionMarker:
    """A vertical line at `x` from `top` to `bottom`."""

    x: float
    top: float
    bottom: float


def _rows(rects: Sequence[Rect]) -> list[list[int]]:
    """Indexes grouped into visual rows (a new row starts when a card begins below the previous one)."""
    rows: list[list[int]] = []
    for index, rect in enumerate(rects):
        if rows and rect[1] < rects[rows[-1][0]][3]:
            rows[-1].append(index)
        else:
            rows.append([index])
    return rows


def _row_for_y(rows: list[list[int]], rects: Sequence[Rect], y: float) -> list[int]:
    """The row whose vertical span contains y, else the nearest one (gaps, above, below)."""

    def distance(row: list[int]) -> float:
        top, bottom = rects[row[0]][1], rects[row[0]][3]
        if y < top:
            return top - y
        if y > bottom:
            return y - bottom
        return 0.0

    return min(rows, key=distance)


def insertion_index(x: float, y: float, rects: Sequence[Rect]) -> int:
    """Index the dragged cards are inserted before (len(rects) means after the last card).

    The cursor picks its row by height (nearest row when between rows or outside the grid; below
    the last row means the very end). Within the row, the left half of a card inserts before it
    and the right half after it.
    """
    if not rects:
        return 0
    rows = _rows(rects)
    if y > rects[rows[-1][0]][3]:
        return len(rects)
    row = _row_for_y(rows, rects, y)
    for index in row:
        x0, _y0, x1, _y1 = rects[index]
        if x < (x0 + x1) / 2:
            return index
    return row[-1] + 1


def insertion_marker(index: int, x: float, y: float, rects: Sequence[Rect], gap: float) -> InsertionMarker | None:
    """Where to draw the line for `index`: in the gap before card `index`, or after the last card
    of the cursor's row when the insertion point is the end of that row."""
    if not rects:
        return None
    rows = _rows(rects)
    row_of = {card: row_number for row_number, row in enumerate(rows) for card in row}
    previous = index - 1
    ends_row = previous >= 0 and (index == len(rects) or row_of[index] != row_of[previous])
    cursor_row = row_of[_row_for_y(rows, rects, y)[0]]
    if ends_row and (index == len(rects) or row_of[previous] == cursor_row):
        x0, y0, x1, y1 = rects[previous]
        return InsertionMarker(x1 + gap / 2, y0, y1)
    x0, y0, x1, y1 = rects[index]
    return InsertionMarker(x0 - gap / 2, y0, y1)
