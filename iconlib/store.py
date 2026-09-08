"""Local icon library: files on disk + a JSON manifest, both committed to the repo."""

from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import ghstore

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


# Results of background GitHub mirroring, drained by the UI to show toasts.
SYNC_EVENTS: List[tuple] = []


def _sync(message: str, paths: Iterable[str], deletes: Iterable[str] = ()) -> None:
    """Mirror the given repo-relative paths to GitHub, if a token is configured.

    A failure here must never lose the local write, so problems are recorded
    rather than raised.
    """
    if not ghstore.enabled():
        return
    files = {}
    for path in paths:
        full = ROOT / path
        if full.exists():
            files[path] = full.read_bytes()
    try:
        sha = ghstore.commit_files(files, message, deletes=deletes)
        if sha:
            SYNC_EVENTS.append((True, f"Committed to GitHub ({sha})"))
    except Exception as exc:  # noqa: BLE001 - surfaced in the UI instead
        SYNC_EVENTS.append((False, f"GitHub sync failed: {exc}"))


def drain_sync() -> List[tuple]:
    events, SYNC_EVENTS[:] = list(SYNC_EVENTS), []
    return events


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
    stale = ""
    if old and old.get("file") and old["file"] != filename:
        (ICON_DIR / old["file"]).unlink(missing_ok=True)
        stale = f"icons/{old['file']}"

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
    _sync(f"Add icon {icon_id}", [f"icons/{filename}", "icons/manifest.json"],
          deletes=[stale] if stale else ())
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
    _sync(f"Update icon {icon_id}", ["icons/manifest.json"])
    return record


def delete_icon(icon_id: str) -> bool:
    manifest = load_manifest()
    record = manifest["icons"].pop(icon_id, None)
    if not record:
        return False
    (ICON_DIR / record["file"]).unlink(missing_ok=True)
    save_manifest(manifest)
    _sync(f"Remove icon {icon_id}", ["icons/manifest.json"],
          deletes=[f"icons/{record['file']}"])
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


def save_diagram(name: str, spec: Dict[str, Any], sync: bool = True) -> Path:
    _ensure_dirs()
    path = DIAGRAM_DIR / f"{slugify(name)}.json"
    path.write_text(json.dumps(spec, indent=2) + "\n")
    if sync:
        _sync(f"Save diagram {slugify(name)}", [f"diagrams/{path.name}"])
    return path


def save_diagram_bundle(name: str, spec: Dict[str, Any], svg: str) -> Path:
    """Spec + rendered SVG, mirrored to GitHub as a single commit."""
    slug = slugify(name)
    save_diagram(name, spec, sync=False)
    export = save_export(name, svg, sync=False)
    _sync(f"Save diagram {slug}",
          [f"diagrams/{slug}.json", f"exports/{export.name}"])
    return export


def load_diagram(name: str) -> Dict[str, Any]:
    return json.loads((DIAGRAM_DIR / f"{slugify(name)}.json").read_text())


def delete_diagram(name: str) -> None:
    slug = slugify(name)
    (DIAGRAM_DIR / f"{slug}.json").unlink(missing_ok=True)
    (EXPORT_DIR / f"{slug}.svg").unlink(missing_ok=True)
    _sync(f"Remove diagram {slug}", [],
          deletes=[f"diagrams/{slug}.json", f"exports/{slug}.svg"])


def save_export(name: str, svg: str, sync: bool = True) -> Path:
    _ensure_dirs()
    path = EXPORT_DIR / f"{slugify(name)}.svg"
    path.write_text(svg)
    if sync:
        _sync(f"Export {path.name}", [f"exports/{path.name}"])
    return path
