"""
export/weekly_briefing.py
=========================
Генерира пълен интерактивен HTML дашборд за българската икономика.
"""
import html as _html
import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from config import LENS_BADGES_BG, LENS_NAMES_BG, MACRO_REGIMES, MODULE_WEIGHTS
from catalog.series import SERIES_CATALOG
from core.display import databrowser_url, is_stale, stale_note, verdict_sentence
from core.primitives import apply_transform


def _score_color(score) -> str:
    if score is None:
        return "#8892a4"
    for threshold, _, color in MACRO_REGIMES:
        if score >= threshold:
            return color
    return MACRO_REGIMES[-1][2]


def _fmt_score(score) -> str:
    return f"{score:.1f}" if score is not None else "—"


def _series_results(lens_reports: dict) -> dict:
    """{key: score dict} — плоският индекс на скорираните серии."""
    return {
        s["key"]: s
        for rep in lens_reports.values()
        for s in rep.get("series", [])
    }


def _display_series(snapshot: dict, key: str, spec: dict) -> pd.Series:
    """
    Серията както се ПОКАЗВА: с приложената каталожна трансформация.
    Дисплеят и скорингът трябва да гледат едно и също число.
    """
    if key not in snapshot or snapshot[key].empty:
        return pd.Series(dtype="float64")
    return apply_transform(snapshot[key], spec.get("transform", "level")).dropna()


def _compute_as_of(snapshot: dict) -> str | None:
    """Най-скорошното наблюдение измежду показваните серии (YYYY-MM)."""
    last_dates = []
    for key, spec in SERIES_CATALOG.items():
        s = _display_series(snapshot, key, spec)
        if not s.empty:
            last_dates.append(s.index[-1])
    if not last_dates:
        return None
    return max(last_dates).strftime("%Y-%m")


def _prep_chart_data(snapshot: dict) -> dict:
    chart_data = {}
    cutoff = pd.Timestamp.now() - pd.DateOffset(years=12)
    for key, spec in SERIES_CATALOG.items():
        if key not in snapshot or snapshot[key].empty:
            continue
        s_raw = snapshot[key]
        transform = spec.get("transform", "level")
        s = _display_series(snapshot, key, spec)
        if s.empty:
            continue
        s_recent = s[s.index >= cutoff]
        if s_recent.empty:
            continue
        entry = {
            "name": spec["name_bg"],
            "dates": [d.strftime("%Y-%m-%d") for d in s_recent.index],
            "values": [round(float(v), 4) for v in s_recent.values],
            "lens": spec["lens"][0] if spec.get("lens") else "growth",
            "is_rate": spec.get("is_rate", False),
        }
        if transform == "roll4q_mean":
            # Суровото тримесечие остава видимо като тънка прекъсната линия.
            raw_recent = s_raw.reindex(s_recent.index)
            entry["values_raw"] = [
                round(float(v), 4) if pd.notna(v) else None for v in raw_recent.values
            ]
        chart_data[key] = entry
    return chart_data


def generate_html(
    snapshot: dict,
    lens_reports: dict,
    composite,
    regime: dict,
    output_path: str,
):
    chart_data = _prep_chart_data(snapshot)
    as_of = _compute_as_of(snapshot)
    as_of_str = as_of if as_of else "няма данни"
    today = date.today()
    generated_str = datetime.now().strftime("%d.%m.%Y")

    module_scores = {lens: rep.get("score") for lens, rep in lens_reports.items()}
    results = _series_results(lens_reports)
    verdict = verdict_sentence(lens_reports)

    # ── Latest values table ──────────────────────────────────────────────────
    rows_html = ""
    for key, spec in SERIES_CATALOG.items():
        lens = spec["lens"][0] if spec.get("lens") else "growth"
        badge = LENS_BADGES_BG.get(lens, lens)
        hint = _html.escape(spec.get("narrative_hint", "") or "")
        url = databrowser_url(spec.get("id", ""))
        name_html = _html.escape(spec["name_bg"])
        if url:
            name_html = (
                f'<a href="{url}" target="_blank" rel="noopener" '
                f'onclick="event.stopPropagation()">{name_html}</a>'
            )
        name_cell = f'<td class="ind-name" title="{hint}">{name_html}</td>'

        if key not in snapshot or snapshot[key].empty:
            rows_html += f"""
            <tr>
                {name_cell}
                <td><span class="lens-badge lens-{lens}">{badge}</span></td>
                <td>—</td><td>—</td><td>—</td>
                <td style="color:#888">Липсват данни</td>
            </tr>"""
            continue
        s = _display_series(snapshot, key, spec)
        if s.empty:
            continue
        last_val = s.iloc[-1]
        last_ts = s.index[-1]
        last_date = last_ts.strftime("%Y-%m")
        schedule = spec.get("release_schedule", "monthly")
        if is_stale(last_ts, schedule, today):
            last_date = (
                f'<span class="stale" title="{_html.escape(stale_note(schedule))}">⚠</span> '
                f'{last_date}'
            )
        prev_val = s.iloc[-2] if len(s) > 1 else None
        delta = last_val - prev_val if prev_val is not None else None
        delta_str = ""
        delta_cls = ""
        if delta is not None:
            sign = "+" if delta > 0 else ""
            delta_cls = "pos" if delta > 0 else "neg" if delta < 0 else ""
            delta_str = f'{sign}{delta:.2f}'
        res = results.get(key, {})
        score_val = res.get("score")
        rows_html += f"""
            <tr onclick="showChart('{key}')" style="cursor:pointer">
                {name_cell}
                <td><span class="lens-badge lens-{lens}">{badge}</span></td>
                <td>{last_date}</td>
                <td><b>{last_val:.2f}</b></td>
                <td class="{delta_cls}">{delta_str}</td>
                <td style="color:{_score_color(score_val)}"><b>{_fmt_score(score_val)}</b></td>
            </tr>"""

    # ── Module score bars ────────────────────────────────────────────────────
    module_bars = ""
    for mod, score in module_scores.items():
        color = _score_color(score)
        name = LENS_NAMES_BG.get(mod, mod.capitalize())
        width = score if score is not None else 0.0
        module_bars += f"""
        <div class="mod-row">
            <div class="mod-label">{name}</div>
            <div class="mod-bar-wrap">
                <div class="mod-bar" style="width:{width:.1f}%; background:{color}"></div>
            </div>
            <div class="mod-score" style="color:{color}">{_fmt_score(score)}</div>
        </div>"""

    # ── Regime hero ──────────────────────────────────────────────────────────
    regime_color = regime["color"]
    regime_name = regime["name"]
    composite_str = _fmt_score(composite)
    weights_str = " · ".join(
        f"{LENS_NAMES_BG.get(m, m).lower()} {w:.0%}" for m, w in MODULE_WEIGHTS.items()
    )

    html = f"""<!DOCTYPE html>
<html lang="bg">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Българска Макроикономика — Дашборд</title>
<script src="https://cdn.plot.ly/plotly-2.24.1.min.js"></script>
<style>
  :root {{
    --bg:#0f1117; --card:#1a1d27; --border:#2a2d3e;
    --text:#e2e8f0; --muted:#8892a4; --accent:#7c6af7;
    --pos:#22c55e; --neg:#ef4444;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; padding:20px; }}
  a {{ color:var(--accent); text-decoration:none; }}
  
  .container {{ max-width:1280px; margin:0 auto; }}
  
  /* Header */
  .header {{ display:flex; justify-content:space-between; align-items:center; padding:20px 0 30px; border-bottom:1px solid var(--border); margin-bottom:30px; flex-wrap:wrap; gap:10px; }}
  .header-left h1 {{ font-size:1.6em; font-weight:700; }}
  .header-left .sub {{ color:var(--muted); font-size:0.85em; margin-top:4px; }}
  .header-right {{ text-align:right; }}
  .updated {{ color:var(--muted); font-size:0.8em; }}
  
  /* Regime hero */
  .regime-hero {{ background:var(--card); border-radius:16px; padding:30px; margin-bottom:30px;
                  border-left:6px solid {regime_color}; display:flex; align-items:center; gap:30px; flex-wrap:wrap; }}
  .regime-score-big {{ font-size:4em; font-weight:800; color:{regime_color}; line-height:1; }}
  .regime-label {{ font-size:1.5em; font-weight:600; color:{regime_color}; }}
  .regime-desc {{ color:var(--muted); font-size:0.9em; margin-top:6px; max-width:500px; }}
  .verdict {{ font-size:1.05em; font-weight:600; color:var(--text); margin-top:10px; max-width:560px; line-height:1.45; }}

  /* Методология */
  .methodology {{ background:var(--card); border:1px solid var(--border); border-radius:12px;
                  padding:18px 24px; margin-bottom:30px; }}
  .methodology summary {{ cursor:pointer; font-weight:600; font-size:0.95em; }}
  .methodology h4 {{ font-size:0.85em; text-transform:uppercase; letter-spacing:0.6px;
                     color:var(--accent); margin:16px 0 4px; }}
  .methodology p {{ color:var(--muted); font-size:0.87em; line-height:1.55; }}
  .methodology code {{ background:#252836; padding:1px 5px; border-radius:4px; font-size:0.92em; }}

  /* Индикаторни имена + застояли наблюдения */
  .ind-name a {{ border-bottom:1px dotted rgba(124,106,247,0.5); }}
  .ind-name a:hover {{ border-bottom-color:var(--accent); }}
  .stale {{ color:#ff9800; cursor:help; }}

  /* Module bars */
  .modules-card {{ background:var(--card); border-radius:12px; padding:24px; margin-bottom:30px; border:1px solid var(--border); }}
  .modules-card h2 {{ margin-bottom:20px; font-size:1.1em; color:var(--muted); text-transform:uppercase; letter-spacing:1px; }}
  .mod-row {{ display:flex; align-items:center; gap:12px; margin-bottom:14px; }}
  .mod-label {{ width:160px; font-size:0.9em; color:var(--muted); flex-shrink:0; }}
  .mod-bar-wrap {{ flex:1; background:#252836; border-radius:4px; height:8px; overflow:hidden; }}
  .mod-bar {{ height:100%; border-radius:4px; transition:width 0.5s; }}
  .mod-score {{ width:40px; text-align:right; font-weight:700; font-size:0.95em; }}
  
  /* Two-column layout */
  .two-col {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:30px; }}
  @media(max-width:900px) {{ .two-col {{ grid-template-columns:1fr; }} }}
  
  /* Cards */
  .card {{ background:var(--card); border-radius:12px; padding:24px; border:1px solid var(--border); }}
  .card h2 {{ font-size:1.1em; color:var(--muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:16px; }}
  
  /* Table */
  table {{ width:100%; border-collapse:collapse; font-size:0.88em; }}
  th {{ color:var(--muted); font-weight:500; padding:8px 10px; text-align:left; border-bottom:1px solid var(--border); }}
  td {{ padding:9px 10px; border-bottom:1px solid #1e2130; }}
  tr:hover td {{ background:#1e2130; }}
  .pos {{ color:var(--pos); }}
  .neg {{ color:var(--neg); }}
  
  /* Lens badges */
  .lens-badge {{ font-size:0.72em; padding:2px 7px; border-radius:20px; font-weight:600; text-transform:uppercase; letter-spacing:0.5px; }}
  .lens-growth {{ background:#1e3a5f; color:#60a5fa; }}
  .lens-inflation {{ background:#3f1515; color:#f87171; }}
  .lens-labor {{ background:#3f2a00; color:#fbbf24; }}
  .lens-credit {{ background:#2d1f4a; color:#c084fc; }}
  .lens-external {{ background:#0f3030; color:#34d399; }}
  
  /* Chart area */
  .chart-area {{ background:var(--card); border-radius:12px; padding:24px; border:1px solid var(--border); margin-bottom:30px; }}
  .chart-area h2 {{ font-size:1.1em; color:var(--muted); text-transform:uppercase; letter-spacing:1px; margin-bottom:6px; }}
  .chart-selector {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px; }}
  .chart-btn {{ background:#252836; border:1px solid var(--border); color:var(--muted); padding:6px 14px; border-radius:20px;
                cursor:pointer; font-size:0.82em; transition:all 0.2s; }}
  .chart-btn:hover, .chart-btn.active {{ background:var(--accent); color:#fff; border-color:var(--accent); }}
  #main-chart {{ height:380px; }}
  
  /* Footer */
  footer {{ text-align:center; color:var(--muted); font-size:0.8em; padding:30px 0 10px; border-top:1px solid var(--border); margin-top:10px; }}
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <div class="header-left">
      <h1>🇧🇬 Българска Макроикономика</h1>
      <div class="sub">Данни от НСИ и БНБ (чрез Eurostat) · Автоматично обновяване</div>
    </div>
    <div class="header-right">
      <div class="updated">Генериран {generated_str} · Данни към {as_of_str}</div>
    </div>
  </div>

  <!-- Regime Hero -->
  <div class="regime-hero">
    <div>
      <div class="regime-score-big">{composite_str}</div>
      <div style="color:var(--muted); font-size:0.8em; margin-top:4px;">от 100</div>
    </div>
    <div>
      <div class="regime-label">{regime_name}</div>
      <div class="verdict">{verdict}</div>
      <div class="regime-desc">
        Композитен макроикономически резултат за България по {len(SERIES_CATALOG)} ключови
        индикатора от Eurostat (НСИ и БНБ данни). 50 = близката 10-годишна норма;
        по-високо = по-здраво.
      </div>
    </div>
  </div>

  <!-- Методология (ФОРМА-КАНОН: обяснението стои при уреда, не в друг документ) -->
  <details class="methodology" open>
    <summary>Как да четеш този дашборд</summary>

    <h4>Скалата 0–100</h4>
    <p>
      Всяка серия се сравнява със СОБСТВЕНАТА си близка норма — медианата на
      последните 10 години, а разсейването се мери робастно
      (<code>1.4826 · MAD</code>, за да не разтяга скалата един извънреден месец).
      Полученото отклонение минава през <code>score = 50·(1 + tanh(z/2))</code>:
      <b>50 = нормалното за България напоследък</b>, ±2σ ≈ 88 / 12. Числото е
      описателно (къде сме), не прогнозно.
    </p>

    <h4>Инфлацията се мери като отклонение от 2%</h4>
    <p>
      Не „ниско = добре" — иначе дефлацията би излизала отличник. Здравето е
      максимално при целта на ЕЦБ (2%) и пада симетрично в двете посоки
      (U-форма). България е в еврозоната от 01.01.2026 → същият център като EA.
    </p>

    <h4>Текущата сметка е 4-тримесечна плъзгаща</h4>
    <p>
      Конвенционалният прочит за съотношения спрямо БВП. Суровото тримесечие е
      чувствително по-волатилно и остава на графиката като тънка прекъсната
      линия, но скорът и таблицата четат плъзгащата.
    </p>

    <h4>Композитът</h4>
    <p>
      Претеглена средна на петте лещи ({weights_str}). Леща без данни ИЗПАДА и
      теглата се преизчисляват — не се брои като „неутрално 50".
    </p>

    <h4>As-of дисциплина</h4>
    <p>
      „Данни към" е най-скорошното НАБЛЮДЕНИЕ, не времето на генериране. Всеки
      ред показва своя период; <span class="stale">⚠</span> означава наблюдение
      по-старо от двойния очакван ритъм на публикуване (месечни &gt; 2 месеца,
      тримесечни &gt; 6 месеца). Имената на индикаторите водят към набора в
      Eurostat databrowser.
    </p>
  </details>

  <!-- Module Bars -->
  <div class="modules-card">
    <h2>Компоненти на резултата</h2>
    {module_bars}
  </div>

  <!-- Two columns: Table + Chart selector -->
  <div class="two-col">
    <div class="card">
      <h2>Последни стойности</h2>
      <table>
        <thead><tr><th>Индикатор</th><th>Леща</th><th>Период</th><th>Стойност</th><th>Δ</th><th>Score</th></tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>

    <div class="card">
      <h2>Режими по компонент</h2>
      <div id="radar-chart" style="height:320px;"></div>
    </div>
  </div>

  <!-- Main Chart -->
  <div class="chart-area">
    <h2 id="chart-title">Изберете индикатор</h2>
    <div class="chart-selector" id="chart-selector"></div>
    <div id="main-chart"></div>
  </div>

</div>

<footer>
  Данните са от <a href="https://ec.europa.eu/eurostat" target="_blank">Eurostat</a> (НСИ и БНБ репортинг) ·
  Генериран {generated_str} · Данни към {as_of_str} ·
  <a href="https://github.com/tsvetoslavtsachev/bg-macro-dashboard" target="_blank">GitHub</a>
</footer>

<script>
const CHART_DATA = {json.dumps(chart_data, ensure_ascii=False)};

const LENS_COLORS = {{
  growth:    "#60a5fa",
  inflation: "#f87171",
  labor:     "#fbbf24",
  credit:    "#c084fc",
  external:  "#34d399"
}};

const LENS_BG = {{
  growth:    "rgba(96,165,250,0.08)",
  inflation: "rgba(248,113,113,0.08)",
  labor:     "rgba(251,191,36,0.08)",
  credit:    "rgba(192,132,252,0.08)",
  external:  "rgba(52,211,153,0.08)"
}};

const MODULE_SCORES = {json.dumps(module_scores)};
// Един речник — същите имена като модул-баровете и briefing_context (config.py)
const BG_NAMES = {json.dumps(LENS_NAMES_BG, ensure_ascii=False)};

// Build chart selector buttons
const selector = document.getElementById("chart-selector");
for (const [key, data] of Object.entries(CHART_DATA)) {{
  const btn = document.createElement("button");
  btn.className = "chart-btn";
  btn.textContent = data.name;
  btn.dataset.key = key;
  btn.onclick = () => showChart(key);
  selector.appendChild(btn);
}}

let activeKey = null;

function showChart(key) {{
  if (!CHART_DATA[key]) return;
  
  // Update active button
  document.querySelectorAll(".chart-btn").forEach(b => b.classList.remove("active"));
  const btn = document.querySelector(`[data-key="${{key}}"]`);
  if (btn) btn.classList.add("active");
  
  const data = CHART_DATA[key];
  const color = LENS_COLORS[data.lens] || "#7c6af7";
  const fillColor = LENS_BG[data.lens] || "rgba(124,106,247,0.08)";
  
  document.getElementById("chart-title").textContent = data.name;
  
  const trace = {{
    x: data.dates,
    y: data.values,
    type: "scatter",
    mode: "lines",
    name: data.name,
    line: {{ color: color, width: 2.5 }},
    fill: "tozeroy",
    fillcolor: fillColor,
    hovertemplate: "%{{x|%b %Y}}: <b>%{{y:.2f}}</b><extra></extra>"
  }};

  const traces = [trace];

  // Суровото тримесечие под плъзгащата средна
  if (data.values_raw) {{
    traces.push({{
      x: data.dates,
      y: data.values_raw,
      type: "scatter",
      mode: "lines",
      name: "тримесечно",
      line: {{ color: color, width: 1, dash: "dash" }},
      opacity: 0.4,
      hovertemplate: "%{{x|%b %Y}} (тримесечно): <b>%{{y:.2f}}</b><extra></extra>"
    }});
  }}

  // Add zero line
  const shapes = [];
  if (data.values.some(v => v < 0)) {{
    shapes.push({{
      type: "line", x0: data.dates[0], x1: data.dates[data.dates.length-1],
      y0: 0, y1: 0, line: {{ color: "#555", width: 1, dash: "dot" }}
    }});
  }}
  
  const layout = {{
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: {{ color: "#8892a4", family: "-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" }},
    margin: {{ t: 10, r: 20, b: 40, l: 50 }},
    xaxis: {{ showgrid: false, zeroline: false, color: "#8892a4" }},
    yaxis: {{ gridcolor: "#1e2130", zerolinecolor: "#444", color: "#8892a4" }},
    shapes: shapes,
    hovermode: "x unified",
    showlegend: traces.length > 1,
    legend: {{ orientation: "h", y: 1.12, x: 0 }}
  }};

  Plotly.react("main-chart", traces, layout, {{displayModeBar: false, responsive: true}});
  activeKey = key;
}}

// Radar chart
(function() {{
  // Леща без данни (null) изпада от радара — не се рисува като „неутрално 50"
  const entries = Object.entries(MODULE_SCORES).filter(([, v]) => v !== null);
  if (!entries.length) return;
  const categories = entries.map(([k]) => BG_NAMES[k] || k);
  const values = entries.map(([, v]) => v);
  // Close the polygon
  const cats = [...categories, categories[0]];
  const vals = [...values, values[0]];

  const trace = {{
    type: "scatterpolar",
    r: vals,
    theta: cats,
    fill: "toself",
    fillcolor: "rgba(124,106,247,0.15)",
    line: {{ color: "#7c6af7", width: 2 }},
    marker: {{ color: "#7c6af7", size: 6 }},
    hovertemplate: "%{{theta}}: <b>%{{r:.1f}}</b><extra></extra>"
  }};
  
  const layout = {{
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: {{ color: "#8892a4" }},
    margin: {{ t: 20, r: 20, b: 20, l: 20 }},
    polar: {{
      bgcolor: "rgba(0,0,0,0)",
      radialaxis: {{ visible: true, range: [0, 100], color: "#444", gridcolor: "#2a2d3e", tickfont: {{ size: 10 }} }},
      angularaxis: {{ color: "#8892a4", gridcolor: "#2a2d3e" }}
    }},
    showlegend: false
  }};
  
  Plotly.newPlot("radar-chart", [trace], layout, {{displayModeBar: false, responsive: true}});
}})();

// Auto-show first chart
const firstKey = Object.keys(CHART_DATA)[0];
if (firstKey) showChart(firstKey);
</script>
</body>
</html>
"""

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ HTML дашбордът е запазен в: {output_path}")
