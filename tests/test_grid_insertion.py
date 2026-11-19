from __future__ import annotations

import pytest

from pdf_toolbox.core.grid_insertion import insertion_index, insertion_marker

# Two rows of three 100x150 cards with 20px gaps, then a third row with one card:
#   row 0: 0 [0..100]  1 [120..220]  2 [240..340]   y 0..150
#   row 1: 3            4             5              y 170..320
#   row 2: 6                                         y 340..490
CARD_W, CARD_H, GAP = 100, 150, 20


def grid(count: int, columns: int = 3) -> list[tuple[float, float, float, float]]:
    rects = []
    for index in range(count):
        row, column = divmod(index, columns)
        x0, y0 = column * (CARD_W + GAP), row * (CARD_H + GAP)
        rects.append((x0, y0, x0 + CARD_W, y0 + CARD_H))
    return rects


RECTS = grid(7)


@pytest.mark.parametrize(
    ("point", "expected"),
    [
        ((-30, 75), 0),  # before the first card
        ((10, 75), 0),  # on card 0, left half
        ((90, 75), 1),  # on card 0, right half
        ((110, 75), 1),  # in the gap between cards 0 and 1
        ((300, 75), 3),  # on card 2, right half: end of row 0
        ((500, 75), 3),  # right of row 0
        ((10, 250), 3),  # on card 3, left half (start of row 1)
        ((150, 250), 4),  # on card 4, left half
        ((190, 250), 5),  # on card 4, right half
        ((350, 250), 6),  # right of row 1: end of row 1
        ((130, 163), 4),  # in the gap between rows, nearer row 1
        ((130, 155), 1),  # in the gap between rows, nearer row 0
        ((60, 400), 7),  # on card 6, right half: the very end
        ((10, 400), 6),  # on card 6, left half
        ((200, 400), 7),  # right of the last card in a short last row
        ((10, 900), 7),  # below everything: the very end
        ((150, -40), 1),  # above the grid: uses the first row
    ],
)
def test_insertion_index(point: tuple[float, float], expected: int) -> None:
    assert insertion_index(point[0], point[1], RECTS) == expected


def test_insertion_index_with_no_cards() -> None:
    assert insertion_index(5, 5, []) == 0


def test_single_row() -> None:
    rects = grid(3, columns=10)
    assert [insertion_index(x, 75, rects) for x in (-5, 49, 51, 169, 171, 400)] == [0, 0, 1, 1, 2, 3]


def test_marker_is_after_the_row_end_or_before_the_next_card() -> None:
    # Index 3 from the end of row 0: line to the right of card 2, on row 0.
    end_of_row = insertion_marker(3, 300, 75, RECTS, GAP)
    assert (end_of_row.x, end_of_row.top, end_of_row.bottom) == (350, 0, 150)
    # Index 3 from the start of row 1: line to the left of card 3, on row 1.
    start_of_row = insertion_marker(3, 10, 250, RECTS, GAP)
    assert (start_of_row.x, start_of_row.top, start_of_row.bottom) == (-10, 170, 320)
    # Between two cards in a row.
    between = insertion_marker(1, 110, 75, RECTS, GAP)
    assert between.x == 110
    # The very end of the grid: after the last card.
    end = insertion_marker(7, 60, 400, RECTS, GAP)
    assert (end.x, end.top) == (110, 340)
    assert insertion_marker(0, 0, 0, [], GAP) is None
