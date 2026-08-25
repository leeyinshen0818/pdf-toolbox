from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


class SharpnessPreset(str, Enum):
    SOFT = "Soft"
    NORMAL = "Normal"
    SHARP = "Sharp"
    SHARPER = "Sharper"


class TonePreset(str, Enum):
    NORMAL = "Normal"
    BRIGHT_10 = "Bright +10"
    BRIGHT_20 = "Bright +20"
    BRIGHT_CONTRAST = "Bright + Contrast"
    STRONG = "Strong"


SHARPNESS_FACTORS = {
    SharpnessPreset.SOFT: 0.65,
    SharpnessPreset.NORMAL: 1.0,
    SharpnessPreset.SHARP: 1.45,
    SharpnessPreset.SHARPER: 1.85,
}

TONE_FACTORS = {
    TonePreset.NORMAL: (1.0, 1.0),
    TonePreset.BRIGHT_10: (1.08, 1.0),
    TonePreset.BRIGHT_20: (1.16, 1.0),
    TonePreset.BRIGHT_CONTRAST: (1.12, 1.14),
    TonePreset.STRONG: (1.20, 1.24),
}


@dataclass(frozen=True)
class CorrectionSettings:
    sharpness: SharpnessPreset = SharpnessPreset.NORMAL
    tone: TonePreset = TonePreset.NORMAL

    def normalized(self) -> "CorrectionSettings":
        return CorrectionSettings(
            sharpness=SharpnessPreset(self.sharpness),
            tone=TonePreset(self.tone),
        )

    def reset_all(self) -> "CorrectionSettings":
        return CorrectionSettings()

    def cache_key(self) -> tuple[str, str]:
        normalized = self.normalized()
        return (normalized.sharpness.value, normalized.tone.value)


def apply_corrections(image: Image.Image, settings: CorrectionSettings) -> Image.Image:
    corrected = ImageOps.exif_transpose(image)
    normalized = settings.normalized()

    if normalized.sharpness == SharpnessPreset.SOFT:
        corrected = corrected.filter(ImageFilter.GaussianBlur(radius=0.55))
    elif normalized.sharpness != SharpnessPreset.NORMAL:
        corrected = ImageEnhance.Sharpness(corrected).enhance(SHARPNESS_FACTORS[normalized.sharpness])

    brightness, contrast = TONE_FACTORS[normalized.tone]
    if brightness != 1.0:
        corrected = ImageEnhance.Brightness(corrected).enhance(brightness)
    if contrast != 1.0:
        corrected = ImageEnhance.Contrast(corrected).enhance(contrast)

    return corrected.copy()


def flatten_to_white(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        return background.convert("RGB")

    if image.mode != "RGB":
        return image.convert("RGB")

    return image.copy()
