# Magnet Studio

Magnet Studio is a small web app for turning simple black-and-white artwork into round whiteboard magnet STL files.

## Workflow

1. Launch the app with `run_app.bat` or `run_magnets.bat`.
2. Upload local artwork or open an SVG search and import an SVG URL.
3. Pick an image, tune the threshold, and preview the mask before generating.
4. Generate the STL and download it from the app.

## Best artwork

- SVG icons
- silhouettes
- bold logos
- black and white clipart

Avoid photos, gradients, and very thin line art.

## Install

```bash
pip install -r requirements.txt
```

You also need OpenSCAD installed and available in `PATH`.

## Defaults

- diameter: 40 mm
- base thickness: 3.0 mm
- raised image: 0.6 mm
- image margin: 3.0 mm
- pocket: 6.2 mm diameter x 2.2 mm depth

## Folders

- `images`: source artwork
- `out`: generated STL files
- `thresholds.json`: saved per-image threshold and invert settings

## Notes

- The app serves locally at `http://127.0.0.1:5000`.
- The slicer color change height matches the base thickness.
