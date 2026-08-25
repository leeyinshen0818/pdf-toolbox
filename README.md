# PDF Toolbox

PDF Toolbox is a small offline desktop app for practical PDF workflows.

Phase 1 implements Image -> PDF:

- Import JPG, JPEG, and PNG files.
- Drag files into the app or use the file picker.
- Reorder images by dragging them in the list.
- Remove selected images or clear the list.
- Export the current order into one PDF using Fit, A4, or US Letter page sizing.
- Preview page layout before export.
- Apply non-destructive per-image rotation, flip, sharpness, brightness, and contrast corrections.

Future phases are reserved for PDF -> Image and PDF Organizer.

## Run

```powershell
python run.py
```

or, after installing the project:

```powershell
python -m pip install -e .
pdf-toolbox
```

## Test

```powershell
python -m pytest
```
