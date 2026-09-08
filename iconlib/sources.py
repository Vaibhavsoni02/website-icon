"""Where icons come from: Iconify, twenty-icons (company logos by domain), any URL, uploads."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import requests

ICONIFY = "https://api.iconify.design"
TWENTY = "https://twenty-icons.com"
UA = {"User-Agent": "icon-studio/1.0 (+local tool)"}
TIMEOUT = 15

# Sets that carry brand/product marks - handy as a default filter when drawing
# architecture diagrams.
LOGO_SETS = [
    "logos", "simple-icons", "devicon", "skill-icons", "vscode-icons", "cib",
    "fa6-brands", "mdi", "tabler", "carbon", "material-symbols", "ph", "lucide",
]

EXT_BY_TYPE = {
    "image/svg+xml": "svg",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/x-icon": "ico",
    "image/vnd.microsoft.icon": "ico",
}


class SourceError(RuntimeError):
    pass


def _get(url: str, **kwargs: Any) -> requests.Response:
    try:
        resp = requests.get(url, headers=UA, timeout=TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        raise SourceError(f"Request failed: {exc}") from exc
    if resp.status_code != 200:
        raise SourceError(f"HTTP {resp.status_code} for {url}")
    return resp


# --- Iconify --------------------------------------------------------------

def iconify_search(query: str, limit: int = 48, prefixes: Optional[List[str]] = None) -> List[str]:
    """Return icon names like 'logos:aws'. Empty query returns []."""
    if not query.strip():
        return []
    params: Dict[str, Any] = {"query": query.strip(), "limit": max(32, min(int(limit), 999))}
    if prefixes:
        params["prefixes"] = ",".join(prefixes)
    data = _get(f"{ICONIFY}/search", params=params).json()
    return list(data.get("icons", []))[:limit]


def iconify_preview_url(name: str, height: int = 48, color: Optional[str] = None) -> str:
    prefix, _, icon = name.partition(":")
    url = f"{ICONIFY}/{prefix}/{icon}.svg?height={height}"
    if color:
        url += f"&color={color.lstrip('#')}"
    return url


def iconify_fetch(name: str, height: int = 128, color: Optional[str] = None) -> Tuple[bytes, str]:
    """Download one Iconify icon as SVG bytes."""
    resp = _get(iconify_preview_url(name, height=height, color=color))
    body = resp.content
    if b"<svg" not in body[:512]:
        raise SourceError(f"'{name}' did not return an SVG")
    return body, "svg"


# --- twenty-icons (github.com/twentyhq/favicon) ---------------------------

DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$", re.I)
TWENTY_SIZES = [16, 32, 64, 128, 180, 192]


def clean_domain(value: str) -> str:
    """'https://www.Stripe.com/pricing' -> 'stripe.com'."""
    value = value.strip().lower()
    value = re.sub(r"^[a-z]+://", "", value)
    value = value.split("/")[0].split("?")[0]
    if value.startswith("www."):
        value = value[4:]
    return value


def twenty_fetch(domain: str, size: int = 128) -> Tuple[bytes, str]:
    """Company logo for a domain, via the twentyhq/favicon service."""
    domain = clean_domain(domain)
    if not DOMAIN_RE.match(domain):
        raise SourceError(f"'{domain}' does not look like a domain (try stripe.com)")
    size = size if size in TWENTY_SIZES else 128
    resp = _get(f"{TWENTY}/{domain}/{size}")
    ext = EXT_BY_TYPE.get(resp.headers.get("content-type", "").split(";")[0].strip(), "png")
    if not resp.content:
        raise SourceError(f"No logo returned for {domain}")
    return resp.content, ext


def twenty_preview_url(domain: str, size: int = 64) -> str:
    return f"{TWENTY}/{clean_domain(domain)}/{size if size in TWENTY_SIZES else 64}"


# --- arbitrary URL / upload ----------------------------------------------

def url_fetch(url: str) -> Tuple[bytes, str]:
    if not url.startswith(("http://", "https://")):
        raise SourceError("URL must start with http:// or https://")
    resp = _get(url)
    ctype = resp.headers.get("content-type", "").split(";")[0].strip()
    ext = EXT_BY_TYPE.get(ctype)
    if ext is None:
        tail = url.split("?")[0].rsplit(".", 1)
        ext = tail[-1].lower() if len(tail) == 2 and len(tail[-1]) <= 4 else "png"
    if ext not in EXT_BY_TYPE.values():
        raise SourceError(f"Unsupported content type: {ctype or 'unknown'}")
    return resp.content, ext


def sniff_ext(filename: str, data: bytes) -> str:
    if data[:5].lower().startswith(b"<?xml") or b"<svg" in data[:512].lower():
        return "svg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:4] == b"\x00\x00\x01\x00":
        return "ico"
    return (filename.rsplit(".", 1)[-1].lower() if "." in filename else "png")


def suggest_name(source: str, ref: str) -> str:
    """A sensible default library name for a fetched icon."""
    if source == "iconify":
        return ref.split(":")[-1]
    if source == "twenty-icons":
        return clean_domain(ref).rsplit(".", 1)[0].replace(".", "-")
    if source == "url":
        tail = ref.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
        return tail.rsplit(".", 1)[0] or "icon"
    return ref or "icon"
