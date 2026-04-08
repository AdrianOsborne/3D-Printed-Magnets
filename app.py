from __future__ import annotations

import html
import json
import re
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from magnet_generator import (
    Settings,
    get_settings_for_image,
    iter_input_files,
    load_threshold_overrides,
    process_images,
    render_preview_images,
)

BASE_DIR = Path(__file__).resolve().parent
IMAGE_DIR = BASE_DIR / "images"
OUTPUT_DIR = BASE_DIR / "out"
THRESHOLDS_PATH = BASE_DIR / "thresholds.json"
LIBRARY_PATH = BASE_DIR / "library.json"
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".svg"}
SVGREPO_SEARCH_TEMPLATE = "https://www.svgrepo.com/vectors/{term}/monocolor/"
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.svgrepo.com/",
}

app = Flask(__name__)


def default_settings() -> Settings:
    return Settings()


def load_json_file(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback
    return data


def save_json_file(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_library() -> dict:
    data = load_json_file(LIBRARY_PATH, {})
    return data if isinstance(data, dict) else {}


def save_library(data: dict) -> None:
    save_json_file(LIBRARY_PATH, data)


def save_overrides(data: dict) -> None:
    save_json_file(THRESHOLDS_PATH, data)


def read_overrides() -> dict:
    return load_threshold_overrides(str(THRESHOLDS_PATH))


def sanitize_name(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", text.strip()).strip("-")
    return cleaned or "icon"


def display_name_from_filename(name: str) -> str:
    return Path(name).stem.replace("-", " ").replace("_", " ").strip() or Path(name).stem


def image_path_from_name(name: str) -> Path:
    candidate = (IMAGE_DIR / name).resolve()
    if candidate.parent != IMAGE_DIR.resolve() or not candidate.exists() or candidate.suffix.lower() not in SUPPORTED_EXTS:
        raise FileNotFoundError(name)
    return candidate


def output_path_from_name(name: str) -> Path:
    candidate = (OUTPUT_DIR / name).resolve()
    if candidate.parent != OUTPUT_DIR.resolve() or not candidate.exists():
        raise FileNotFoundError(name)
    return candidate


def get_unique_path(folder: Path, stem: str, suffix: str) -> Path:
    candidate = folder / f"{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = folder / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate


def ensure_library_entries() -> dict:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    library = load_library()
    files = {path.name for path in iter_input_files(IMAGE_DIR, SUPPORTED_EXTS)}
    for filename in files:
        entry = library.get(filename)
        if not isinstance(entry, dict):
            entry = {}
        entry.setdefault("source", "upload")
        entry.setdefault("enabled", True)
        entry.setdefault("displayName", display_name_from_filename(filename))
        library[filename] = entry
    stale_keys = [key for key in library if key not in files]
    for key in stale_keys:
        del library[key]
    save_library(library)
    return library


def build_image_entry(path: Path, library: dict, overrides: dict, settings: Settings) -> dict:
    lib_entry = library.get(path.name, {})
    image_settings = get_settings_for_image(path, settings, overrides)
    stl_name = f"{path.stem}.stl"
    output_exists = (OUTPUT_DIR / stl_name).exists()
    return {
        "name": path.name,
        "displayName": lib_entry.get("displayName", display_name_from_filename(path.name)),
        "source": lib_entry.get("source", "upload"),
        "enabled": bool(lib_entry.get("enabled", True)),
        "threshold": image_settings.threshold,
        "invert": image_settings.invert,
        "sourceUrl": lib_entry.get("sourceUrl", ""),
        "sourcePageUrl": lib_entry.get("sourcePageUrl", ""),
        "thumbnailUrl": lib_entry.get("thumbnailUrl", ""),
        "originalPreviewUrl": f"/preview/{quote(path.name)}?kind=original",
        "maskPreviewUrl": f"/preview/{quote(path.name)}?kind=mask",
        "downloadUrl": f"/outputs/{quote(stl_name)}" if output_exists else "",
        "hasOutput": output_exists,
    }


def build_state() -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    library = ensure_library_entries()
    overrides = read_overrides()
    settings = default_settings()
    images = [
        build_image_entry(path, library, overrides, settings)
        for path in iter_input_files(IMAGE_DIR, SUPPORTED_EXTS)
    ]
    images_by_source = {
        source: [image for image in images if image["source"] == source]
        for source in ("search", "upload", "url")
    }
    enabled_images = [image for image in images if image["enabled"]]
    outputs = [
        {"name": path.name, "downloadUrl": f"/outputs/{quote(path.name)}"}
        for path in sorted(OUTPUT_DIR.glob("*.stl"))
    ]
    return {
        "images": images,
        "imagesBySource": images_by_source,
        "enabledImages": enabled_images,
        "outputs": outputs,
        "defaults": {
            "threshold": settings.threshold,
            "diameter": settings.magnet_diameter_outer,
            "baseThickness": settings.base_thickness,
            "imageExtrusion": settings.image_extrusion,
            "imageMargin": settings.image_margin,
            "pocketDiameter": settings.pocket_diameter,
            "pocketDepth": settings.pocket_depth,
        },
    }


def read_generation_settings(payload: dict | None) -> Settings:
    payload = payload or {}
    defaults = default_settings()
    return Settings(
        magnet_diameter_outer=float(payload.get("diameter", defaults.magnet_diameter_outer)),
        base_thickness=float(payload.get("baseThickness", defaults.base_thickness)),
        image_extrusion=float(payload.get("imageExtrusion", defaults.image_extrusion)),
        image_margin=float(payload.get("imageMargin", defaults.image_margin)),
        pocket_diameter=float(payload.get("pocketDiameter", defaults.pocket_diameter)),
        pocket_depth=float(payload.get("pocketDepth", defaults.pocket_depth)),
        threshold=int(payload.get("threshold", defaults.threshold)),
        invert=bool(payload.get("invert", defaults.invert)),
        blur=defaults.blur,
        simplify_epsilon=defaults.simplify_epsilon,
        min_contour_area=defaults.min_contour_area,
        target_resolution=defaults.target_resolution,
    )


def fetch_text(url: str) -> str:
    request_obj = Request(url, headers=HTTP_HEADERS)
    with urlopen(request_obj, timeout=20) as response:
        return response.read().decode("utf-8", errors="ignore")


def download_remote_bytes(url: str) -> tuple[bytes, str]:
    request_obj = Request(url, headers=HTTP_HEADERS)
    with urlopen(request_obj, timeout=20) as response:
        data = response.read()
        content_type = response.headers.get("Content-Type", "").lower()
    return data, content_type


def infer_image_suffix(url: str, content_type: str, data: bytes) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in SUPPORTED_EXTS:
        return suffix
    if "svg" in content_type or b"<svg" in data.lower():
        return ".svg"
    if "png" in content_type or data.startswith(b"\x89PNG"):
        return ".png"
    if "jpeg" in content_type or "jpg" in content_type or data.startswith(b"\xff\xd8"):
        return ".jpg"
    if "webp" in content_type or data[:4] == b"RIFF":
        return ".webp"
    if "bmp" in content_type or data[:2] == b"BM":
        return ".bmp"
    raise ValueError("The URL did not return a supported image type.")


def absolute_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        return f"https://www.svgrepo.com{url}"
    return url


def parse_meta_content(page_html: str, prop_name: str) -> str:
    pattern = re.compile(
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop_name)}["\'][^>]+content=["\']([^"\']+)["\']',
        re.IGNORECASE,
    )
    match = pattern.search(page_html)
    return html.unescape(match.group(1)) if match else ""


def parse_svg_download_url(page_html: str) -> str:
    patterns = [
        re.compile(r'href=["\']([^"\']+\.svg(?:\?[^"\']*)?)["\']', re.IGNORECASE),
        re.compile(r'data-url=["\']([^"\']+\.svg(?:\?[^"\']*)?)["\']', re.IGNORECASE),
        re.compile(r'"(https://[^"]+\.svg(?:\?[^"]*)?)"', re.IGNORECASE),
    ]
    for pattern in patterns:
        for match in pattern.finditer(page_html):
            url = absolute_url(html.unescape(match.group(1)))
            if url.lower().endswith(".svg") or ".svg?" in url.lower():
                return url
    return ""


def normalize_svgrepo_term(query: str) -> str:
    parts = [part for part in re.split(r"[\s/]+", query.strip().lower()) if part]
    return "-".join(parts) or "icon"


def build_svgrepo_search_url(query: str) -> str:
    return SVGREPO_SEARCH_TEMPLATE.format(term=quote(normalize_svgrepo_term(query)))


def parse_svgrepo_import_url(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url.strip())
    if parsed.netloc.lower() not in {"www.svgrepo.com", "svgrepo.com"}:
        raise ValueError("Only SVG Repo links are allowed here.")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 3 and parts[0] == "download":
        icon_id = parts[1]
        slug = Path(parts[2]).stem
        return (
            f"https://www.svgrepo.com/svg/{icon_id}/{slug}",
            f"https://www.svgrepo.com/download/{icon_id}/{slug}.svg",
            display_name_from_filename(slug),
        )
    if len(parts) >= 3 and parts[0] == "svg":
        icon_id = parts[1]
        slug = parts[2]
        return (
            f"https://www.svgrepo.com/svg/{icon_id}/{slug}",
            f"https://www.svgrepo.com/download/{icon_id}/{slug}.svg",
            display_name_from_filename(slug),
        )
    raise ValueError("Use an SVG Repo icon page or SVG Repo download link.")


def resolve_svgrepo_download_url(source_url: str) -> tuple[str, str, str, str]:
    page_url, direct_download_url, display_name = parse_svgrepo_import_url(source_url)
    thumbnail_url = ""
    resolved_download_url = direct_download_url
    try:
        item_html = fetch_text(page_url)
        thumbnail_url = parse_meta_content(item_html, "og:image")
        parsed_download = parse_svg_download_url(item_html)
        if parsed_download:
            resolved_download_url = parsed_download
    except Exception:
        pass
    return page_url, resolved_download_url, display_name, thumbnail_url


def store_library_entry(
    filename: str,
    source: str,
    display_name: str,
    source_url: str = "",
    source_page_url: str = "",
    thumbnail_url: str = "",
) -> None:
    library = ensure_library_entries()
    library[filename] = {
        "source": source,
        "enabled": True,
        "displayName": display_name,
        "sourceUrl": source_url,
        "sourcePageUrl": source_page_url,
        "thumbnailUrl": thumbnail_url,
    }
    save_library(library)


def rename_related_files(old_name: str, new_name: str) -> str:
    old_path = image_path_from_name(old_name)
    new_stem = sanitize_name(new_name)
    target = get_unique_path(IMAGE_DIR, new_stem, old_path.suffix.lower())
    old_path.rename(target)

    overrides = read_overrides()
    if old_name in overrides:
        overrides[target.name] = overrides.pop(old_name)
        save_overrides(overrides)

    library = ensure_library_entries()
    if old_name in library:
        entry = library.pop(old_name)
        entry["displayName"] = display_name_from_filename(target.name)
        library[target.name] = entry
        save_library(library)

    old_output = OUTPUT_DIR / f"{Path(old_name).stem}.stl"
    if old_output.exists():
        new_output = OUTPUT_DIR / f"{target.stem}.stl"
        if new_output.exists():
            new_output.unlink()
        old_output.rename(new_output)
    return target.name


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def api_state():
    return jsonify(build_state())


@app.post("/api/svgrepo/import-link")
def api_svgrepo_import_link():
    payload = request.get_json(silent=True) or {}
    source_url = str(payload.get("url", "")).strip()
    if not source_url:
        return jsonify({"error": "Enter an SVG Repo link."}), 400
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        page_url, download_url, display_name, thumbnail_url = resolve_svgrepo_download_url(source_url)
        svg_bytes, _content_type = download_remote_bytes(download_url)
        target = get_unique_path(IMAGE_DIR, sanitize_name(display_name), ".svg")
        target.write_bytes(svg_bytes)
        store_library_entry(
            filename=target.name,
            source="search",
            display_name=display_name_from_filename(target.name),
            source_url=download_url,
            source_page_url=page_url,
            thumbnail_url=thumbnail_url,
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"imported": target.name, "state": build_state()})


@app.post("/api/images/upload")
def api_upload_images():
    uploaded = request.files.getlist("files")
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    imported = []
    for file in uploaded:
        if not file or not file.filename:
            continue
        suffix = Path(file.filename).suffix.lower()
        if suffix not in SUPPORTED_EXTS:
            continue
        stem = sanitize_name(Path(secure_filename(file.filename)).stem)
        target = get_unique_path(IMAGE_DIR, stem, suffix)
        file.save(target)
        store_library_entry(
            filename=target.name,
            source="upload",
            display_name=display_name_from_filename(target.name),
        )
        imported.append(target.name)
    return jsonify({"imported": imported, "state": build_state()})


@app.post("/api/images/import-url")
def api_import_url():
    payload = request.get_json(silent=True) or {}
    url = str(payload.get("url", "")).strip()
    if not url:
        return jsonify({"error": "Enter an image URL."}), 400
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    explicit_name = str(payload.get("name", "")).strip()
    stem = sanitize_name(explicit_name) if explicit_name else sanitize_name(Path(urlparse(url).path).stem or "imported-image")
    try:
        image_bytes, content_type = download_remote_bytes(url)
        suffix = infer_image_suffix(url, content_type, image_bytes)
        target = get_unique_path(IMAGE_DIR, stem, suffix)
        target.write_bytes(image_bytes)
        store_library_entry(
            filename=target.name,
            source="url",
            display_name=display_name_from_filename(target.name),
            source_url=url,
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"imported": target.name, "state": build_state()})


@app.post("/api/images/<path:name>/toggle")
def api_toggle_image(name: str):
    try:
        path = image_path_from_name(name)
    except FileNotFoundError:
        return jsonify({"error": "Image not found."}), 404
    payload = request.get_json(silent=True) or {}
    library = ensure_library_entries()
    entry = library.get(path.name, {})
    entry["enabled"] = bool(payload.get("enabled", True))
    entry.setdefault("source", "upload")
    entry.setdefault("displayName", display_name_from_filename(path.name))
    library[path.name] = entry
    save_library(library)
    return jsonify({"toggled": path.name, "state": build_state()})


@app.post("/api/images/<path:name>/rename")
def api_rename_image(name: str):
    try:
        image_path_from_name(name)
    except FileNotFoundError:
        return jsonify({"error": "Image not found."}), 404
    payload = request.get_json(silent=True) or {}
    new_name = str(payload.get("name", "")).strip()
    if not new_name:
        return jsonify({"error": "Enter a new image name."}), 400
    updated_name = rename_related_files(name, new_name)
    return jsonify({"renamed": name, "newName": updated_name, "state": build_state()})


@app.post("/api/images/<path:name>/settings")
def api_update_image_settings(name: str):
    try:
        path = image_path_from_name(name)
    except FileNotFoundError:
        return jsonify({"error": "Image not found."}), 404
    payload = request.get_json(silent=True) or {}
    overrides = read_overrides()
    overrides[path.name] = {
        "threshold": int(payload.get("threshold", default_settings().threshold)),
        "invert": bool(payload.get("invert", False)),
    }
    save_overrides(overrides)
    return jsonify({"saved": path.name, "state": build_state()})


@app.post("/api/generate")
def api_generate():
    payload = request.get_json(silent=True) or {}
    requested_names = payload.get("images") or []
    state = build_state()
    enabled_names = [image["name"] for image in state["enabledImages"]]
    names_to_generate = requested_names or enabled_names
    try:
        files = [image_path_from_name(name) for name in names_to_generate]
    except FileNotFoundError:
        return jsonify({"error": "One or more selected images no longer exist."}), 404
    if not files:
        return jsonify({"error": "Enable at least one image before generating."}), 400
    settings = read_generation_settings(payload.get("settings"))
    overrides = read_overrides()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        results = process_images(files, OUTPUT_DIR, settings, overrides)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(
        {
            "generated": [
                {
                    "image": image_path.name,
                    "output": stl_path.name,
                    "threshold": image_settings.threshold,
                    "invert": image_settings.invert,
                }
                for image_path, stl_path, image_settings in results
            ],
            "state": build_state(),
        }
    )


@app.get("/preview/<path:name>")
def preview_image(name: str):
    kind = request.args.get("kind", "original")
    try:
        path = image_path_from_name(name)
    except FileNotFoundError:
        return jsonify({"error": "Image not found."}), 404
    overrides = read_overrides()
    settings = get_settings_for_image(path, default_settings(), overrides)
    threshold_override = request.args.get("threshold")
    invert_override = request.args.get("invert")
    if threshold_override is not None:
        settings.threshold = int(threshold_override)
    if invert_override is not None:
        settings.invert = invert_override.lower() in {"1", "true", "yes", "on"}
    original, mask = render_preview_images(path, settings, preview_size=960)
    selected = mask if kind == "mask" else original
    buffer = BytesIO()
    selected.save(buffer, format="PNG")
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png")


@app.get("/outputs/<path:name>")
def download_output(name: str):
    try:
        path = output_path_from_name(name)
    except FileNotFoundError:
        return jsonify({"error": "Output not found."}), 404
    return send_file(path, as_attachment=True, download_name=path.name)


@app.get("/favicon.ico")
def favicon():
    return ("", 204)


if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=5000)
