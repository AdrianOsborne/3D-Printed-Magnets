# Round whiteboard magnet generator

A script that mass generates **STL files** for round whiteboard magnets from input images.

Each output model has:
- a round magnet body
- the same outer diameter every time
- the same base thickness every time
- the same raised image extrusion every time
- a **centered bottom recess** for a **6x2 mm magnet**

<img width="256" height="256" alt="image" src="https://github.com/user-attachments/assets/42ecabe3-a8f2-471c-93ed-e4e5194fdf5a" />
<img width="256" height="256" alt="image" src="https://github.com/user-attachments/assets/c5dd69f9-b0e8-49bf-92cd-729d88235aaf" />
<img width="256" height="256" alt="image" src="https://github.com/user-attachments/assets/4a04d47b-1215-4000-bcbf-07b235460323" />


## Recommendations
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

<img width="1920" height="1032" alt="image" src="https://github.com/user-attachments/assets/d9b398dd-0a4f-4caf-8915-afa39940e9bd" />

## Installation

```bash
pip install pillow opencv-python numpy cairosvg
```

You also need **OpenSCAD** installed and available in PATH because the script exports STL files.

## Threshold tuner UI

Use the UI when some icons need different threshold settings.

<img width="1920" height="1032" alt="image" src="https://github.com/user-attachments/assets/0178b181-d65c-4046-9cc3-491d2e050cf0" />

Launch it with:

```bash
run_threshold_tuner.bat
```

That UI lets you:
- preview the original image
- preview the thresholded mask
- adjust threshold per image
- toggle invert per image
- open an SVG icon database search for black and white artwork
- import an SVG from a URL directly into `images`
- save everything into `thresholds.json`

Then the main generator will automatically use `thresholds.json` if it exists.

## Example
<img width="1920" height="1032" alt="image" src="https://github.com/user-attachments/assets/bc81a8ec-a51c-4d29-9d32-f6320245b6bb" />

<img width="1920" height="1032" alt="image" src="https://github.com/user-attachments/assets/facf7618-e7d6-4065-b5a6-dcb7ce0070f5" />



## Defaults

- round diameter: 40 mm
- base thickness: 3.0 mm
- raised image: 0.6 mm
- image margin: 3 mm
- centered bottom recess: 6.2 mm diameter x 2.2 mm depth

## Slicer setup

Set your filament swap or color change at:

- **3.0 mm**

## Notes

- The recess diameter is 6.2 mm on purpose so a 6 mm magnet fits more easily.
- The recess is centered on the back and starts from the true bottom face.
- The script creates temporary SCAD files only during export, so your output folder should contain STL files only.
