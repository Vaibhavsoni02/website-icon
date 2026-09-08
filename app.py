"""Icon Studio - find icons, keep them in a local library, draw diagrams with them."""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from iconlib import diagram, ghstore, render, repo, sources, store

st.set_page_config(page_title="Icon Studio", page_icon="🧩", layout="wide")

# st.image lost `use_container_width` in favour of `width="stretch"` in 1.49.
_VERSION = tuple(int(p) for p in st.__version__.split(".")[:2] if p.isdigit())
FILL = {"width": "stretch"} if _VERSION >= (1, 49) else {"use_container_width": True}

STARTER_PACK = [
    "logos:aws", "logos:google-cloud", "logos:kubernetes", "logos:docker-icon",
    "logos:postgresql", "logos:redis", "logos:kafka-icon", "logos:snowflake-icon",
    "logos:python", "logos:react", "logos:github-icon", "logos:airflow-icon",
]

NODE_COLS = ["id", "label", "sub", "icon", "group", "col", "accent"]
EDGE_COLS = ["src", "dst", "label", "dashed", "color"]


# --- helpers --------------------------------------------------------------

def _text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def spec() -> Dict[str, Any]:
    if "spec" not in st.session_state:
        st.session_state.spec = diagram.blank_spec()
    return st.session_state.spec


def show_sync() -> None:
    """Surface the result of any GitHub mirroring the last action triggered."""
    for ok, message in store.drain_sync():
        st.toast(message, icon="☁️" if ok else "⚠️")
        if not ok:
            st.session_state.sync_error = message


def save_bytes(name: str, data: bytes, ext: str, source: str, ref: str, tags: List[str]) -> None:
    record = store.save_icon(name=name, data=data, ext=ext, source=source, ref=ref, tags=tags)
    st.toast(f"Saved **{record['id']}** → `icons/{record['file']}`", icon="✅")
    show_sync()


def add_node_from_icon(record: Dict[str, Any]) -> None:
    current = spec()
    if any(n["id"] == record["id"] for n in current["nodes"]):
        st.toast(f"{record['id']} is already on the canvas", icon="ℹ️")
        return
    current["nodes"].append({
        "id": record["id"], "label": record["name"], "sub": "",
        "icon": record["id"], "group": "", "col": None, "accent": "",
    })
    st.toast(f"Added **{record['name']}** to the diagram", icon="🧩")


def sync_editor_state() -> None:
    """Data editors keep their own widget state; nuke it when the spec changes underneath."""
    for key in ("nodes_editor", "edges_editor", "groups_editor"):
        st.session_state.pop(key, None)


# --- sidebar --------------------------------------------------------------

icons_all = store.list_icons()
with st.sidebar:
    st.markdown("### 🧩 Icon Studio")
    st.caption(f"`{store.ROOT.name}/`")
    st.metric("Icons in library", len(icons_all))
    st.metric("Nodes on canvas", len(spec()["nodes"]))
    st.divider()
    if ghstore.enabled():
        st.caption(f"☁️ syncing to `{ghstore.repo()}`")
        st.caption("Saves commit straight to GitHub.")
    elif repo.is_repo():
        pending = repo.pending_changes()
        st.caption(f"git · `{repo.branch() or 'main'}`")
        st.caption(f"{len(pending)} uncommitted change(s) in icons/diagrams")
    else:
        st.caption("git · not a repo yet (see the Repo tab)")
    if st.session_state.get("sync_error"):
        st.warning(st.session_state.sync_error, icon="⚠️")
    st.divider()
    st.caption(
        "Sources: [Iconify](https://iconify.design) · "
        "[twenty-icons](https://github.com/twentyhq/favicon)"
    )

# A segmented control rather than st.tabs: tabs reset to the first one on every
# st.rerun(), which would bounce you out of the canvas each time you save.
VIEWS = ["🔎 Find icons", "🗂 Library", "🧩 Diagram", "⬆️ Repo"]
view = st.segmented_control("View", VIEWS, default=VIEWS[0], key="view",
                            label_visibility="collapsed") or st.session_state.get(
    "last_view", VIEWS[0])
st.session_state.last_view = view


# --- 1. find icons --------------------------------------------------------

if view == VIEWS[0]:
    mode = st.radio(
        "Source",
        ["Iconify search", "Company logo by domain", "URL or upload"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if mode == "Iconify search":
        c1, c2, c3 = st.columns([3, 2, 1])
        query = c1.text_input("Search", placeholder="kafka, database, user, aws lambda…",
                              key="iconify_q")
        prefixes = c2.multiselect("Icon sets (blank = all)", sources.LOGO_SETS,
                                  default=[], key="iconify_sets")
        limit = c3.slider("Results", 16, 96, 40, step=8)
        tags_in = st.text_input("Tags to apply when saving", value="",
                                placeholder="infra, gcp, v2", key="iconify_tags")

        if query.strip():
            try:
                results = sources.iconify_search(query, limit=limit, prefixes=prefixes or None)
            except sources.SourceError as exc:
                results = []
                st.error(str(exc))
            if not results:
                st.info("No icons matched. Try a shorter word, or clear the icon-set filter.")
            else:
                st.caption(f"{len(results)} results · click **Save** to add to your library")
                per_row = 8
                for start in range(0, len(results), per_row):
                    cols = st.columns(per_row)
                    for col, name in zip(cols, results[start:start + per_row]):
                        with col:
                            st.markdown(
                                render.icon_tile(sources.iconify_preview_url(name, 44), name),
                                unsafe_allow_html=True,
                            )
                            if st.button("Save", key=f"sv-{name}", use_container_width=True):
                                try:
                                    data, ext = sources.iconify_fetch(name, height=128)
                                    save_bytes(
                                        sources.suggest_name("iconify", name), data, ext,
                                        "iconify", name,
                                        [t for t in tags_in.split(",")] + [name.split(":")[0]],
                                    )
                                    st.rerun()
                                except sources.SourceError as exc:
                                    st.error(str(exc))
        else:
            st.info("Type a keyword above. Iconify covers 200k+ icons — brand logos "
                    "(`logos:`, `simple-icons:`), UI glyphs (`mdi:`, `tabler:`), cloud "
                    "provider sets and more.")

    elif mode == "Company logo by domain":
        st.caption("Powered by [twentyhq/favicon](https://github.com/twentyhq/favicon) — "
                   "any company's logo from its domain.")
        c1, c2 = st.columns([3, 1])
        domains_raw = c1.text_area(
            "Domains (one per line)", height=110,
            placeholder="stripe.com\nnotion.so\nhttps://www.datadoghq.com/pricing",
            key="dom_input",
        )
        size = c2.selectbox("Size", sources.TWENTY_SIZES, index=4)
        tags_in = c2.text_input("Tags", value="company", key="dom_tags")

        if c2.button("Fetch", type="primary", use_container_width=True):
            fetched, failed = [], []
            for line in domains_raw.splitlines():
                if not line.strip():
                    continue
                try:
                    data, ext = sources.twenty_fetch(line, size=int(size))
                    fetched.append((sources.clean_domain(line), data, ext))
                except sources.SourceError as exc:
                    failed.append(f"{line.strip()} — {exc}")
            st.session_state.domain_hits = fetched
            st.session_state.domain_fails = failed

        for problem in st.session_state.get("domain_fails", []):
            st.warning(problem)

        hits = st.session_state.get("domain_hits", [])
        if hits:
            st.divider()
            cols = st.columns(min(6, len(hits)))
            for i, (domain, data, ext) in enumerate(hits):
                with cols[i % len(cols)]:
                    st.image(data, width=72)
                    st.caption(domain)
                    if st.button("Save", key=f"dsv-{domain}", use_container_width=True):
                        save_bytes(sources.suggest_name("twenty-icons", domain), data, ext,
                                   "twenty-icons", domain,
                                   [t for t in tags_in.split(",")] + [domain])
                        st.rerun()
            if st.button("Save all", type="primary"):
                for domain, data, ext in hits:
                    save_bytes(sources.suggest_name("twenty-icons", domain), data, ext,
                               "twenty-icons", domain,
                               [t for t in tags_in.split(",")] + [domain])
                st.rerun()

    else:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**From a URL**")
            url = st.text_input("Image URL", placeholder="https://…/logo.svg", key="url_in")
            url_name = st.text_input("Name", value="", placeholder="auto from filename",
                                     key="url_name")
            url_tags = st.text_input("Tags", value="", key="url_tags")
            if st.button("Fetch & save", type="primary", disabled=not url.strip()):
                try:
                    data, ext = sources.url_fetch(url.strip())
                    save_bytes(url_name.strip() or sources.suggest_name("url", url),
                               data, ext, "url", url.strip(), url_tags.split(","))
                    st.rerun()
                except sources.SourceError as exc:
                    st.error(str(exc))
        with c2:
            st.markdown("**Upload files**")
            uploads = st.file_uploader(
                "SVG / PNG / JPG / GIF / WEBP / ICO",
                type=["svg", "png", "jpg", "jpeg", "gif", "webp", "ico"],
                accept_multiple_files=True, key="uploader",
            )
            up_tags = st.text_input("Tags", value="", key="up_tags")
            if uploads and st.button("Save uploads", type="primary"):
                for up in uploads:
                    raw = up.getvalue()
                    ext = sources.sniff_ext(up.name, raw)
                    save_bytes(up.name.rsplit(".", 1)[0], raw, ext, "upload", up.name,
                               up_tags.split(","))
                st.rerun()


# --- 2. library -----------------------------------------------------------

if view == VIEWS[1]:
    if not icons_all:
        st.info("Your library is empty.")
        if st.button("⚡ Grab a starter pack (12 common infra icons)", type="primary"):
            progress = st.progress(0.0)
            for i, name in enumerate(STARTER_PACK, 1):
                try:
                    data, ext = sources.iconify_fetch(name, height=128)
                    store.save_icon(sources.suggest_name("iconify", name), data, ext,
                                    "iconify", name, ["starter", name.split(":")[0]])
                except sources.SourceError:
                    pass
                progress.progress(i / len(STARTER_PACK))
            st.rerun()
    else:
        c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
        needle = c1.text_input("Filter", placeholder="name or tag", key="lib_q")
        tag_pick = c2.selectbox("Tag", [""] + store.all_tags(), key="lib_tag")
        per_row = c3.slider("Per row", 3, 10, 6, key="lib_cols")
        c4.metric("Shown", len(store.list_icons(needle, tag_pick)))

        shown = store.list_icons(needle, tag_pick)
        for start in range(0, len(shown), per_row):
            cols = st.columns(per_row)
            for col, record in zip(cols, shown[start:start + per_row]):
                uri = store.data_uri(record)
                with col:
                    st.markdown(render.icon_tile(uri, record["id"], size=52),
                                unsafe_allow_html=True)
                    if st.button("＋ Add", key=f"add-{record['id']}",
                                 help="Add to the diagram canvas",
                                 use_container_width=True):
                        add_node_from_icon(record)
                        sync_editor_state()
                        st.rerun()
                    with st.expander("Copy"):
                        components.html(
                            render.copy_png_widget(uri, record["id"], png_size=512),
                            height=46,
                        )
                        st.caption("Path")
                        st.code(store.rel_path(record), language=None)
                        st.caption("Markdown")
                        st.code(f"![{record['name']}]({store.rel_path(record)})", language=None)
                        st.caption("HTML")
                        st.code(f'<img src="{store.rel_path(record)}" width="48" '
                                f'alt="{record["name"]}" />', language="html")
                        with st.popover("Data URI"):
                            st.code(uri, language=None)
                        st.download_button(
                            "Download file", data=store.icon_bytes(record),
                            file_name=record["file"], mime=store.mime_of(record),
                            key=f"dl-{record['id']}", use_container_width=True,
                        )
                        new_tags = st.text_input(
                            "Tags", value=", ".join(record.get("tags", [])),
                            key=f"tg-{record['id']}",
                        )
                        b1, b2 = st.columns(2)
                        if b1.button("Update", key=f"up-{record['id']}",
                                     use_container_width=True):
                            store.update_icon(record["id"], tags=new_tags.split(","))
                            st.rerun()
                        if b2.button("Delete", key=f"del-{record['id']}",
                                     use_container_width=True):
                            store.delete_icon(record["id"])
                            st.rerun()
                        st.caption(f"{record['source']} · {record.get('ref', '')} · "
                                   f"{record['bytes']} B")


# --- 3. diagram -----------------------------------------------------------

def nodes_to_df(current: Dict[str, Any]) -> pd.DataFrame:
    rows = [{c: n.get(c) for c in NODE_COLS} for n in current["nodes"]]
    return pd.DataFrame(rows, columns=NODE_COLS)


def df_to_nodes(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    out, seen = [], set()
    for _, row in frame.iterrows():
        node_id = store.slugify(_text(row.get("id")))
        if not _text(row.get("id")) or node_id in seen:
            continue
        seen.add(node_id)
        lane = row.get("col")
        out.append({
            "id": node_id,
            "label": _text(row.get("label")) or node_id,
            "sub": _text(row.get("sub")),
            "icon": _text(row.get("icon")),
            "group": _text(row.get("group")),
            "col": None if lane is None or pd.isna(lane) else int(lane),
            "accent": _text(row.get("accent")),
        })
    return out


def edges_to_df(current: Dict[str, Any]) -> pd.DataFrame:
    rows = [{c: e.get(c) for c in EDGE_COLS} for e in current["edges"]]
    return pd.DataFrame(rows, columns=EDGE_COLS)


def df_to_edges(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    out = []
    for _, row in frame.iterrows():
        src, dst = _text(row.get("src")), _text(row.get("dst"))
        if not src or not dst:
            continue
        out.append({
            "src": src, "dst": dst, "label": _text(row.get("label")),
            "dashed": bool(row.get("dashed")) if not pd.isna(row.get("dashed")) else False,
            "color": _text(row.get("color")),
        })
    return out


if view == VIEWS[2]:
    current = spec()
    preview_box = st.container()

    top = st.columns([2, 1, 1, 1, 1])
    current["title"] = top[0].text_input("Title", value=current.get("title", ""),
                                         placeholder="Payments data flow")
    current["direction"] = top[1].selectbox(
        "Flow", ["LR", "TB"], index=0 if current.get("direction", "LR") == "LR" else 1,
        format_func=lambda v: "Left → right" if v == "LR" else "Top ↓ down",
    )
    current["theme"] = top[2].selectbox(
        "Theme", ["light", "dark"], index=0 if current.get("theme") == "light" else 1)
    diagram_name = top[3].text_input("Save as", value=st.session_state.get("dname", "untitled"),
                                     key="dname")
    saved = store.list_diagrams()
    load_pick = top[4].selectbox("Open saved", [""] + saved, key="dload")

    quick = st.expander("⚡ Quick build from text", expanded=not current["nodes"])
    with quick:
        st.caption("One relation per line: `client -> api : REST`. Use `..>` for a dashed "
                   "edge. A bare word just adds a node. Ids matching a saved icon pick it "
                   "up automatically.")
        text = st.text_area(
            "Relations", height=130, key="dsl",
            placeholder="web -> api : REST\napi -> postgresql : SQL\napi -> redis : cache\n"
                        "api ..> kafka : events",
        )
        qc1, qc2, qc3 = st.columns([1, 1, 4])
        if qc1.button("Apply", type="primary", use_container_width=True):
            diagram.parse_text(text, current)
            sync_editor_state()
            st.rerun()
        if qc2.button("Clear canvas", use_container_width=True):
            st.session_state.spec = diagram.blank_spec()
            sync_editor_state()
            st.rerun()

    if load_pick and st.session_state.get("loaded_name") != load_pick:
        st.session_state.spec = store.load_diagram(load_pick)
        st.session_state.loaded_name = load_pick
        sync_editor_state()
        st.rerun()

    icon_ids = [""] + sorted(store.icon_map())
    left, right = st.columns(2)
    with left:
        st.markdown("**Nodes**")
        edited_nodes = st.data_editor(
            nodes_to_df(current), num_rows="dynamic", use_container_width=True,
            key="nodes_editor", hide_index=True,
            column_config={
                "id": st.column_config.TextColumn("id", help="Unique, used by edges", width="small"),
                "label": st.column_config.TextColumn("label"),
                "sub": st.column_config.TextColumn("subtitle", width="small"),
                "icon": st.column_config.SelectboxColumn("icon", options=icon_ids, width="small"),
                "group": st.column_config.TextColumn("group", width="small"),
                "col": st.column_config.NumberColumn("lane", help="Pin to a column/row",
                                                     min_value=0, step=1, width="small"),
                "accent": st.column_config.TextColumn("accent", help="#hex border", width="small"),
            },
        )
        current["nodes"] = df_to_nodes(edited_nodes)

    with right:
        st.markdown("**Edges**")
        node_ids = [n["id"] for n in current["nodes"]]
        edited_edges = st.data_editor(
            edges_to_df(current), num_rows="dynamic", use_container_width=True,
            key="edges_editor", hide_index=True,
            column_config={
                "src": st.column_config.SelectboxColumn("from", options=node_ids),
                "dst": st.column_config.SelectboxColumn("to", options=node_ids),
                "label": st.column_config.TextColumn("label"),
                "dashed": st.column_config.CheckboxColumn("dashed", width="small"),
                "color": st.column_config.TextColumn("color", width="small"),
            },
        )
        current["edges"] = df_to_edges(edited_edges)

        used_groups = sorted({n["group"] for n in current["nodes"] if n["group"]})
        if used_groups:
            existing = {g["id"]: g for g in current.get("groups", [])}
            st.markdown("**Groups**")
            group_df = pd.DataFrame(
                [{"id": g, "label": existing.get(g, {}).get("label", g),
                  "color": existing.get(g, {}).get("color", "")} for g in used_groups],
                columns=["id", "label", "color"],
            )
            edited_groups = st.data_editor(
                group_df, use_container_width=True, key="groups_editor", hide_index=True,
                disabled=["id"],
                column_config={"color": st.column_config.TextColumn("color", width="small")},
            )
            current["groups"] = [
                {"id": _text(r["id"]), "label": _text(r["label"]) or _text(r["id"]),
                 "color": _text(r["color"])}
                for _, r in edited_groups.iterrows() if _text(r["id"])
            ]
        else:
            current["groups"] = []

    svg = diagram.render_svg(current)
    with preview_box:
        st.image(svg, **FILL)
        e1, e2, e3, e4 = st.columns([2, 2, 2, 3])
        e1.download_button("⬇ SVG", data=svg, file_name=f"{store.slugify(diagram_name)}.svg",
                           mime="image/svg+xml", use_container_width=True)
        with e2:
            components.html(
                render.copy_png_widget(
                    diagram.svg_data_uri(svg), store.slugify(diagram_name), png_size=2200,
                    label="Copy PNG", show_download=True,
                    background="#0e1320" if current["theme"] == "dark" else "#ffffff",
                ),
                height=46,
            )
        if e3.button("💾 Save to repo", type="primary", use_container_width=True,
                     disabled=not current["nodes"]):
            path = store.save_diagram_bundle(diagram_name, current, svg)
            st.session_state.loaded_name = store.slugify(diagram_name)
            st.toast(f"Saved `diagrams/{store.slugify(diagram_name)}.json` and "
                     f"`exports/{path.name}`", icon="💾")
            show_sync()
        if saved and e4.button("🗑 Delete saved diagram", use_container_width=True,
                               disabled=not load_pick):
            store.delete_diagram(load_pick)
            st.session_state.loaded_name = None
            st.rerun()


# --- 4. repo --------------------------------------------------------------

if view == VIEWS[3]:
    st.markdown("#### ☁️ GitHub sync")
    if ghstore.enabled():
        st.success(f"Enabled — every save commits to **{ghstore.repo()}** "
                   f"on `{ghstore.branch()}`.")
        if st.button("Test connection"):
            try:
                info = ghstore.check()
                st.success(f"Write access confirmed to **{info['repo']}** "
                           f"(branch `{info['branch']}`, "
                           f"{'private' if info['private'] else 'public'}).")
                st.session_state.pop("sync_error", None)
            except ghstore.GitHubError as exc:
                st.error(str(exc))
    else:
        st.info(
            "Not configured — saves only touch the local disk. That's fine when you "
            "run this on your own machine, but on Streamlit Cloud the disk is wiped "
            "on every reboot. To persist there, add these to the app's **Secrets**:"
        )
        st.code(
            'GITHUB_TOKEN = "github_pat_…"\n'
            'GITHUB_REPO = "owner/repo"\n'
            'GITHUB_BRANCH = "main"',
            language="toml",
        )
        st.caption("Use a fine-grained PAT limited to that one repo, with "
                   "**Contents: read and write**. Never commit it.")

    st.divider()
    st.markdown("#### 🖥 Local git")
    st.markdown(f"Repo root: `{store.ROOT}`")
    if not repo.is_repo():
        st.warning("This folder isn't a git repository yet.")
        if st.button("git init", type="primary"):
            code, out = repo.init()
            st.code(out or f"exit {code}")
            st.rerun()
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Branch", repo.branch() or "-")
        c2.metric("Icons", len(store.list_icons()))
        c3.metric("Diagrams", len(store.list_diagrams()))

        origin = repo.remote_url()
        if origin:
            st.caption(f"origin → {origin}")
        else:
            st.info("No `origin` remote. Add one to push:")
            st.code("git remote add origin git@github.com:<you>/<repo>.git", language="bash")

        status = repo.status()
        st.text_area("git status", value=status or "clean", height=150, disabled=True)

        message = st.text_input(
            "Commit message",
            value=f"Add {len(store.list_icons())} icons and "
                  f"{len(store.list_diagrams())} diagram(s)",
        )
        b1, b2 = st.columns(2)
        if b1.button("Commit icons, diagrams & exports", type="primary",
                     use_container_width=True):
            ok, out = repo.commit(message)
            (st.success if ok else st.warning)(out or "done")
        if b2.button("Push", use_container_width=True, disabled=not origin):
            ok, out = repo.push()
            (st.success if ok else st.error)(out or "done")
