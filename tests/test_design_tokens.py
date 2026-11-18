from __future__ import annotations

import pytest

from pdf_toolbox.ui import tokens as T


REQUIRED_PAIRS = {
    "text on page-bg": (T.TEXT, T.PAGE_BG),
    "text on card-bg": (T.TEXT, T.CARD_BG),
    "text-secondary on card-bg": (T.TEXT_SECONDARY, T.CARD_BG),
    "on-primary on primary": (T.ON_PRIMARY, T.PRIMARY),
    "on-primary on primary-hover": (T.ON_PRIMARY, T.PRIMARY_HOVER),
    "disabled-text on disabled-bg": (T.DISABLED_TEXT, T.DISABLED_BG),
    "success text on success bg": (T.SUCCESS_TEXT, T.SUCCESS_BG),
    "warning text on warning bg": (T.WARNING_TEXT, T.WARNING_BG),
    "danger text on danger bg": (T.DANGER_TEXT, T.DANGER_BG),
}


@pytest.mark.parametrize("pair", sorted(REQUIRED_PAIRS))
def test_token_text_colours_meet_wcag_aa_contrast(pair: str) -> None:
    foreground, background = REQUIRED_PAIRS[pair]

    assert T.contrast_ratio(foreground, background) >= 4.5, pair
