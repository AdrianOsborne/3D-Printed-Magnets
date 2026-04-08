from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import cairosvg
import cv2
import numpy as np
from PIL import Image, ImageOps

Point = Tuple[float, float]
Ring = List[Point]
CompoundPolygon = Dict[str, object]


@dataclass
class Settings:
    magnet_diameter_outer: float = 40.0
    base_thickness: float = 3.0
    image_extrusion: float = 0.6
    image_margin: float = 3.0

    pocket_diameter: float = 6.2
    pocket_depth: float = 2.2

    threshold: int = 160
    invert: bool = False
    blur: int = 3
    simplify_epsilon: float = 1.25
    min_contour_area: float = 60.0
    target_resolution: int = 1200

    @property
    def radius(self) -> float:
        return self.magnet_diameter_outer / 2.0

    @property
    def art_radius(self) -> float:
        return self.radius - self.image_margin


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate round whiteboard magnet STL files from images."
    )
    parser.add_argument("--input", required=True, help="Input folder of images")
    parser.add_argument("--output", required=True, help="Output folder for STL files")
    parser.add_argument("--diameter", type=float, default=40.0, help="Overall magnet diameter in mm")
    parser.add_argument("--base-thickness", type=float, default=3.0, help="Base thickness in mm")
    parser.add_argument("--image-extrusion", type=float, default=0.6, help="Raised image height in mm")
    parser.add_argument("--image-margin", type=float, default=3.0, help="Margin from outer edge in mm")
    parser.add_argument("--pocket-diameter", type=float, default=6.2, help="Pocket diameter for 6 mm magnet fit")
    parser.add_argument("--pocket-depth", type=float, default=2.2, help="Pocket depth for 2 mm magnet fit")
    parser.add_argument("--threshold", type=int, default=160)
    parser.add_argument("--invert", action="store_true", help="Invert image before contour extraction")
    parser.add_argument("--target-resolution", type=int, default=1200)
    parser.add_argument("--simplify-epsilon", type=float, default=1.25)
    parser.add_argument("--min-contour-area", type=float, default=60.0)
    parser.add_argument("--thresholds-file", default="", help="Optional JSON file with per-image threshold settings")
    parser.add_argument(
        "--extensions",
        default=".png,.jpg,.jpeg,.bmp,.webp,.svg",
        help="Comma-separated allowed input extensions",
    )
    return parser.parse_args()


def ensure_odd(value: int) -> int:
    return value if value % 2 == 1 else value + 1


def _load_image_any_format(image_path: Path) -> Image.Image:
    if image_path.suffix.lower() == ".svg":
        png_bytes = cairosvg.svg2png(url=str(image_path))
        return Image.open(BytesIO(png_bytes)).convert("RGBA")
    return Image.open(image_path).convert("RGBA")


def load_threshold_overrides(path_text: str) -> Dict[str, Dict[str, object]]:
    if not path_text:
        return {}
    path = Path(path_text)
    if not path.exists():
        print(f"Threshold override file not found, ignoring: {path}")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Could not read thresholds file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("Thresholds file must contain a JSON object.")
    return data


def get_settings_for_image(
    image_path: Path,
    settings: Settings,
    overrides: Dict[str, Dict[str, object]],
) -> Settings:
    key = image_path.name
    entry = overrides.get(key) or overrides.get(image_path.stem)
    if not isinstance(entry, dict):
        return settings

    new_settings = settings
    if "threshold" in entry:
        try:
            new_settings = replace(new_settings, threshold=int(entry["threshold"]))
        except Exception:
            pass
    if "invert" in entry:
        try:
            new_settings = replace(new_settings, invert=bool(entry["invert"]))
        except Exception:
            pass
    return new_settings


def load_and_prepare_mask(image_path: Path, settings: Settings) -> np.ndarray:
    with _load_image_any_format(image_path) as img:
        rgba = img.copy()

        white_bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        merged = Image.alpha_composite(white_bg, rgba).convert("L")

        res = settings.target_resolution
        merged.thumbnail((res, res), Image.Resampling.LANCZOS)

        canvas = Image.new("L", (res, res), 255)
        x = (res - merged.width) // 2
        y = (res - merged.height) // 2
        canvas.paste(merged, (x, y))

        if settings.invert:
            canvas = ImageOps.invert(canvas)

        arr = np.array(canvas)

    blur_size = ensure_odd(max(1, settings.blur))
    if blur_size > 1:
        arr = cv2.GaussianBlur(arr, (blur_size, blur_size), 0)

    _, mask = cv2.threshold(arr, settings.threshold, 255, cv2.THRESH_BINARY_INV)

    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    return mask


def ring_area(points: Sequence[Point]) -> float:
    area = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        area += (x1 * y2) - (x2 * y1)
    return area / 2.0


def simplify_contour(contour: np.ndarray, epsilon: float) -> Ring:
    approx = cv2.approxPolyDP(contour, epsilon, True)
    pts = [(float(pt[0][0]), float(pt[0][1])) for pt in approx]
    return pts


def extract_compound_polygons(mask: np.ndarray, settings: Settings) -> List[CompoundPolygon]:
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None or len(contours) == 0:
        raise ValueError(
            "No usable contours found. Try a simpler image, use --invert, or adjust --threshold."
        )

    hierarchy = hierarchy[0]
    compounds: List[CompoundPolygon] = []

    for idx, contour in enumerate(contours):
        parent = hierarchy[idx][3]
        if parent != -1:
            continue

        area = cv2.contourArea(contour)
        if area < settings.min_contour_area:
            continue

        outer = simplify_contour(contour, settings.simplify_epsilon)
        if len(outer) < 3:
            continue

        if ring_area(outer) < 0:
            outer.reverse()

        holes: List[Ring] = []
        child = hierarchy[idx][2]
        while child != -1:
            child_contour = contours[child]
            child_area = cv2.contourArea(child_contour)
            if child_area >= settings.min_contour_area:
                hole = simplify_contour(child_contour, settings.simplify_epsilon)
                if len(hole) >= 3:
                    if ring_area(hole) > 0:
                        hole.reverse()
                    holes.append(hole)
            child = hierarchy[child][0]

        compounds.append({"outer": outer, "holes": holes})

    if not compounds:
        raise ValueError(
            "No usable contours found. Try a simpler image, use --invert, or adjust --threshold."
        )
    return compounds


def all_points_from_compounds(compounds: Sequence[CompoundPolygon]) -> List[Point]:
    pts: List[Point] = []
    for comp in compounds:
        pts.extend(comp["outer"])
        for hole in comp["holes"]:
            pts.extend(hole)
    return pts


def transform_compounds_to_centered_circle(
    compounds: Sequence[CompoundPolygon], settings: Settings
) -> List[CompoundPolygon]:
    points = all_points_from_compounds(compounds)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    cx_src = (min_x + max_x) / 2.0
    cy_src = (min_y + max_y) / 2.0

    max_radius_src = 0.0
    for x, y in points:
        dx = x - cx_src
        dy = y - cy_src
        max_radius_src = max(max_radius_src, math.hypot(dx, dy))

    if max_radius_src <= 0:
        raise ValueError("Image contours produced invalid bounds.")

    scale = settings.art_radius / max_radius_src

    def transform_ring(ring: Ring) -> Ring:
        out: Ring = []
        for x, y in ring:
            tx = (x - cx_src) * scale
            ty = (cy_src - y) * scale
            out.append((round(tx, 4), round(ty, 4)))
        return out

    out_compounds: List[CompoundPolygon] = []
    for comp in compounds:
        out_compounds.append(
            {
                "outer": transform_ring(comp["outer"]),
                "holes": [transform_ring(h) for h in comp["holes"]],
            }
        )
    return out_compounds


def format_points(points: Sequence[Point]) -> str:
    return ", ".join(f"[{x:.4f}, {y:.4f}]" for x, y in points)


def scad_compound_module(name: str, compound: CompoundPolygon) -> str:
    points: List[Point] = []
    paths: List[List[int]] = []

    def add_ring(ring: Ring):
        start = len(points)
        points.extend(ring)
        paths.append(list(range(start, start + len(ring))))

    add_ring(compound["outer"])
    for hole in compound["holes"]:
        add_ring(hole)

    points_text = ", ".join(f"[{x:.4f}, {y:.4f}]" for x, y in points)
    paths_text = ", ".join("[" + ", ".join(str(i) for i in path) + "]" for path in paths)

    return f"""module {name}() {{
    polygon(points=[{points_text}], paths=[{paths_text}], convexity=10);
}}
"""


def build_scad(compounds: Sequence[CompoundPolygon], settings: Settings, model_name: str) -> str:
    modules: List[str] = []
    union_calls: List[str] = []

    for idx, comp in enumerate(compounds):
        mod_name = f"shape_{idx}"
        modules.append(scad_compound_module(mod_name, comp))
        union_calls.append(
            f"            linear_extrude(height={settings.image_extrusion:.4f}) {mod_name}();"
        )

    image_union = "\n".join(union_calls)

    scad = f"""{''.join(modules)}

module base_disc() {{
    translate([0, 0, 0]) cylinder(h={settings.base_thickness:.4f}, d={settings.magnet_diameter_outer:.4f}, $fn=180);
}}

module image_layer() {{
    translate([0, 0, {settings.base_thickness:.4f}])
    intersection() {{
        union() {{
{image_union}
        }}
        cylinder(h={settings.image_extrusion:.4f}, r={settings.art_radius:.4f}, $fn=180);
    }}
}}

module magnet_recess() {{
    translate([0, 0, -0.01])
        cylinder(h={settings.pocket_depth + 0.02:.4f}, d={settings.pocket_diameter:.4f}, $fn=120);
}}

translate([{settings.radius:.4f}, {settings.radius:.4f}, 0])
difference() {{
    union() {{
        base_disc();
        image_layer();
    }}
    magnet_recess();
}}
"""
    return scad


def export_stl(scad_path: Path, stl_path: Path) -> None:
    openscad = shutil.which("openscad")
    if not openscad:
        raise RuntimeError(
            "OpenSCAD was not found in PATH. Install OpenSCAD, then rerun."
        )

    cmd = [openscad, "-o", str(stl_path), str(scad_path)]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"OpenSCAD failed for {scad_path.name}:\n{completed.stderr.strip()}")


def iter_input_files(input_dir: Path, extensions: Iterable[str]) -> List[Path]:
    allowed = {ext.lower().strip() for ext in extensions if ext.strip()}
    return [
        p for p in sorted(input_dir.iterdir())
        if p.is_file() and p.suffix.lower() in allowed
    ]


def process_image(image_path: Path, out_dir: Path, settings: Settings) -> Path:
    mask = load_and_prepare_mask(image_path, settings)
    compounds = extract_compound_polygons(mask, settings)
    transformed = transform_compounds_to_centered_circle(compounds, settings)

    base_name = image_path.stem
    stl_path = out_dir / f"{base_name}.stl"

    with tempfile.TemporaryDirectory(prefix="magnet_scad_") as tmpdir:
        scad_path = Path(tmpdir) / f"{base_name}.scad"
        scad_text = build_scad(transformed, settings, base_name)
        scad_path.write_text(scad_text, encoding="utf-8")
        export_stl(scad_path, stl_path)

    return stl_path


def main() -> int:
    args = parse_args()

    settings = Settings(
        magnet_diameter_outer=args.diameter,
        base_thickness=args.base_thickness,
        image_extrusion=args.image_extrusion,
        image_margin=args.image_margin,
        pocket_diameter=args.pocket_diameter,
        pocket_depth=args.pocket_depth,
        threshold=args.threshold,
        invert=args.invert,
        target_resolution=args.target_resolution,
        simplify_epsilon=args.simplify_epsilon,
        min_contour_area=args.min_contour_area,
    )
    overrides = load_threshold_overrides(args.thresholds_file)

    input_dir = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"Input folder does not exist: {input_dir}")

    files = iter_input_files(input_dir, args.extensions.split(","))
    if not files:
        raise SystemExit("No matching input images found.")

    print(f"Found {len(files)} image(s).")
    print(f"Output folder: {out_dir}")
    print(
        f"Round magnet diameter: {settings.magnet_diameter_outer} mm | "
        f"base {settings.base_thickness} mm | image extrusion {settings.image_extrusion} mm"
    )
    print(
        f"Centered bottom recess: {settings.pocket_diameter} mm diameter x {settings.pocket_depth} mm depth"
    )
    if overrides:
        print(f"Using per-image threshold overrides from: {args.thresholds_file}")
    print()

    failures = 0
    for image_path in files:
        try:
            image_settings = get_settings_for_image(image_path, settings, overrides)
            stl_path = process_image(image_path=image_path, out_dir=out_dir, settings=image_settings)
            print(
                f"[OK] {image_path.name} -> {stl_path.name} | "
                f"threshold={image_settings.threshold} invert={image_settings.invert}"
            )
        except Exception as exc:
            failures += 1
            print(f"[FAIL] {image_path.name}: {exc}")

    print()
    print(f"Done. Success: {len(files) - failures}, Failed: {failures}")
    print(
        f"Set your slicer filament swap at {settings.base_thickness:.2f} mm "
        f"to change color for the raised image."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
