from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from pdf_toolbox.core.image_corrections import CorrectionSettings
from pdf_toolbox.core.image_validation import ImageInfo, ImageValidationError, validate_image_file
from pdf_toolbox.core.path_keys import path_key as image_key


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

    def apply_corrections_to_all(self, corrections: CorrectionSettings) -> int:
        """Give every image the same corrections; returns how many images there are."""
        normalized = corrections.normalized()
        self._entries = [replace(entry, corrections=normalized) for entry in self._entries]
        return len(self._entries)

    def move_paths(self, paths: Iterable[str | Path], step: int) -> bool:
        """Move the given images one place up (step=-1) or down (step=1), keeping them in order.

        Returns False (and changes nothing) when an image is already at that end of the list.
        """
        if step not in (-1, 1):
            raise ValueError("step must be -1 or 1")
        moving = {image_key(path) for path in paths}
        flags = [image_key(entry.path) in moving for entry in self._entries]
        if not any(flags):
            return False
        if (step < 0 and flags[0]) or (step > 0 and flags[-1]):
            return False
        entries = list(self._entries)
        indexes = range(len(entries)) if step < 0 else range(len(entries) - 1, -1, -1)
        for index in indexes:
            if flags[index]:
                other = index + step
                entries[index], entries[other] = entries[other], entries[index]
                flags[index], flags[other] = flags[other], flags[index]
        self._entries = entries
        return True

    def clear(self) -> None:
        self._entries.clear()
        self._keys.clear()

    def reorder_by_paths(self, ordered_paths: Iterable[str | Path]) -> None:
        entries_by_key = {image_key(entry.path): entry for entry in self._entries}
        ordered_keys = [image_key(path) for path in ordered_paths]

        if set(ordered_keys) != set(entries_by_key) or len(ordered_keys) != len(entries_by_key):
            raise ValueError("New image order must contain each current image exactly once.")

        self._entries = [entries_by_key[key] for key in ordered_keys]
