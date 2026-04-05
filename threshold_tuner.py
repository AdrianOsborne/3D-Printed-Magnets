#!/usr/bin/env python3
"""
Simple threshold tuning UI for the round whiteboard magnet generator.

What it does:
- loads images from a folder
- previews original and thresholded versions
- lets you set threshold and invert per image
- saves settings to thresholds.json

The generator can then use:
python magnet_generator.py --input ./images --output ./out --thresholds-file thresholds.json
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cairosvg
import cv2
import numpy as np
from PIL import Image, ImageOps, ImageTk

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".svg"}


def load_image_any_format(image_path: Path) -> Image.Image:
    if image_path.suffix.lower() == ".svg":
        png_bytes = cairosvg.svg2png(url=str(image_path))
        return Image.open(BytesIO(png_bytes)).convert("RGBA")
    return Image.open(image_path).convert("RGBA")


def make_preview(image_path: Path, threshold: int, invert: bool, preview_size: int = 420):
    with load_image_any_format(image_path) as img:
        rgba = img.copy()
        white_bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        merged = Image.alpha_composite(white_bg, rgba).convert("L")

        canvas = Image.new("L", (1000, 1000), 255)
        merged.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
        x = (1000 - merged.width) // 2
        y = (1000 - merged.height) // 2
        canvas.paste(merged, (x, y))

        if invert:
            canvas = ImageOps.invert(canvas)

        arr = np.array(canvas)
        arr = cv2.GaussianBlur(arr, (3, 3), 0)
        _, mask = cv2.threshold(arr, int(threshold), 255, cv2.THRESH_BINARY_INV)

        original = canvas.convert("RGB")
        mask_img = Image.fromarray(mask).convert("RGB")

        original.thumbnail((preview_size, preview_size), Image.Resampling.NEAREST)
        mask_img.thumbnail((preview_size, preview_size), Image.Resampling.NEAREST)

        return ImageTk.PhotoImage(original), ImageTk.PhotoImage(mask_img)


class ThresholdTunerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Magnet Threshold Tuner")
        self.root.geometry("1080x720")

        self.image_dir = Path("images")
        self.output_json = Path("thresholds.json")
        self.files = []
        self.index = 0
        self.settings = {}

        self.current_original = None
        self.current_mask = None

        self.build_ui()
        self.load_existing_settings()
        self.load_directory(self.image_dir)

    def build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")

        ttk.Button(top, text="Choose image folder", command=self.choose_folder).pack(side="left")
        ttk.Button(top, text="Save thresholds.json", command=self.save_settings).pack(side="left", padx=8)
        ttk.Button(top, text="Previous", command=self.prev_image).pack(side="left", padx=(20, 4))
        ttk.Button(top, text="Next", command=self.next_image).pack(side="left")

        self.file_label = ttk.Label(top, text="No folder loaded")
        self.file_label.pack(side="left", padx=20)

        controls = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        controls.pack(fill="x")

        self.threshold_var = tk.IntVar(value=160)
        self.invert_var = tk.BooleanVar(value=False)

        ttk.Label(controls, text="Threshold").pack(side="left")
        self.threshold_scale = ttk.Scale(
            controls,
            from_=0,
            to=255,
            orient="horizontal",
            command=self.on_scale_move,
            length=360,
        )
        self.threshold_scale.set(160)
        self.threshold_scale.pack(side="left", padx=8)

        self.threshold_value_label = ttk.Label(controls, text="160")
        self.threshold_value_label.pack(side="left", padx=(0, 20))

        ttk.Checkbutton(
            controls,
            text="Invert",
            variable=self.invert_var,
            command=self.update_preview,
        ).pack(side="left")

        ttk.Button(controls, text="Apply to this image", command=self.apply_current).pack(side="left", padx=20)

        previews = ttk.Frame(self.root, padding=10)
        previews.pack(fill="both", expand=True)

        left = ttk.LabelFrame(previews, text="Original", padding=10)
        left.pack(side="left", fill="both", expand=True, padx=(0, 5))

        right = ttk.LabelFrame(previews, text="Threshold preview", padding=10)
        right.pack(side="left", fill="both", expand=True, padx=(5, 0))

        self.original_label = ttk.Label(left)
        self.original_label.pack(expand=True)

        self.mask_label = ttk.Label(right)
        self.mask_label.pack(expand=True)

        bottom = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        bottom.pack(fill="x")

        self.info_label = ttk.Label(
            bottom,
            text="Tip: tune until the right parts are solid white in the threshold preview.",
        )
        self.info_label.pack(anchor="w")

    def load_existing_settings(self):
        if self.output_json.exists():
            try:
                self.settings = json.loads(self.output_json.read_text(encoding="utf-8"))
            except Exception:
                self.settings = {}

    def choose_folder(self):
        folder = filedialog.askdirectory(initialdir=str(self.image_dir if self.image_dir.exists() else Path.cwd()))
        if folder:
            self.load_directory(Path(folder))

    def load_directory(self, folder: Path):
        self.image_dir = folder
        if not self.image_dir.exists():
            self.files = []
            self.file_label.config(text="Folder not found")
            return

        self.files = [p for p in sorted(self.image_dir.iterdir()) if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS]
        self.index = 0
        if not self.files:
            self.file_label.config(text=f"No supported images in {self.image_dir}")
            self.original_label.configure(image="")
            self.mask_label.configure(image="")
            return
        self.show_current()

    def get_current_entry(self):
        if not self.files:
            return None
        name = self.files[self.index].name
        entry = self.settings.get(name, {})
        if not isinstance(entry, dict):
            entry = {}
        return entry

    def show_current(self):
        if not self.files:
            return
        path = self.files[self.index]
        entry = self.get_current_entry() or {}
        threshold = int(entry.get("threshold", 160))
        invert = bool(entry.get("invert", False))
        self.threshold_scale.set(threshold)
        self.threshold_value_label.config(text=str(threshold))
        self.invert_var.set(invert)
        self.file_label.config(text=f"{self.index + 1}/{len(self.files)}  {path.name}")
        self.update_preview()

    def on_scale_move(self, value):
        self.threshold_value_label.config(text=str(int(float(value))))
        self.update_preview()

    def update_preview(self):
        if not self.files:
            return
        path = self.files[self.index]
        threshold = int(float(self.threshold_scale.get()))
        invert = bool(self.invert_var.get())

        try:
            original_tk, mask_tk = make_preview(path, threshold, invert)
        except Exception as exc:
            messagebox.showerror("Preview error", f"Could not preview {path.name}\n\n{exc}")
            return

        self.current_original = original_tk
        self.current_mask = mask_tk
        self.original_label.configure(image=self.current_original)
        self.mask_label.configure(image=self.current_mask)

    def apply_current(self):
        if not self.files:
            return
        path = self.files[self.index]
        self.settings[path.name] = {
            "threshold": int(float(self.threshold_scale.get())),
            "invert": bool(self.invert_var.get()),
        }
        self.info_label.config(text=f"Saved in memory for {path.name}. Click Save thresholds.json to write the file.")

    def save_settings(self):
        try:
            self.output_json.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Save error", f"Could not save {self.output_json}\n\n{exc}")
            return
        self.info_label.config(text=f"Saved {self.output_json} with {len(self.settings)} image setting(s).")

    def prev_image(self):
        if not self.files:
            return
        self.apply_current()
        self.index = (self.index - 1) % len(self.files)
        self.show_current()

    def next_image(self):
        if not self.files:
            return
        self.apply_current()
        self.index = (self.index + 1) % len(self.files)
        self.show_current()


def main():
    root = tk.Tk()
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    app = ThresholdTunerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
