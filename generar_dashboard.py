"""
generar_dashboard.py
--------------------
Lee la base de datos GenAI Radar desde Notion y genera
un archivo dashboard.html local con gráficas y estadísticas.

No requiere Notion Plus ni configurar vistas manualmente.
Abre dashboard.html en el navegador para ver el resultado.

Requiere en .env:
  NOTION_TOKEN=...
  NOTION_DB_ID=...
"""

import os
import webbrowser
import requests
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

from dotenv import load_dotenv

# ----------------------------
# Config
# ----------------------------
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DB_ID        = os.getenv("NOTION_DB_ID")

if not NOTION_TOKEN or not DB_ID:
    raise SystemExit("Faltan variables de entorno: NOTION_TOKEN y/o NOTION_DB_ID")

NOTION_HEADERS = {
    "Authorization":  f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type":   "application/json",
}
OUTPUT = BASE_DIR / "dashboard.html"


# ----------------------------
# Lectura de Notion (requests directo, sin SDK)
# ----------------------------
def fetch_all_pages() -> list[dict]:
    """Descarga todos los registros de la base de datos vía API REST."""
    pages  = []
    cursor = None
    url    = f"https://api.notion.com/v1/databases/{DB_ID}/query"

    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor

        resp = requests.post(url, headers=NOTION_HEADERS, json=body, timeout=30)
        if resp.status_code != 200:
            raise SystemExit(f"Error Notion API: {resp.status_code} — {resp.text[:300]}")

        data = resp.json()
        pages.extend(data.get("results", []))

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    print(f"  → {len(pages)} registros descargados de Notion")
    return pages


def extract(page: dict) -> dict:
    """Extrae los campos relevantes de un registro Notion."""
    props = page.get("properties", {})

    def select(key):
        v = props.get(key, {}).get("select")
        return v.get("name", "") if v else ""

    def date_val(key):
        v = props.get(key, {}).get("date")
        return v.get("start", "") if v else ""

    def title_val(key):
        v = props.get(key, {}).get("title", [])
        return v[0].get("plain_text", "") if v else ""

    def checkbox_val(key):
        return props.get(key, {}).get("checkbox", False)

    created  = page.get("created_time", "")
    date_str = date_val("Date") or created[:10]

    return {
        "name":      title_val("Name"),
        "category":  select("Category"),
        "ecosystem": select("Ecosystem"),
        "source":    select("Source"),
        "status":    select("Status"),
        "priority":  select("Priority"),
        "signal":    checkbox_val("Signal"),
        "date":      date_str,
        "week":      date_to_week(date_str),
    }


def date_to_week(date_str: str) -> str:
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%Y-W%V")
    except Exception:
        return "N/A"


# ----------------------------
# Agregacion
# ----------------------------
def aggregate(records: list[dict]) -> dict:
    totals = {
        "total":     len(records),
        "signal":    sum(1 for r in records if r["signal"]),
        "to_review": sum(1 for r in records if r["status"] == "To review"),
        "high_prio": sum(1 for r in records if r["priority"] in ("High", "Strategic")),
    }

    by_category  = defaultdict(int)
    by_ecosystem = defaultdict(int)
    by_source    = defaultdict(int)
    by_status    = defaultdict(int)
    by_priority  = defaultdict(int)
    by_week      = defaultdict(int)

    for r in records:
        by_category[r["category"]   or "Sin categoria"]  += 1
        by_ecosystem[r["ecosystem"] or "Sin ecosistema"] += 1
        by_source[r["source"]       or "Sin fuente"]     += 1
        by_status[r["status"]       or "Sin estado"]     += 1
        by_priority[r["priority"]   or "Sin prioridad"]  += 1
        if r["week"] != "N/A":
            by_week[r["week"]] += 1

    weeks_sorted = sorted(by_week.keys())[-8:]
    weeks_data   = {w: by_week[w] for w in weeks_sorted}

    return {
        "totals":       totals,
        "by_category":  dict(sorted(by_category.items(),  key=lambda x: -x[1])),
        "by_ecosystem": dict(sorted(by_ecosystem.items(), key=lambda x: -x[1])),
        "by_source":    dict(sorted(by_source.items(),    key=lambda x: -x[1])),
        "by_status":    dict(sorted(by_status.items(),    key=lambda x: -x[1])),
        "by_priority":  dict(sorted(by_priority.items(),  key=lambda x: -x[1])),
        "by_week":      weeks_data,
    }


# ----------------------------
# Generacion HTML
# ----------------------------
CATEGORY_COLORS = {
    "Generacion":      "#6366f1",
    "Control":         "#0ea5e9",
    "Motion":          "#f59e0b",
    "LoRA / Adapter":  "#ec4899",
    "Postproceso":     "#10b981",
    "Workflow / Node": "#8b5cf6",
    "Tooling":         "#64748b",
    "Conocimiento":    "#f97316",
}

ECOSYSTEM_COLORS = {
    "Flux":    "#a3a3a3",
    "Wan":     "#dc2626",
    "Qwen":    "#7c3aed",
    "SDXL":    "#2563eb",
    "SD 1.5":  "#16a34a",
    "ComfyUI": "#d97706",
    "Multi":   "#64748b",
}

SOURCE_COLORS = {
    "GitHub":       "#6366f1",
    "HuggingFace":  "#f59e0b",
    "Civitai":      "#0ea5e9",
    "Blog":         "#10b981",
    "Docs":         "#64748b",
    "OpenModelDB":  "#7c3aed",
}

PRIORITY_COLORS = {
    "Strategic": "#dc2626",
    "High":      "#f97316",
    "Medium":    "#eab308",
    "Low":       "#94a3b8",
}

_PALETTE = ["#6366f1", "#0ea5e9", "#f59e0b", "#ec4899", "#10b981",
            "#8b5cf6", "#64748b", "#f97316", "#dc2626", "#16a34a"]


def color_for(group: str, name: str) -> str:
    mapping = {
        "category":  CATEGORY_COLORS,
        "ecosystem": ECOSYSTEM_COLORS,
        "source":    SOURCE_COLORS,
        "priority":  PRIORITY_COLORS,
    }
    return mapping.get(group, {}).get(name, _PALETTE[hash(name) % len(_PALETTE)])


def bar_chart(data: dict, group: str) -> str:
    if not data:
        return "<p class='empty'>Sin datos</p>"
    max_v = max(data.values()) or 1
    rows  = ""
    for name, count in data.items():
        pct = int(count / max_v * 100)
        col = color_for(group, name)
        rows += (
            f'<div class="bar-row">'
            f'<span class="bar-label" title="{name}">{name}</span>'
            f'<div class="bar-track">'
            f'<div class="bar-bg">'
            f'<div class="bar-fill" style="width:{pct}%;background:{col}"></div>'
            f'</div>'
            f'<span class="bar-count">{count}</span>'
            f'</div></div>'
        )
    return f"<div class='chart'>{rows}</div>"


def line_chart(data: dict) -> str:
    if len(data) < 2:
        return "<p class='empty'>Pocas semanas de datos aun. Vuelve en unos dias.</p>"

    weeks  = list(data.keys())
    values = list(data.values())
    max_v  = max(values) or 1
    W, H, pad = 480, 130, 28

    pts = []
    for i, v in enumerate(values):
        x = pad + i * (W - pad * 2) / max(len(values) - 1, 1)
        y = H - pad - (v / max_v) * (H - pad * 2)
        pts.append((x, y, v, weeks[i]))

    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y, _, _ in pts)
    dots     = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#6366f1">'
        f'<title>{w}: {v}</title></circle>'
        for x, y, v, w in pts
    )
    labels = "".join(
        f'<text x="{x:.1f}" y="{H - 6}" font-size="9"'
        f' text-anchor="middle" fill="#64748b">{w[-3:]}</text>'
        for x, y, v, w in pts
    )
    return (
        f'<svg viewBox="0 0 {W} {H}" class="sparkline">'
        f'<polyline points="{polyline}" fill="none" stroke="#6366f1"'
        f' stroke-width="2.5" stroke-linejoin="round"/>'
        f'{dots}{labels}'
        f'</svg>'
    )


def stat_card(label: str, value, sub: str = "") -> str:
    sub_html = f"<small>{sub}</small>" if sub else ""
    return (
        f'<div class="stat-card">'
        f'<div class="stat-value">{value}</div>'
        f'<div class="stat-label">{label}</div>'
        f'{sub_html}</div>'
    )


def render_html(agg: dict, generated_at: str) -> str:
    t = agg["totals"]
    pct_signal = int(t["signal"] / t["total"] * 100) if t["total"] else 0

    cards = "".join([
        stat_card("Total registros",   t["total"]),
        stat_card("Con Signal",        t["signal"],    f"{pct_signal}% del total"),
        stat_card("Por revisar",       t["to_review"]),
        stat_card("Alta prioridad",    t["high_prio"], "High + Strategic"),
    ])

    css = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #0f172a; color: #e2e8f0; padding: 24px; }
h1   { font-size: 1.6rem; font-weight: 700; margin-bottom: 4px; }
.subtitle { color: #64748b; font-size: .85rem; margin-bottom: 28px; }
h2   { font-size: .95rem; font-weight: 600; margin-bottom: 14px; color: #cbd5e1; }
.stats { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 28px; }
.stat-card { background: #1e293b; border-radius: 10px; padding: 18px 22px;
             min-width: 130px; flex: 1; }
.stat-value { font-size: 2rem; font-weight: 700; color: #6366f1; }
.stat-label { font-size: .8rem; color: #94a3b8; margin-top: 4px; }
.stat-card small { display: block; color: #475569; font-size: .72rem; margin-top: 6px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; }
.card { background: #1e293b; border-radius: 10px; padding: 20px; min-width: 0; }
.chart { display: flex; flex-direction: column; gap: 8px; }
.bar-row { display: flex; align-items: center; gap: 8px; min-width: 0; }
.bar-label { flex: 0 0 110px; font-size: .78rem; color: #94a3b8;
             white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bar-track { flex: 1; min-width: 0; display: flex; align-items: center; gap: 6px; }
.bar-bg    { flex: 1; min-width: 0; background: #0f172a; border-radius: 4px;
             height: 16px; overflow: hidden; }
.bar-fill  { height: 100%; border-radius: 4px; max-width: 100%; }
.bar-count { flex: 0 0 auto; font-size: .78rem; color: #64748b; }
.sparkline { width: 100%; height: auto; display: block; }
.empty  { color: #475569; font-size: .82rem; padding: 8px 0; }
.footer { margin-top: 28px; color: #334155; font-size: .75rem; text-align: right; }
"""

    week_chart  = line_chart(agg["by_week"])
    cat_chart   = bar_chart(agg["by_category"],  "category")
    eco_chart   = bar_chart(agg["by_ecosystem"], "ecosystem")
    src_chart   = bar_chart(agg["by_source"],    "source")
    stat_chart  = bar_chart(agg["by_status"],    "status")
    prio_chart  = bar_chart(agg["by_priority"],  "priority")
    total       = t["total"]

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GenAI Radar - Dashboard</title>
<style>{css}</style>
</head>
<body>
<h1>GenAI Radar - Dashboard</h1>
<p class="subtitle">Generado el {generated_at} &middot; {total} registros en Notion</p>
<div class="stats">{cards}</div>
<div class="grid">
  <div class="card"><h2>Entradas por semana</h2>{week_chart}</div>
  <div class="card"><h2>Por categoria</h2>{cat_chart}</div>
  <div class="card"><h2>Por ecosistema</h2>{eco_chart}</div>
  <div class="card"><h2>Por fuente</h2>{src_chart}</div>
  <div class="card"><h2>Por estado</h2>{stat_chart}</div>
  <div class="card"><h2>Por prioridad</h2>{prio_chart}</div>
</div>
<p class="footer">GenAI Radar &middot; dashboard estatico generado localmente</p>
</body>
</html>"""


# ----------------------------
# Main
# ----------------------------
if __name__ == "__main__":
    print(f"\n{'='*50}")
    print(f"  GenAI Radar - Dashboard")
    print(f"{'='*50}\n")

    print("Descargando registros de Notion...")
    pages   = fetch_all_pages()
    records = [extract(p) for p in pages]

    print("Agregando datos...")
    agg = aggregate(records)

    generated_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    html = render_html(agg, generated_at)

    OUTPUT.write_text(html, encoding="utf-8")

    t = agg["totals"]
    print(f"\n  Dashboard generado: {OUTPUT.name}")
    print(f"\n  Total registros : {t['total']}")
    print(f"  Con Signal      : {t['signal']}")
    print(f"  Por revisar     : {t['to_review']}")
    print(f"  Alta prioridad  : {t['high_prio']}")

    print("\n  Categorias:")
    for k, v in list(agg["by_category"].items())[:6]:
        print(f"    {k:22s} {v}")

    print("\n  Ecosistemas:")
    for k, v in list(agg["by_ecosystem"].items())[:5]:
        print(f"    {k:22s} {v}")

    print("\n  Abriendo en el navegador...\n")
    webbrowser.open(OUTPUT.as_uri())
