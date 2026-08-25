from __future__ import annotations

from dataclasses import fields

from PIL import Image, ImageFilter

from pdf_toolbox.core.image_corrections import (
    CorrectionSettings,
    SharpnessPreset,
    TonePreset,
    apply_corrections,
)


def test_only_sharpness_and_tone_correction_state_remain() -> None:
    assert [field.name for field in fields(CorrectionSettings)] == ["sharpness", "tone"]


def test_default_correction_values_are_normal() -> None:
    settings = CorrectionSettings()

    assert settings.sharpness == SharpnessPreset.NORMAL
    assert settings.tone == TonePreset.NORMAL


def test_soften_preset() -> None:
    image = Image.new("RGB", (5, 5), (0, 0, 0))
    image.putpixel((2, 2), (255, 255, 255))

    result = apply_corrections(image, CorrectionSettings(sharpness=SharpnessPreset.SOFT))

    assert result.getpixel((2, 2))[0] < 255
    assert result.getpixel((2, 1))[0] > 0


def test_sharpen_preset() -> None:
    image = Image.new("RGB", (9, 3), (0, 0, 0))
    for x in range(4, 9):
        for y in range(3):
            image.putpixel((x, y), (255, 255, 255))
    blurred = image.filter(ImageFilter.GaussianBlur(radius=1))

    normal_left = apply_corrections(blurred, CorrectionSettings()).getpixel((3, 1))[0]
    sharp_left = apply_corrections(blurred, CorrectionSettings(sharpness=SharpnessPreset.SHARP)).getpixel((3, 1))[0]

    assert sharp_left < normal_left


def test_brightness_preset() -> None:
    image = Image.new("RGB", (1, 1), (100, 100, 100))

    result = apply_corrections(image, CorrectionSettings(tone=TonePreset.BRIGHT_20))

    assert result.getpixel((0, 0))[0] > 100


def test_contrast_preset() -> None:
    image = Image.new("RGB", (2, 1))
    image.putpixel((0, 0), (80, 80, 80))
    image.putpixel((1, 0), (180, 180, 180))

    result = apply_corrections(image, CorrectionSettings(tone=TonePreset.BRIGHT_CONTRAST))

    assert result.getpixel((1, 0))[0] - result.getpixel((0, 0))[0] > 100


def test_reset_corrections() -> None:
    settings = CorrectionSettings(sharpness=SharpnessPreset.SHARPER, tone=TonePreset.STRONG)

    assert settings.reset_all() == CorrectionSettings()
