# 🧩 Icon Studio

A local Streamlit tool for grabbing icons once, keeping them in a **version-controlled
library**, and wiring them into clean architecture diagrams.

```bash
./run.sh
```

First run creates `.venv` and installs dependencies; then the app opens at
<http://localhost:8501>.

---

## What it does

### 🔎 Find icons

| Source | Good for | Notes |
| --- | --- | --- |
| **Iconify search** | Everything — 200k+ icons | Brand logos (`logos:`, `simple-icons:`, `devicon:`), UI glyphs (`mdi:`, `tabler:`, `lucide:`), cloud provider sets. Saved as SVG. |
| **Company logo by domain** | Any company, by its website | Powered by [twentyhq/favicon](https://github.com/twentyhq/favicon) — `stripe.com` → the Stripe logo. Paste full URLs, they get cleaned to a domain. |
| **URL or upload** | Your own assets | SVG / PNG / JPG / GIF / WEBP / ICO. |

Everything you save lands in `icons/` and is registered in `icons/manifest.json`.

### 🗂 Library

Each icon gets a card with:

- **Copy image** — puts a rendered PNG on your clipboard, ready to paste straight into
  Slack, Google Docs, Figma, Notion, a deck…
- **Download PNG** — same render, as a file.
- Copy-ready snippets: repo path, Markdown, `<img>` HTML, and a self-contained data URI.
- Tag editing, delete, and **＋ Diagram** to drop it onto the canvas.

### 🧩 Diagram

Build a diagram from your saved icons and export a **self-contained SVG** — every icon is
embedded as a data URI, so the file works anywhere with no external requests.

Fastest way in is the **Quick build from text** box:

```
web -> api : REST
api -> postgresql : SQL
api -> redis : cache
api ..> kafka : events
```

- `->` solid edge, `..>` dashed edge, `: text` labels the edge, a bare word adds a node.
- Node ids that match a saved icon id pick that icon up automatically.

Then fine-tune in the two tables:

| Nodes | |
| --- | --- |
| `id` | unique, referenced by edges |
| `label` / `subtitle` | card text |
| `icon` | pick from your library |
| `group` | draws a labelled container around members |
| `lane` | pin to a specific column (row in top-down mode) — otherwise inferred from the edges |
| `accent` | `#hex` border colour |

Layout is automatic: nodes are layered by longest path through the edges, and each group
gets its own band of rows so a container never swallows a node that isn't a member.

Export: **⬇ SVG**, **Copy PNG** (clipboard, 2200px), or **💾 Save to repo**, which writes
`diagrams/<name>.json` (re-editable) and `exports/<name>.svg`.

### ⬆️ Repo

Two ways to get saves into the repo, depending on where the app is running.

**Local git** — `git status`, one-click commit of `icons/`, `diagrams/` and `exports/`,
and push. To push somewhere, add a remote first:

```bash
git remote add origin git@github.com:<you>/<repo>.git
```

**GitHub sync** — for deployments with an ephemeral disk (Streamlit Community Cloud wipes
it on every reboot). With a token configured, each save commits straight to the repo over
the API, so the library survives restarts. Configure via environment variables or
Streamlit secrets:

```toml
GITHUB_TOKEN = "github_pat_…"
GITHUB_REPO = "owner/repo"
GITHUB_BRANCH = "main"
```

Use a **fine-grained PAT scoped to that one repository** with *Contents: read and write* —
nothing else. On Streamlit Cloud it goes in **Manage app → Settings → Secrets**, never in
a GitHub repo secret (those are only visible to Actions) and never in a committed file.
`.streamlit/secrets.toml` is gitignored; see `.streamlit/secrets.toml.example`.

When enabled, an icon and the updated manifest land in a *single* commit, and the Repo tab
gains a **Test connection** button that verifies write access. A sync failure never loses
the local write — it surfaces as a warning and the file is still on disk.

---

## Layout

```
icons/            saved icons + manifest.json   ← committed
diagrams/         diagram specs (JSON)          ← committed
exports/          rendered SVGs                 ← committed
iconlib/
  sources.py      Iconify / twenty-icons / URL fetching
  store.py        library on disk + manifest
  ghstore.py      optional GitHub API mirror (for ephemeral hosts)
  diagram.py      layout + SVG renderer + text DSL
  render.py       clipboard/download widgets
  repo.py         git helpers
app.py            the Streamlit UI
```

## Using saved icons outside the app

```markdown
![Postgres](icons/postgresql.svg)
```

```python
from iconlib import store
uri = store.data_uri(store.icon_map()["postgresql"])   # data:image/svg+xml;base64,…
```

```python
from iconlib import diagram
spec = diagram.blank_spec()
diagram.parse_text("api -> postgresql : SQL", spec)
open("out.svg", "w").write(diagram.render_svg(spec))
```

## Notes

- **Licensing** is not handled for you. Iconify sets carry their own licences (each icon's
  set is recorded in its tags), and company logos are trademarks — fine for internal
  architecture diagrams, check before shipping them in marketing material.
- **Copy image** needs a secure context; `localhost` qualifies, so it works out of the box.
