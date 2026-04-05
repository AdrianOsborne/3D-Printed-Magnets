# Round whiteboard magnet generator

This script mass-generates **STL files** for round whiteboard magnets from input images.

## What it makes

Each output model has:
- a round magnet body
- the same outer diameter every time
- the same base thickness every time
- the same raised image extrusion every time
- a **centered bottom recess** for a **6x2 mm magnet**
- STL output only

## Best input types

Use:
- SVG logos and icons
- simple logos
- black and white clipart
- silhouettes
- bold line art

Avoid:
- detailed photos
- soft gradients
- very thin lines

## Install

```bash
pip install pillow opencv-python numpy cairosvg
```

You also need **OpenSCAD** installed and available in PATH because the script exports STL files.

## Threshold tuner UI

Use the UI when some icons need different threshold settings.

Launch it with:

```bash
run_threshold_tuner.bat
```

That UI lets you:
- preview the original image
- preview the thresholded mask
- adjust threshold per image
- toggle invert per image
- save everything into `thresholds.json`

Then the main generator will automatically use `thresholds.json` if it exists.

## Important fixes in this version

- inner cutouts now work for shapes like bottle caps, dollar signs, and recycling icons
- scaling now fits the artwork inside the usable circle instead of just fitting the bounding box
- artwork is centered by its true overall shape, so corners should no longer get clipped

## Example

```bash
python magnet_generator.py --input ./images --output ./out --thresholds-file thresholds.json
```

## Default shape and size

Defaults:
- round diameter: 40 mm
- base thickness: 3.0 mm
- raised image: 0.6 mm
- image margin: 3 mm
- centered bottom recess: 6.2 mm diameter x 2.2 mm depth

## Slicer setup

Set your filament swap or color change at:

- **3.0 mm**

That is the top of the base and the start of the raised front image.

## Notes

- The recess diameter is 6.2 mm on purpose so a 6 mm magnet fits more easily.
- The recess is centered on the back and starts from the true bottom face.
- The script creates temporary SCAD files only during export, so your output folder should contain STL files only.
