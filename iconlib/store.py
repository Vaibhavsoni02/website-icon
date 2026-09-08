"""Local icon library: files on disk + a JSON manifest, both committed to the repo."""

from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / "icons"
MANIFEST = ICON_DIR / "manifest.json"
DIAGRAM_DIR = ROOT / "diagrams"
EXPORT_DIR = ROOT / "exports"

MIME = {
    "svg": "image/svg+xml",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "ico": "image/x-icon",
}


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")
    return slug or "icon"


def _ensure_dirs() -> None:
    for d in (ICON_DIR, DIAGRAM_DIR, EXPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_manifest() -> Dict[str, Any]:
    _ensure_dirs()
    if not MANIFEST.exists():
        return {"version": 1, "icons": {}}
    try:
        data = json.loads(MANIFEST.read_text())
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "icons": {}}
    data.setdefault("icons", {})
    return data


def save_manifest(manifest: Dict[str, Any]) -> None:
    _ensure_dirs()
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def unique_id(base: str, taken: Optional[set] = None) -> str:
    taken = taken if taken is not None else set(load_manifest()["icons"])
    slug = slugify(base)
    if slug not in taken:
        return slug
    n = 2
    while f"{slug}-{n}" in taken:
        n += 1
    return f"{slug}-{n}"


def save_icon(
    name: str,
    data: bytes,
    ext: str,
    source: str,
    ref: str = "",
    tags: Optional[List[str]] = None,
    icon_id: Optional[str] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Write the icon file and register it in the manifest. Returns the record."""
    _ensure_dirs()
    manifest = load_manifest()
    ext = (ext or "svg").lower().lstrip(".")
    if icon_id is None:
        icon_id = slugify(name) if overwrite else unique_id(name, set(manifest["icons"]))

    filename = f"{icon_id}.{ext}"
    (ICON_DIR / filename).write_bytes(data)

    # A re-save with a different extension shouldn't leave the old file behind.
    old = manifest["icons"].get(icon_id)
    if old and old.get("file") and old["file"] != filename:
        (ICON_DIR / old["file"]).unlink(missing_ok=True)

    record = {
        "id": icon_id,
        "name": name,
        "file": filename,
        "ext": ext,
        "source": source,
        "ref": ref,
        "tags": sorted({t.strip().lower() for t in (tags or []) if t.strip()}),
        "bytes": len(data),
        "added_at": (old or {}).get("added_at") or time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    manifest["icons"][icon_id] = record
    save_manifest(manifest)
    return record


def update_icon(icon_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    manifest = load_manifest()
    record = manifest["icons"].get(icon_id)
    if not record:
        return None
    if "tags" in fields:
        fields["tags"] = sorted({t.strip().lower() for t in fields["tags"] if t.strip()})
    record.update(fields)
    save_manifest(manifest)
    return record


def delete_icon(icon_id: str) -> bool:
    manifest = load_manifest()
    record = manifest["icons"].pop(icon_id, None)
    if not record:
        return False
    (ICON_DIR / record["file"]).unlink(missing_ok=True)
    save_manifest(manifest)
    return True


def icon_path(record: Dict[str, Any]) -> Path:
    return ICON_DIR / record["file"]


def icon_bytes(record: Dict[str, Any]) -> bytes:
    path = icon_path(record)
    return path.read_bytes() if path.exists() else b""


def mime_of(record: Dict[str, Any]) -> str:
    return MIME.get(record.get("ext", ""), "application/octet-stream")


def data_uri(record: Dict[str, Any]) -> str:
    raw = icon_bytes(record)
    if not raw:
        return ""
    return f"data:{mime_of(record)};base64,{base64.b64encode(raw).decode()}"


def rel_path(record: Dict[str, Any]) -> str:
    return f"icons/{record['file']}"


def list_icons(query: str = "", tag: str = "") -> List[Dict[str, Any]]:
    icons = list(load_manifest()["icons"].values())
    if query:
        q = query.lower().strip()
        icons = [
            i for i in icons
            if q in i["id"] or q in i["name"].lower() or any(q in t for t in i.get("tags", []))
        ]
    if tag:
        icons = [i for i in icons if tag in i.get("tags", [])]
    return sorted(icons, key=lambda i: i["id"])


def all_tags() -> List[str]:
    tags: set = set()
    for record in load_manifest()["icons"].values():
        tags.update(record.get("tags", []))
    return sorted(tags)


def icon_map() -> Dict[str, Dict[str, Any]]:
    return load_manifest()["icons"]


# --- saved diagrams -------------------------------------------------------

def list_diagrams() -> List[str]:
    _ensure_dirs()
    return sorted(p.stem for p in DIAGRAM_DIR.glob("*.json"))


def save_diagram(name: str, spec: Dict[str, Any]) -> Path:
    _ensure_dirs()
    path = DIAGRAM_DIR / f"{slugify(name)}.json"
    path.write_text(json.dumps(spec, indent=2) + "\n")
    return path


def load_diagram(name: str) -> Dict[str, Any]:
    return json.loads((DIAGRAM_DIR / f"{slugify(name)}.json").read_text())


def delete_diagram(name: str) -> None:
    (DIAGRAM_DIR / f"{slugify(name)}.json").unlink(missing_ok=True)


def save_export(name: str, svg: str) -> Path:
    _ensure_dirs()
    path = EXPORT_DIR / f"{slugify(name)}.svg"
    path.write_text(svg)
    return path
