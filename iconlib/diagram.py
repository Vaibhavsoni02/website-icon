"""Turn a diagram spec into one self-contained SVG (icons embedded as data URIs)."""

from __future__ import annotations

import base64
import re
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

from . import store

NODE_W = 180
NODE_H = 112
COL_GAP = 104
ROW_GAP = 44
MARGIN = 44
TITLE_H = 60
ICON = 44
GROUP_PAD = 22
GROUP_LABEL_H = 26

FONT = ("-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,'Helvetica Neue',"
        "Arial,sans-serif")

THEMES = {
    "light": dict(
        bg="#ffffff", card="#ffffff", card_stroke="#e3e7f0", text="#141a2c",
        sub="#6c7488", edge="#98a2b6", edge_text="#5d6577", edge_pill="#ffffff",
        group_stroke="#d3daea", group_fill="#f7f9fd", group_text="#7b839a",
        title="#0e1424", shadow_opacity="0.10",
    ),
    "dark": dict(
        bg="#0e1320", card="#181f2e", card_stroke="#2b3448", text="#e9edf7",
        sub="#98a2ba", edge="#5c6782", edge_text="#96a0b8", edge_pill="#0e1320",
        group_stroke="#2e3853", group_fill="#131a29", group_text="#8a94ad",
        title="#f3f6fd", shadow_opacity="0.45",
    ),
}

ACCENTS = ["#5b8def", "#22a06b", "#e0851f", "#b957d6", "#d95c5c", "#2aa9bf",
           "#7a86e8", "#4f9d3a"]


def blank_spec() -> Dict[str, Any]:
    return {
        "title": "",
        "direction": "LR",
        "theme": "light",
        "nodes": [],
        "edges": [],
        "groups": [],
    }


# --- layout ---------------------------------------------------------------

def _assign_layers(nodes: List[dict], edges: List[dict]) -> Dict[str, int]:
    """Longest-path layering; an explicit `col` on a node always wins."""
    ids = [n["id"] for n in nodes]
    idset = set(ids)
    auto = {i: 0 for i in ids}
    live = [e for e in edges if e.get("src") in idset and e.get("dst") in idset
            and e["src"] != e["dst"]]
    for _ in range(len(ids) + 1):
        changed = False
        for e in live:
            want = auto[e["src"]] + 1
            if want > auto[e["dst"]] and want <= len(ids):
                auto[e["dst"]] = want
                changed = True
        if not changed:
            break
    out = {}
    for n in nodes:
        col = n.get("col")
        out[n["id"]] = int(col) if col is not None and str(col) != "" else auto[n["id"]]
    return out


def _layout(spec: Dict[str, Any]) -> Tuple[Dict[str, Tuple[float, float]], float, float]:
    nodes = spec["nodes"]
    if not nodes:
        return {}, 420, 200

    horizontal = spec.get("direction", "LR").upper() != "TB"
    layers = _assign_layers(nodes, spec.get("edges", []))
    has_groups = any(n.get("group") for n in nodes)

    lane_gap = (COL_GAP if horizontal else ROW_GAP + 26) + (26 if has_groups else 0)
    stack_gap = (ROW_GAP if horizontal else 36) + (34 if has_groups else 0)

    # Keep members of the same group next to each other inside a lane.
    group_order: Dict[str, int] = {}
    for n in nodes:
        g = n.get("group") or ""
        group_order.setdefault(g, len(group_order))
    order = {n["id"]: i for i, n in enumerate(nodes)}

    lanes: Dict[int, List[str]] = {}
    for n in nodes:
        lanes.setdefault(layers[n["id"]], []).append(n["id"])
    by_id = {n["id"]: n for n in nodes}
    for lane in lanes.values():
        lane.sort(key=lambda i: (group_order[by_id[i].get("group") or ""], order[i]))

    lane_keys = sorted(lanes)
    title_h = TITLE_H if spec.get("title") else 0
    size_along = NODE_W if horizontal else NODE_H
    size_across = NODE_H if horizontal else NODE_W
    step = size_across + stack_gap

    # Each group gets its own band of rows (columns in TB) so a group's bounding
    # box can never enclose a node that isn't a member of it.
    rows: Dict[str, float] = {}
    if has_groups:
        bands = []
        for n in nodes:
            key = n.get("group") or ""
            if key not in bands:
                bands.append(key)
        if "" in bands:  # ungrouped nodes sit in the first band
            bands.remove("")
            bands.insert(0, "")
        height_of, offset_of, cursor = {}, {}, 0
        for key in bands:
            per_lane: Dict[int, int] = {}
            for n in nodes:
                if (n.get("group") or "") == key:
                    per_lane[layers[n["id"]]] = per_lane.get(layers[n["id"]], 0) + 1
            height_of[key] = max(per_lane.values()) if per_lane else 1
            offset_of[key] = cursor
            cursor += height_of[key]
        total_rows = cursor
        for lane in lane_keys:
            for key in bands:
                members = [i for i in lanes[lane] if (by_id[i].get("group") or "") == key]
                if not members:
                    continue
                first = offset_of[key] + (height_of[key] - len(members)) / 2.0
                for mi, node_id in enumerate(members):
                    rows[node_id] = first + mi
    else:
        total_rows = max(len(v) for v in lanes.values())
        for lane in lane_keys:
            members = lanes[lane]
            first = (total_rows - len(members)) / 2.0
            for mi, node_id in enumerate(members):
                rows[node_id] = first + mi

    pad_across = (GROUP_PAD + GROUP_LABEL_H) if has_groups else 0
    span_along = len(lane_keys) * size_along + (len(lane_keys) - 1) * lane_gap
    span_across = total_rows * size_across + (total_rows - 1) * stack_gap + pad_across * 2

    if horizontal:
        width = MARGIN * 2 + span_along
        height = MARGIN * 2 + title_h + span_across
    else:
        width = MARGIN * 2 + span_across
        height = MARGIN * 2 + title_h + span_along

    pos: Dict[str, Tuple[float, float]] = {}
    for li, lane in enumerate(lane_keys):
        for node_id in lanes[lane]:
            along = li * (size_along + lane_gap)
            across = pad_across + rows[node_id] * step
            if horizontal:
                pos[node_id] = (MARGIN + along, MARGIN + title_h + across)
            else:
                pos[node_id] = (MARGIN + across, MARGIN + title_h + along)
    return pos, width, height


# --- helpers --------------------------------------------------------------

def _wrap(text: str, max_chars: int, max_lines: int) -> List[str]:
    words, lines, cur = str(text).split(), [], ""
    for word in words:
        candidate = f"{cur} {word}".strip()
        if len(candidate) <= max_chars or not cur:
            cur = candidate
        else:
            lines.append(cur)
            cur = word
            if len(lines) == max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if not lines:
        return [""]
    if len(lines) == max_lines:
        leftover = len(" ".join(words)) > len(" ".join(lines))
        if leftover or len(lines[-1]) > max_chars:
            lines[-1] = lines[-1][: max_chars - 1].rstrip() + "…"
    return lines


def _icon_uri(icon_id: Optional[str], icons: Dict[str, dict]) -> str:
    if not icon_id:
        return ""
    record = icons.get(icon_id)
    return store.data_uri(record) if record else ""


def _bezier_mid(p0, p1, p2, p3) -> Tuple[float, float]:
    return (
        (p0[0] + 3 * p1[0] + 3 * p2[0] + p3[0]) / 8,
        (p0[1] + 3 * p1[1] + 3 * p2[1] + p3[1]) / 8,
    )


def _edge_path(src_xy, dst_xy, horizontal: bool):
    """Return (path_d, start, c1, c2, end) for one edge."""
    sx, sy = src_xy
    dx, dy = dst_xy
    if horizontal:
        forward = dx > sx + NODE_W / 2
        if forward:
            start = (sx + NODE_W, sy + NODE_H / 2)
            end = (dx, dy + NODE_H / 2)
        elif dx < sx - NODE_W / 2:
            start = (sx, sy + NODE_H / 2)
            end = (dx + NODE_W, dy + NODE_H / 2)
        else:  # same lane - loop out to the side
            start = (sx + NODE_W, sy + NODE_H / 2)
            end = (dx + NODE_W, dy + NODE_H / 2)
            bulge = 56
            c1 = (start[0] + bulge, start[1])
            c2 = (end[0] + bulge, end[1])
            return (f"M{start[0]:.1f},{start[1]:.1f} C{c1[0]:.1f},{c1[1]:.1f} "
                    f"{c2[0]:.1f},{c2[1]:.1f} {end[0]:.1f},{end[1]:.1f}"), start, c1, c2, end
        pull = max(46, abs(end[0] - start[0]) * 0.45)
        sign = 1 if end[0] >= start[0] else -1
        c1 = (start[0] + pull * sign, start[1])
        c2 = (end[0] - pull * sign, end[1])
    else:
        forward = dy > sy + NODE_H / 2
        if forward:
            start = (sx + NODE_W / 2, sy + NODE_H)
            end = (dx + NODE_W / 2, dy)
        elif dy < sy - NODE_H / 2:
            start = (sx + NODE_W / 2, sy)
            end = (dx + NODE_W / 2, dy + NODE_H)
        else:
            start = (sx + NODE_W, sy + NODE_H / 2)
            end = (dx + NODE_W, dy + NODE_H / 2)
            c1 = (start[0] + 56, start[1])
            c2 = (end[0] + 56, end[1])
            return (f"M{start[0]:.1f},{start[1]:.1f} C{c1[0]:.1f},{c1[1]:.1f} "
                    f"{c2[0]:.1f},{c2[1]:.1f} {end[0]:.1f},{end[1]:.1f}"), start, c1, c2, end
        pull = max(40, abs(end[1] - start[1]) * 0.45)
        sign = 1 if end[1] >= start[1] else -1
        c1 = (start[0], start[1] + pull * sign)
        c2 = (end[0], end[1] - pull * sign)
    d = (f"M{start[0]:.1f},{start[1]:.1f} C{c1[0]:.1f},{c1[1]:.1f} "
         f"{c2[0]:.1f},{c2[1]:.1f} {end[0]:.1f},{end[1]:.1f}")
    return d, start, c1, c2, end


# --- render ---------------------------------------------------------------

def render_svg(spec: Dict[str, Any], icons: Optional[Dict[str, dict]] = None) -> str:
    icons = icons if icons is not None else store.icon_map()
    theme = THEMES.get(spec.get("theme", "light"), THEMES["light"])
    horizontal = spec.get("direction", "LR").upper() != "TB"
    nodes = [n for n in spec.get("nodes", []) if n.get("id")]
    node_ids = {n["id"] for n in nodes}
    edges = [e for e in spec.get("edges", [])
             if e.get("src") in node_ids and e.get("dst") in node_ids]
    pos, width, height = _layout({**spec, "nodes": nodes})

    if not nodes:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="420" height="160" '
                f'viewBox="0 0 420 160"><rect width="420" height="160" rx="12" '
                f'fill="{theme["bg"]}"/><text x="210" y="86" text-anchor="middle" '
                f'font-family="{FONT}" font-size="14" fill="{theme["sub"]}">'
                f'Add a node to start your diagram</text></svg>')

    out: List[str] = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'font-family="{FONT}">'
    )

    edge_colors = sorted({e.get("color") or theme["edge"] for e in edges} | {theme["edge"]})
    marker_id = {c: f"arw{i}" for i, c in enumerate(edge_colors)}
    out.append("<defs>")
    out.append(
        f'<filter id="cardshadow" x="-25%" y="-25%" width="150%" height="160%">'
        f'<feDropShadow dx="0" dy="2" stdDeviation="3.2" flood-color="#0b1330" '
        f'flood-opacity="{theme["shadow_opacity"]}"/></filter>'
    )
    for color, mid in marker_id.items():
        out.append(
            f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,1 L9,5 L0,9 z" fill="{color}"/></marker>'
        )
    out.append("</defs>")
    out.append(f'<rect width="{width:.0f}" height="{height:.0f}" fill="{theme["bg"]}"/>')

    if spec.get("title"):
        out.append(
            f'<text x="{MARGIN}" y="{MARGIN + 16}" font-size="21" font-weight="650" '
            f'fill="{theme["title"]}">{escape(str(spec["title"]))}</text>'
        )

    # group containers, drawn behind everything
    group_labels = {g.get("id"): g.get("label") or g.get("id")
                    for g in spec.get("groups", []) if g.get("id")}
    group_colors = {g.get("id"): g.get("color") for g in spec.get("groups", []) if g.get("id")}
    members: Dict[str, List[str]] = {}
    for n in nodes:
        if n.get("group"):
            members.setdefault(str(n["group"]), []).append(n["id"])
    for gi, (gid, ids) in enumerate(sorted(members.items())):
        xs = [pos[i][0] for i in ids]
        ys = [pos[i][1] for i in ids]
        gx = min(xs) - GROUP_PAD
        gy = min(ys) - GROUP_PAD - GROUP_LABEL_H
        gw = max(xs) + NODE_W + GROUP_PAD - gx
        gh = max(ys) + NODE_H + GROUP_PAD - gy
        stroke = group_colors.get(gid) or theme["group_stroke"]
        out.append(
            f'<rect x="{gx:.1f}" y="{gy:.1f}" width="{gw:.1f}" height="{gh:.1f}" rx="16" '
            f'fill="{theme["group_fill"]}" stroke="{stroke}" stroke-width="1.2" '
            f'stroke-dasharray="6 5"/>'
        )
        out.append(
            f'<text x="{gx + 16:.1f}" y="{gy + 18:.1f}" font-size="11.5" font-weight="600" '
            f'letter-spacing="0.6" fill="{group_colors.get(gid) or theme["group_text"]}">'
            f'{escape(str(group_labels.get(gid, gid)).upper())}</text>'
        )

    # edges
    for edge in edges:
        color = edge.get("color") or theme["edge"]
        d, p0, c1, c2, p3 = _edge_path(pos[edge["src"]], pos[edge["dst"]], horizontal)
        dash = ' stroke-dasharray="7 6"' if edge.get("dashed") else ""
        arrow = "" if edge.get("arrow") is False else f' marker-end="url(#{marker_id[color]})"'
        out.append(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.7" '
            f'stroke-linecap="round"{dash}{arrow}/>'
        )
        label = str(edge.get("label") or "").strip()
        if label:
            mx, my = _bezier_mid(p0, c1, c2, p3)
            pill_w = 7.2 * len(label) + 14
            out.append(
                f'<rect x="{mx - pill_w / 2:.1f}" y="{my - 10:.1f}" width="{pill_w:.1f}" '
                f'height="19" rx="9.5" fill="{theme["edge_pill"]}" stroke="{color}" '
                f'stroke-opacity="0.35"/>'
            )
            out.append(
                f'<text x="{mx:.1f}" y="{my + 4:.1f}" text-anchor="middle" font-size="11.5" '
                f'fill="{theme["edge_text"]}">{escape(label)}</text>'
            )

    # nodes
    for index, node in enumerate(nodes):
        x, y = pos[node["id"]]
        accent = node.get("accent") or ""
        stroke = accent if accent else theme["card_stroke"]
        out.append(
            f'<g filter="url(#cardshadow)"><rect x="{x:.1f}" y="{y:.1f}" width="{NODE_W}" '
            f'height="{NODE_H}" rx="14" fill="{theme["card"]}" stroke="{stroke}" '
            f'stroke-width="{1.6 if accent else 1.2}"/></g>'
        )
        uri = _icon_uri(node.get("icon"), icons)
        label = str(node.get("label") or node["id"])
        sub = str(node.get("sub") or "").strip()
        cx = x + NODE_W / 2

        if uri:
            out.append(
                f'<image x="{cx - ICON / 2:.1f}" y="{y + 14:.1f}" width="{ICON}" '
                f'height="{ICON}" href="{uri}" xlink:href="{uri}" '
                f'preserveAspectRatio="xMidYMid meet"/>'
            )
            text_top = y + 76
        else:
            color = accent or ACCENTS[index % len(ACCENTS)]
            initials = "".join(w[0] for w in re.split(r"[\s_-]+", label)[:2] if w).upper() or "?"
            out.append(
                f'<circle cx="{cx:.1f}" cy="{y + 36:.1f}" r="21" fill="{color}" '
                f'fill-opacity="0.13" stroke="{color}" stroke-opacity="0.4"/>'
                f'<text x="{cx:.1f}" y="{y + 41:.1f}" text-anchor="middle" font-size="14" '
                f'font-weight="650" fill="{color}">{escape(initials)}</text>'
            )
            text_top = y + 76

        lines = _wrap(label, 22, 1 if sub else 2)
        for li, line in enumerate(lines):
            out.append(
                f'<text x="{cx:.1f}" y="{text_top + li * 15:.1f}" text-anchor="middle" '
                f'font-size="13.5" font-weight="600" fill="{theme["text"]}">'
                f'{escape(line)}</text>'
            )
        if sub:
            out.append(
                f'<text x="{cx:.1f}" y="{text_top + 17:.1f}" text-anchor="middle" '
                f'font-size="11" fill="{theme["sub"]}">'
                f'{escape(_wrap(sub, 26, 1)[0])}</text>'
            )

    out.append("</svg>")
    return "".join(out)


def svg_data_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


# --- quick text DSL -------------------------------------------------------

LINE_RE = re.compile(r"^\s*(?P<src>.+?)\s*(?P<arrow>\.\.>|-->|->|=>)\s*"
                     r"(?P<dst>[^:]+?)\s*(?::\s*(?P<label>.*))?$")


def _match_icon(node_id: str, icons: Dict[str, dict]) -> str:
    """Exact id match, else an icon whose id is a hyphen-prefix of it (or vice versa)."""
    if node_id in icons:
        return node_id
    if len(node_id) < 3:
        return ""
    for candidate in icons:
        if candidate.startswith(node_id + "-") or node_id.startswith(candidate + "-"):
            return candidate
    return ""


def parse_text(text: str, spec: Dict[str, Any], icons: Optional[Dict[str, dict]] = None) -> Dict[str, Any]:
    """Parse lines like `web -> api : REST` (or a bare `redis`) into the spec.

    Node ids that match a saved icon id get that icon attached automatically.
    """
    icons = icons if icons is not None else store.icon_map()
    known = {n["id"]: n for n in spec["nodes"]}
    pairs = {(e["src"], e["dst"]) for e in spec["edges"]}

    def ensure(raw: str) -> str:
        name = raw.strip()
        node_id = store.slugify(name)
        if node_id and node_id not in known:
            node = {
                "id": node_id, "label": name, "sub": "", "group": "", "col": None,
                "accent": "", "icon": _match_icon(node_id, icons),
            }
            spec["nodes"].append(node)
            known[node_id] = node
        return node_id

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = LINE_RE.match(line)
        if not match:
            ensure(line)
            continue
        src = ensure(match.group("src"))
        dst = ensure(match.group("dst"))
        if (src, dst) not in pairs:
            spec["edges"].append({
                "src": src,
                "dst": dst,
                "label": (match.group("label") or "").strip(),
                "dashed": match.group("arrow") == "..>",
            })
            pairs.add((src, dst))
    return spec
