from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from pdf_toolbox.core.image_corrections import CorrectionSettings
from pdf_toolbox.core.image_validation import ImageInfo, ImageValidationError, validate_image_file


@dataclass(frozen=True)
class ImageEntry:
    path: Path
    filename: str
    width: int
    height: int
    format: str
    corrections: CorrectionSettings = CorrectionSettings()

    @classmethod
    def from_info(cls, info: ImageInfo) -> "ImageEntry":
        return cls(
            path=info.path,
            filename=info.filename,
            width=info.width,
            height=info.height,
            format=info.format,
        )


@dataclass(frozen=True)
class RejectedImage:
    path: Path
    reason: str


@dataclass(frozen=True)
class AddImagesResult:
    added: tuple[ImageEntry, ...]
    rejected: tuple[RejectedImage, ...]
    duplicates: tuple[Path, ...]


def image_key(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).resolve(strict=False)))


class ImageCollection:
    def __init__(self) -> None:
        self._entries: list[ImageEntry] = []
        self._keys: set[str] = set()

    @property
    def entries(self) -> tuple[ImageEntry, ...]:
        return tuple(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    def add_paths(self, paths: Iterable[str | Path]) -> AddImagesResult:
        added: list[ImageEntry] = []
        rejected: list[RejectedImage] = []
        duplicates: list[Path] = []

        for raw_path in paths:
            path = Path(raw_path)
            key = image_key(path)
            if key in self._keys:
                duplicates.append(path)
                continue

            try:
                info = validate_image_file(path)
            except ImageValidationError as exc:
                rejected.append(RejectedImage(path=path, reason=str(exc)))
                continue

            entry = ImageEntry.from_info(info)
            self._entries.append(entry)
            self._keys.add(key)
            added.append(entry)

        return AddImagesResult(tuple(added), tuple(rejected), tuple(duplicates))

    def remove_paths(self, paths: Iterable[str | Path]) -> None:
        keys_to_remove = {image_key(path) for path in paths}
        self._entries = [entry for entry in self._entries if image_key(entry.path) not in keys_to_remove]
        self._keys = {image_key(entry.path) for entry in self._entries}

    def update_corrections(self, path: str | Path, corrections: CorrectionSettings) -> None:
        key = image_key(path)
        for index, entry in enumerate(self._entries):
            if image_key(entry.path) == key:
                self._entries[index] = replace(entry, corrections=corrections.normalized())
                return
        raise KeyError(f"Image is not in the collection: {path}")

    def clear(self) -> None:
        self._entries.clear()
        self._keys.clear()

    def reorder_by_paths(self, ordered_paths: Iterable[str | Path]) -> None:
        entries_by_key = {image_key(entry.path): entry for entry in self._entries}
        ordered_keys = [image_key(path) for path in ordered_paths]

        if set(ordered_keys) != set(entries_by_key) or len(ordered_keys) != len(entries_by_key):
            raise ValueError("New image order must contain each current image exactly once.")

        self._entries = [entries_by_key[key] for key in ordered_keys]
