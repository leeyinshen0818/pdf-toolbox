# PDF Toolbox

PDF Toolbox is a small offline Windows desktop app for practical PDF workflows. Files are processed locally on your computer; there are no cloud features, accounts, telemetry, or external conversion services.

## Features

### Image -> PDF

- Convert JPG/JPEG/PNG images into one PDF.
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

### HEIC -> JPG

- Convert HEIC/HEIF photos into JPG.
- Preview files, batch convert, preserve orientation, and choose JPG quality.

## Supported Formats

- Input images: JPG, JPEG, PNG
- Input PDFs: PDF
- HEIC input: HEIC, HEIF
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

Install the project dependencies and PyInstaller build extra, then run:

```powershell
python -m pip install -e .[build]
.\build.ps1
```

The build creates a single-file app that can be copied to your Desktop or sent to another Windows PC:

```text
release/PDF-Toolbox-v1.0.0/PDF Toolbox.exe
release/PDF-Toolbox-v1.0.0-Standalone.exe
```

It also creates the conservative one-folder build:

```text
release/PDF-Toolbox-v1.0.0/PDF Toolbox/PDF Toolbox.exe
```

The build script also creates a ZIP containing the release folder:

```text
release/PDF-Toolbox-v1.0.0-Windows.zip
```

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
