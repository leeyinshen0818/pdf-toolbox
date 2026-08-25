from __future__ import annotations

from PIL import Image, ImageFilter

from pdf_toolbox.core.image_corrections import (
    CorrectionSettings,
    SharpnessPreset,
    TonePreset,
    apply_corrections,
    rotate_180,
    rotate_left,
    rotate_right,
)


def test_horizontal_flip() -> None:
    image = Image.new("RGB", (2, 1))
    image.putpixel((0, 0), (255, 0, 0))
    image.putpixel((1, 0), (0, 0, 255))

    result = apply_corrections(image, CorrectionSettings(flip_horizontal=True))

    assert result.getpixel((0, 0)) == (0, 0, 255)
    assert result.getpixel((1, 0)) == (255, 0, 0)


def test_vertical_flip() -> None:
    image = Image.new("RGB", (1, 2))
    image.putpixel((0, 0), (255, 0, 0))
    image.putpixel((0, 1), (0, 0, 255))

    result = apply_corrections(image, CorrectionSettings(flip_vertical=True))

    assert result.getpixel((0, 0)) == (0, 0, 255)
    assert result.getpixel((0, 1)) == (255, 0, 0)


def test_rotate_90() -> None:
    image = Image.new("RGB", (2, 3), (0, 0, 0))

    result = apply_corrections(image, CorrectionSettings(rotation_degrees=90))

    assert result.size == (3, 2)


def test_rotate_180() -> None:
    settings = rotate_180(CorrectionSettings(rotation_degrees=90))

    assert settings.rotation_degrees == 270


def test_reset_orientation() -> None:
    settings = CorrectionSettings(
        rotation_degrees=90,
        flip_horizontal=True,
        flip_vertical=True,
        sharpness=SharpnessPreset.SHARP,
        tone=TonePreset.BRIGHT_20,
    )

    reset = settings.reset_orientation()

    assert reset.rotation_degrees == 0
    assert not reset.flip_horizontal
    assert not reset.flip_vertical
    assert reset.sharpness == SharpnessPreset.SHARP
    assert reset.tone == TonePreset.BRIGHT_20


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
    settings = rotate_right(rotate_left(CorrectionSettings(flip_horizontal=True, tone=TonePreset.STRONG)))

    assert settings.reset_all() == CorrectionSettings()
