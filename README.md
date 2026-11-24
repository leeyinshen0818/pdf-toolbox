# PDF Toolbox

PDF Toolbox is a small offline Windows desktop app for practical PDF workflows. Files are processed locally on your computer; there are no cloud features, accounts, telemetry, or external conversion services.

## Features

### Image -> PDF

- Convert JPG/JPEG, PNG, and WebP images into one PDF.
- Drag and drop or select multiple images.
- Reorder, preview, remove, and apply simple non-destructive corrections.
- Export with Fit, A4, or US Letter page sizing.

### PDF -> Image

- Convert every page from one or more PDFs into JPG or PNG images.
- Choose Standard 150 DPI or High 300 DPI output.
- Use a persistent default output folder and collision-safe filenames.

### PDF Organizer

- Reorder, rotate, duplicate, delete, and combine PDF pages.
- Export the arranged pages into a new PDF without changing the source PDFs.

### Convert to JPG

- Convert HEIC/HEIF, WebP, and PNG photos into JPG.
- Preview files, batch convert, preserve orientation, and choose JPG quality.
- Transparent areas become white; animated WebP and PNG files use their first frame.

## Supported Formats

- Image -> PDF input: JPG, JPEG, PNG, WebP
- Input PDFs: PDF
- Convert to JPG input: HEIC, HEIF, WebP, PNG
- Output images: JPG, PNG
- Output documents: PDF

## Run

```powershell
python run.py
```

or, after installing the project:

```powershell
python -m pip install -e .
pdf-toolbox
```

## Build

Install the pinned dependencies (Python 3.10, 64-bit) and the PyInstaller build extra, then run:

```powershell
python -m pip install -c constraints.txt -e .[build]
.\build.ps1
```

`build.ps1` stops if the installed packages differ from `constraints.txt`. It builds one single-file app that can be copied to your Desktop or sent to another Windows PC:

```text
release/PDF-Toolbox-2.1.0.exe
```

The app icon is generated from `icon/pdf_icon.png` with `python packaging_support/make_icon.py`.

The single EXE is self-contained for normal use. Windows may take a few extra seconds to start it because PyInstaller extracts bundled runtime files into a temporary folder behind the scenes. The packaged app is intended for modern Windows 10 and Windows 11 PCs and should not require Python, pip, a virtual environment, Ghostscript, ImageMagick, Poppler, FFmpeg, or system HEIC codecs on the target computer.

## Test

```powershell
python -m pytest
```

## Main Dependencies

- Python
- PySide6
- Pillow
- PyMuPDF
- pillow-heif
- PyInstaller for release builds
