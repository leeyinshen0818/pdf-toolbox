# PDF Toolbox

PDF Toolbox is a small offline desktop app for practical PDF workflows.

Phase 1 implements Image -> PDF:

- Import JPG, JPEG, and PNG files.
- Drag files into the app or use the file picker.
- Reorder images by dragging them in the list.
- Remove individual images from their row or clear the list.
- Export the current order into one PDF using Fit, A4, or US Letter page sizing.
- Preview page layout before export.
- Apply non-destructive per-image sharpness, brightness, and contrast corrections.

Phase 2 implements PDF -> Image:

- Import one PDF using the file picker or drag and drop.
- Preview PDF pages as selectable thumbnails.
- Export selected pages as JPG or PNG.
- Choose Standard 150 DPI or High 300 DPI output.
- Use collision-safe page filenames in the selected output folder.

PDF Organizer is reserved for a future phase.

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
