"""
export/weekly_briefing.py
=========================
Генерира пълен интерактивен HTML дашборд за българската икономика.
"""
import html as _html
import json
import math
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from config import (
    CONTEXT_BADGE_BG,
    CONTEXT_BADGE_COLORS,
    CONTEXT_LINE_COLOR,
    CONTEXT_SCORE_NOTE,
    LENS_BADGE_COLORS,
    LENS_BADGES_BG,
    LENS_LINE_COLORS,
    LENS_NAMES_BG,
    MACRO_REGIMES,
    MODULE_WEIGHTS,
)
from analysis.lens_history import HONESTY_LABEL, ROW_LIVE, ROW_QUARTER
from analysis.temperature import TEMP_SERIES, temp_level, zone_table
from catalog.polarity import INFLATION_TARGET, OPT_SOURCE_NOTE, U_BAND
from catalog.series import SERIES_CATALOG
from core.display import (
    ANCHOR_DISCLAIMER,
    fmt_target,
    inflation_voices,
    is_stale,
    source_url,
    stale_note,
    thin_window_note,
    verdict_sentence,
)
from core.primitives import apply_transform, compute_yoy_pct
from core.scorer import TANH_SLOPE


# ── Температурният слой: цветовете на трите нива (мандат №47) ────────────────
# Сиво при 0 · оранж при 1-2 · червено при ≥3. Нивото идва от
# `analysis.temperature.temp_level` — праговете не се преизмислят тук.
TEMP_COLORS = {
    "cold": "#8892a4",
    "warm": "#ff9800",
    "hot":  "#ef4444",
}


# ── Броят лещи не е зашит никъде в текста (мандат №43) ───────────────────────
# Методологията казваше „петте лещи“ буквално. Шестата леща щеше да я направи
# невярна тихо — затова числителното се извежда от MODULE_WEIGHTS.
_COUNT_WORD_BG = {
    2: "двете", 3: "трите", 4: "четирите", 5: "петте",
    6: "шестте", 7: "седемте", 8: "осемте",
}


def _count_word(n: int) -> str:
    return _COUNT_WORD_BG.get(n, f"{n}-те")


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """`#60a5fa` → `rgba(96,165,250,0.08)` — запълването под линията."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


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


def _chart_palette_key(spec: dict) -> str:
    """Кой цвят носи серията на графиката.

    Контекстната серия (мандат №48) няма леща → без този клон fallback-ът щеше
    да я оцвети като РАСТЕЖ и лицето щеше да твърди лещова принадлежност, която
    тя няма. Сивото казва „наблюдение, не компонент".
    """
    if spec.get("context_only"):
        return "context"
    return spec["lens"][0] if spec.get("lens") else "growth"


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
            "lens": _chart_palette_key(spec),
            "is_rate": spec.get("is_rate", False),
        }
        if transform == "roll4q_mean":
            # Суровото тримесечие остава видимо като тънка прекъсната линия.
            raw_recent = s_raw.reindex(s_recent.index)
            entry["values_raw"] = [
                round(float(v), 4) if pd.notna(v) else None for v in raw_recent.values
            ]
            entry["raw_name"] = "тримесечно"
        elif transform == "yoy_roll4":
            # Мандат №47: под плъзгащата стои СУРОВОТО г/г — не суровият индекс.
            # Изгладената линия носи котвата, но шумът остава видим.
            raw_recent = compute_yoy_pct(s_raw).reindex(s_recent.index)
            entry["values_raw"] = [
                round(float(v), 4) if pd.notna(v) else None for v in raw_recent.values
            ]
            entry["raw_name"] = "тримесечно г/г"
        chart_data[key] = entry
    return chart_data


def _regime_bands() -> list:
    """Режимните ленти като [{y0, y1, color}] — праговете от `MACRO_REGIMES`.

    Таблицата е подредена низходящо (80 · 65 · 50 · 35 · 0); горният край на
    всяка лента е прагът на предишната, а на най-горната — 100.
    """
    bands = []
    upper = 100.0
    for threshold, _name, color in MACRO_REGIMES:
        bands.append({"y0": float(threshold), "y1": upper, "color": color})
        upper = float(threshold)
    return bands


def _prep_film_data(history) -> dict:
    """Решетката → JSON за филма. Смятането е ТУК, в JS остава само рисуването."""
    if history is None or len(history) == 0:
        return {}

    q = history[history["row_type"] == ROW_QUARTER].dropna(subset=["composite"])
    live = history[history["row_type"] == ROW_LIVE].dropna(subset=["composite"])

    data = {
        "dates": [d.strftime("%Y-%m-%d") for d in q.index],
        "values": [round(float(v), 1) for v in q["composite"]],
        "bands": _regime_bands(),
        "label": HONESTY_LABEL,
    }
    if len(live):
        data["live"] = {
            "date": live.index[-1].strftime("%Y-%m-%d"),
            "value": round(float(live["composite"].iloc[-1]), 1),
        }

    # ── Температурната лента (мандат №47) ────────────────────────────────────
    # Барове 0–5 по СЪЩИТЕ тримесечни маркове: колко бум-серии са били над
    # зоната си. Цветът се решава тук (`temp_level`), в JS не остава аритметика.
    if "temp_count" in q.columns and q["temp_count"].notna().any():
        counts = [
            int(v) if pd.notna(v) else 0 for v in q["temp_count"]
        ]
        data["temp"] = {
            "values": counts,
            "colors": [TEMP_COLORS[temp_level(c)] for c in counts],
            "max": len(TEMP_SERIES),
            "note": ("Температурата: колко бум-серии са над зоната си "
                     "(абсолютни котви — валидни и назад)"),
        }
    return data


def _prep_wow_data(wow) -> dict:
    """WoW делтата → готови за рисуване редове (нула аритметика в JS)."""
    if not wow:
        return {
            "available": False,
            "empty_note": "Първи запис в живия журнал — делтата тръгва от "
                          "следващия пуск.",
        }

    def _fmt_delta(d) -> str:
        if d is None:
            return "—"
        return f"{d:+.1f}"

    def _cls(d) -> str:
        if d is None or d == 0:
            return ""
        return "pos" if d > 0 else "neg"

    try:
        prev_human = datetime.strptime(wow["prev_date"], "%Y-%m-%d").strftime("%d.%m.%Y")
    except (ValueError, KeyError, TypeError):
        prev_human = str(wow.get("prev_date", "—"))

    lens_deltas = wow.get("lens_deltas") or {}
    rows = [
        {
            "name": LENS_NAMES_BG.get(lens, lens),
            "delta": lens_deltas.get(lens),
            "delta_str": _fmt_delta(lens_deltas.get(lens)),
            "cls": _cls(lens_deltas.get(lens)),
        }
        for lens in MODULE_WEIGHTS
        if lens in lens_deltas
    ]
    # Сортиране по |Δ| — най-голямото движение отгоре, а не азбучен ред.
    rows.sort(key=lambda r: abs(r["delta"]) if r["delta"] is not None else -1.0,
              reverse=True)

    return {
        "available": True,
        "prev_date": prev_human,
        "since": f"спрямо {prev_human}",
        "composite_delta": wow.get("composite_delta"),
        "composite_delta_str": _fmt_delta(wow.get("composite_delta")),
        "composite_cls": _cls(wow.get("composite_delta")),
        "rows": rows,
        "composition_changed": bool(wow.get("composition_changed")),
        "composition_note": "⚠ съставът на уреда се смени между двата записа — "
                            "делтата не е чиста",
    }


def _temp_badge_html(temp) -> str:
    """„Прегряване: N/5" до режимния етикет + tooltip кой гори (мандат №47).

    Данните идват ГОТОВИ от `analysis.temperature` — нула смятане в JS и нула
    прагове, преписани в лицето.
    """
    if not temp or not temp.get("n_total"):
        return ""
    n_hot, n_total = int(temp["n_hot"]), int(temp["n_total"])
    level = temp_level(n_hot)
    if temp.get("hot"):
        tip = " · ".join(
            f"{e['name_bg']}: {e['value']:.1f} (зона до {e['hi']:.0f})"
            for e in temp["hot"]
        )
    else:
        tip = "Нито една бум-серия не е над зоната си."
    return (
        f'<span class="temp-badge temp-{level}" title="{_html.escape(tip)}">'
        f'🌡 Прегряване: {n_hot}/{n_total}</span>'
    )


def _zone_rows_html() -> str:
    """Зоните като редове на таблица в методологията — от POLARITY, не преписани."""
    rows = ""
    for z in zone_table(SERIES_CATALOG):
        rows += (
            f"<tr><td>{_html.escape(z['name_bg'])}</td>"
            f"<td>{z['lo']:.0f} … {z['hi']:.0f}%</td>"
            f"<td>{z['s']:.0f} пп</td>"
            f"<td>{_html.escape(z['provenance'])}</td></tr>"
        )
    return rows


def _anchor_card(voices: dict) -> str:
    """Котвената лента: инфлацията, мерена в пп от целта (мандат №48).

    Вторият глас стои ДО модул-баровете, а не в тях — затова лентата носи
    изричното изречение, че композитът е недокоснат. Празни данни → няма лента,
    а не празна рамка (същото правило като при филма).
    """
    anchors = voices.get("anchors") or []
    perceived = voices.get("perceived")
    if not anchors and not perceived:
        return ""

    rows = ""
    for a in anchors:
        rows += f"""
      <div class="anchor-row">
        <span class="anchor-dot" style="background:{a['color']}"></span>
        <span class="anchor-name">{_html.escape(a['name_bg'])}</span>
        <span class="anchor-sentence">{_html.escape(a['value_str'])} =
          <b>{_html.escape(a['gap_phrase'])}</b> — {_html.escape(a['zone_phrase'])}</span>
      </div>"""

    if perceived:
        rows += f"""
      <div class="anchor-row anchor-context">
        <span class="anchor-dot anchor-dot-ctx"></span>
        <span class="anchor-name">{_html.escape(perceived['name_bg'])}</span>
        <span class="anchor-sentence">{_html.escape(perceived['sentence'])}</span>
      </div>"""

    return f"""
  <!-- Котвената лента: инфлацията с абсолютни зони (мандат №48) -->
  <div class="anchor-card">
    <h2>Инфлацията с котви</h2>
    <div class="anchor-rows">{rows}
    </div>
    <div class="anchor-note">{_html.escape(voices.get('disclaimer', ''))}</div>
  </div>
"""


def generate_html(
    snapshot: dict,
    lens_reports: dict,
    composite,
    regime: dict,
    output_path: str,
    history=None,
    wow=None,
    temp=None,
):
    chart_data = _prep_chart_data(snapshot)
    film_data = _prep_film_data(history)
    wow_data = _prep_wow_data(wow)
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
        is_context = bool(spec.get("context_only"))
        lens = _chart_palette_key(spec)
        badge = CONTEXT_BADGE_BG if is_context else LENS_BADGES_BG.get(lens, lens)
        hint = _html.escape(spec.get("narrative_hint", "") or "")
        url = source_url(spec.get("source", ""), spec.get("id", ""))
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
        thin_mark = ""
        if res.get("thin_window"):
            thin_mark = (
                f'<span class="thin" title="'
                f'{_html.escape(thin_window_note(res.get("percentile_window")))}">⚠</span> '
            )
        if is_context:
            # Контекстната серия НЯМА score — и го казва, вместо да покаже тире,
            # което читателят би прочел като „липсват данни".
            score_cell = (
                f'<td class="ctx-score" title="{_html.escape(CONTEXT_SCORE_NOTE)}">—</td>'
            )
        else:
            score_cell = (
                f'<td style="color:{_score_color(score_val)}">'
                f'{thin_mark}<b>{_fmt_score(score_val)}</b></td>'
            )
        rows_html += f"""
            <tr onclick="showChart('{key}')" style="cursor:pointer">
                {name_cell}
                <td><span class="lens-badge lens-{lens}">{badge}</span></td>
                <td>{last_date}</td>
                <td><b>{last_val:.2f}</b></td>
                <td class="{delta_cls}">{delta_str}</td>
                {score_cell}
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
    temp_badge = _temp_badge_html(temp)
    zone_rows = _zone_rows_html()
    # Score-ът на серия В зоната — смятан, не преписан: платото е U_BAND, точно
    # както центърът на U-формата, а скалата е фамилната tanh.
    zone_score = round(50.0 * (1.0 + math.tanh(U_BAND / TANH_SLOPE)), 1)
    weights_str = " · ".join(
        f"{LENS_NAMES_BG.get(m, m).lower()} {w:.0%}" for m, w in MODULE_WEIGHTS.items()
    )
    lens_count_word = _count_word(len(MODULE_WEIGHTS))

    # Палитрата се генерира от ЕДИНИЯ речник в config.py — CSS баджовете тук,
    # линиите и запълването в JS по-долу. Нова леща = един ред в config.
    # Контекстният сив (мандат №48) се долепя на трите места наведнъж, точно
    # както лещовите цветове — не се пише на ръка в CSS-а и в JS-а поотделно.
    badge_colors = dict(LENS_BADGE_COLORS, context=CONTEXT_BADGE_COLORS)
    line_colors = dict(LENS_LINE_COLORS, context=CONTEXT_LINE_COLOR)
    lens_badge_css = "\n".join(
        f"  .lens-{lens} {{ background:{bg}; color:{fg}; }}"
        for lens, (bg, fg) in badge_colors.items()
    )
    lens_fill_colors = {
        lens: _hex_to_rgba(color, 0.08) for lens, color in line_colors.items()
    }

    # ── Котвената лента: инфлацията с абсолютни зони (мандат №48) ────────────
    anchor_card = _anchor_card(inflation_voices(snapshot))

    # ── Филмът на композита (мандат №45) ─────────────────────────────────────
    # Картата се появява само когато има какво да покаже — стар пуск без история
    # не рисува празна рамка.
    film_card = ""
    if film_data or wow_data.get("available"):
        film_card = f"""
  <!-- Филмът: композитът през времето (мандат №45 П1) -->
  <div class="card film-card">
    <h2>Филмът: композитът през времето</h2>
    <div class="film-label">{_html.escape(HONESTY_LABEL)}</div>
    <div class="film-grid">
      <div>
        <div id="film-chart"></div>
        <div class="film-temp-note" id="film-temp-note"></div>
      </div>
      <div class="wow-block">
        <h3>Какво се смени тази седмица</h3>
        <div id="wow-body"></div>
      </div>
    </div>
  </div>
"""

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
  .regime-line {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; }}
  .regime-label {{ font-size:1.5em; font-weight:600; color:{regime_color}; }}
  .regime-desc {{ color:var(--muted); font-size:0.9em; margin-top:6px; max-width:500px; }}

  /* Термометърът на прегряването (мандат №47) */
  .temp-badge {{ font-size:0.78em; font-weight:700; padding:4px 10px; border-radius:20px;
                 cursor:help; letter-spacing:0.3px; white-space:nowrap; }}
  .temp-cold {{ background:rgba(136,146,164,0.16); color:{TEMP_COLORS['cold']}; }}
  .temp-warm {{ background:rgba(255,152,0,0.16);   color:{TEMP_COLORS['warm']}; }}
  .temp-hot  {{ background:rgba(239,68,68,0.18);   color:{TEMP_COLORS['hot']}; }}
  .film-temp-note {{ color:var(--muted); font-size:0.78em; margin-top:8px; line-height:1.5; }}
  .zone-table {{ width:100%; border-collapse:collapse; font-size:0.82em; margin:10px 0 4px; }}
  .zone-table th {{ font-size:0.95em; padding:6px 8px; }}
  .zone-table td {{ padding:6px 8px; color:var(--muted); vertical-align:top; }}
  .verdict {{ font-size:1.05em; font-weight:600; color:var(--text); margin-top:10px; max-width:560px; line-height:1.45; }}

  /* Филмът на композита (мандат №45) */
  .film-card {{ margin-bottom:30px; }}
  .film-label {{ color:var(--muted); font-size:0.82em; margin:-8px 0 16px; line-height:1.5; }}
  .film-grid {{ display:grid; grid-template-columns:2.2fr 1fr; gap:24px; align-items:start; }}
  @media(max-width:900px) {{ .film-grid {{ grid-template-columns:1fr; }} }}
  #film-chart {{ height:340px; }}
  .wow-block h3 {{ font-size:0.8em; text-transform:uppercase; letter-spacing:0.6px;
                   color:var(--muted); margin-bottom:12px; }}
  .wow-since {{ color:var(--muted); font-size:0.78em; margin-bottom:12px; }}
  .wow-head {{ display:flex; justify-content:space-between; align-items:baseline;
               padding:8px 0 10px; border-bottom:1px solid var(--border); margin-bottom:8px; }}
  .wow-head .label {{ font-size:0.85em; color:var(--text); font-weight:600; }}
  .wow-head .val {{ font-size:1.25em; font-weight:700; }}
  .wow-row {{ display:flex; justify-content:space-between; align-items:baseline;
              padding:5px 0; font-size:0.85em; }}
  .wow-row .label {{ color:var(--muted); }}
  .wow-row .val {{ font-weight:600; }}
  .wow-note {{ color:var(--muted); font-size:0.82em; line-height:1.5; }}
  .wow-warn {{ color:#ff9800; font-size:0.78em; margin-top:10px; line-height:1.45; }}

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
  .thin {{ color:#ff9800; cursor:help; }}

  /* Module bars */
  .modules-card {{ background:var(--card); border-radius:12px; padding:24px; margin-bottom:30px; border:1px solid var(--border); }}
  .modules-card h2 {{ margin-bottom:20px; font-size:1.1em; color:var(--muted); text-transform:uppercase; letter-spacing:1px; }}
  .mod-row {{ display:flex; align-items:center; gap:12px; margin-bottom:14px; }}
  .mod-label {{ width:160px; font-size:0.9em; color:var(--muted); flex-shrink:0; }}
  .mod-bar-wrap {{ flex:1; background:#252836; border-radius:4px; height:8px; overflow:hidden; }}
  .mod-bar {{ height:100%; border-radius:4px; transition:width 0.5s; }}
  .mod-score {{ width:40px; text-align:right; font-weight:700; font-size:0.95em; }}
  
  /* Котвената лента (мандат №48) */
  .anchor-card {{ background:var(--card); border-radius:12px; padding:20px 24px;
                  margin-bottom:30px; border:1px solid var(--border); }}
  .anchor-card h2 {{ font-size:1.1em; color:var(--muted); text-transform:uppercase;
                     letter-spacing:1px; margin-bottom:14px; }}
  .anchor-row {{ display:flex; align-items:baseline; gap:10px; padding:6px 0;
                 font-size:0.9em; flex-wrap:wrap; }}
  .anchor-dot {{ width:10px; height:10px; border-radius:50%; flex-shrink:0; }}
  .anchor-dot-ctx {{ background:{CONTEXT_LINE_COLOR}; }}
  .anchor-name {{ color:var(--muted); min-width:210px; }}
  .anchor-sentence {{ color:var(--text); }}
  .anchor-context .anchor-sentence {{ color:var(--muted); }}
  .anchor-note {{ color:var(--muted); font-size:0.8em; margin-top:12px;
                  line-height:1.5; border-top:1px solid var(--border); padding-top:10px; }}
  .ctx-score {{ color:var(--muted); cursor:help; }}

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
{lens_badge_css}

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
      <div class="sub">Данни от НСИ и БНБ (чрез Eurostat и ЕЦБ) · Автоматично обновяване</div>
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
      <div class="regime-line">
        <span class="regime-label">{regime_name}</span>
        {temp_badge}
      </div>
      <div class="verdict">{verdict}</div>
      <div class="regime-desc">
        Композитен макроикономически резултат за България по {len(SERIES_CATALOG)} ключови
        индикатора от Eurostat и ЕЦБ (НСИ и БНБ данни). 50 = близката 10-годишна норма;
        по-високо = по-здраво.
      </div>
    </div>
  </div>

{film_card}
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

    <h4>Инфлацията: двата гласа</h4>
    <p>
      В композита инфлацията говори ОТНОСИТЕЛНО (U-score-ът горе): колко
      отклонението от целта е голямо спрямо СОБСТВЕНАТА разсейка на серията. За
      агрегация това е верният уред, но за България е системно <b>мек</b> — в
      страна, свикнала с висока инфлация, „нормалното" отклонение е голямо и 5%
      излиза по-малко тревожно, отколкото е. И 2007 беше „нормално" висока
      инфлация.
      Затова лентата „Инфлацията с котви" носи <b>втори, абсолютен глас</b>:
      колко <b>процентни пункта</b> сме от целта ({_html.escape(fmt_target(INFLATION_TARGET))}).
      Зоните са фиксирани: <b>≤1 пп</b> при целта (зелено) ·
      <b>1–2 пп</b> отклонена (жълто) · <b>&gt;2 пп</b> далеч от целта (червено).
      Те НЕ са калибрирани по историята — ако бяха, щяха да върнат същата
      мекота, която котвата поправя. Дефлационната посока минава през същите
      зони огледално. {_html.escape(ANCHOR_DISCLAIMER)}
    </p>

    <h4>Усещаната инфлация — контекст, не компонент</h4>
    <p>
      Третият ред в котвената лента е ЕК потребителската анкета (Eurostat
      <code>ei_bsco_m</code>, показател <code>BS-PT-LY</code>): как хората
      ОЦЕНЯВАТ поскъпването през последните 12 месеца. Числото е качествен
      <b>баланс</b>, не процент — 75 значи, че огромно мнозинство усеща
      поскъпване, а не „75% инфлация". Затова серията носи сивия бадж
      „{CONTEXT_BADGE_BG}", няма score и <b>не влиза в композита</b> — тя е
      наблюдение ДО официалното число. Стойността ѝ е точно в разликата:
      когато възприятието стои на нивата от инфлационната криза, а официалната
      инфлация е кратно по-ниска, това само по себе си е сигнал.
    </p>

    <h4>Текущата сметка е 4-тримесечна плъзгаща</h4>
    <p>
      Конвенционалният прочит за съотношения спрямо БВП. Суровото тримесечие е
      чувствително по-волатилно и остава на графиката като тънка прекъсната
      линия, но скорът и таблицата четат плъзгащата.
    </p>

    <h4>Композитът</h4>
    <p>
      Претеглена средна на {lens_count_word} лещи ({weights_str}). Леща без данни
      ИЗПАДА и теглата се преизчисляват — не се брои като „неутрално 50".
      Двете водещи лещи (инфлация и растеж) носят по 20%; <b>петте структурни</b>
      — труд, кредит, външен сектор, имоти и държавни финанси — са <b>равни</b>
      по 12%.
      <b>Внимание при сравнение назад:</b> с всяка нова леща се мени и СЪСТАВЪТ,
      и теглата — първо имотната (мандат №43), сега фискалната (мандат №50).
      Числото е на същата 0–100 скала, но не се сравнява механично с четенията
      отпреди това: разликата е смес от нови данни, нови тегла и нова леща.
    </p>

    <h4>Оптималните зони и температурата</h4>
    <p>
      Бумът вече <b>не се брои за здраве</b>. Пет серии — двата кредитни ръста,
      цените на жилищата, разрешителните и компенсацията на наетите — се мерят
      срещу <b>абсолютна оптимална зона</b>, а не срещу собствената си 10-годишна
      норма. Причината: в бум прозорец нормата сама се вдига и робастният
      <code>z</code> аплодира прегряването. В зоната здравето е на плато
      (score ≈ <b>{zone_score}</b>, същото като инфлация точно на целта); над
      горния праг score-ът пада с 1σ на всеки <code>s</code> пункта, под долния —
      симетрично. Медианата и MAD-скалата <b>не участват</b>.
    </p>
    <table class="zone-table">
      <thead><tr><th>Серия</th><th>Зона</th><th>1σ на</th><th>Откъде е прагът</th></tr></thead>
      <tbody>{zone_rows}</tbody>
    </table>
    <p>
      {OPT_SOURCE_NOTE} <b>Термометърът</b> („Прегряване: N/5" горе и лентата под
      филма) брои САМО нарушенията НАГОРЕ — колко от петте серии стоят над зоната
      си. Под долния праг е криза/кредитен крънч; той се чете в score-а, който
      пада и в двете посоки, не в термометъра. Праговете са абсолютни, затова
      температурата е смятаема и назад във времето без да знае бъдещето:
      2007-08 свети 4-5 от 5, а спокойните 2015-2019 мълчат на нула.
      <b>Внимание при сравнение назад:</b> съставът на уреда се смени с тези
      полярности — композитът е на същата 0–100 скала, но не се сравнява
      механично с четенията отпреди.
    </p>

    <h4>Имоти и строителство</h4>
    <p>
      Шестата леща стои на <b>три различни въпроса</b>, затова има три отделни
      групи: колко струва жилището (<code>prices</code> — индексът на цените на
      жилищата, г/г), колко се строи днес (<code>activity</code> — строителната
      продукция) и колко влиза в тръбата (<code>pipeline</code> — разрешителните
      за строеж по разгъната площ, водещият индикатор). Двузначността „бум =
      здраве днес, риск утре" при цените и разрешителните е <b>решена</b>: двете
      минаха на оптимални зони (виж по-горе). Строителната продукция остава
      <b>+1</b> — тя е текуща реална активност, не цена на актив и не тръба.
      Разрешителните се четат като <b>4-тримесечна плъзгаща</b> на годишния темп:
      суровото тримесечно г/г скача толкова, че никакъв абсолютен праг не
      издържа (в спокойните 2015-19 то стига 61%, докато плъзгащата остава под
      39%). Суровата линия е видима на графиката, но котвата стъпва на
      изгладената.
    </p>

    <h4>Държавните финанси</h4>
    <p>
      Седмата леща стои на <b>два различни въпроса</b> в две отделни групи:
      <b>потокът</b> (<code>fiscal_balance</code> — бюджетното салдо: колко се
      харчи над приходите) и <b>стокът</b> (<code>debt</code> — държавният дълг:
      колко е натрупано). Днешната картина е точно тази разцепка — остър поток
      при все още нисък сток. Фискалният лост е <b>единственият домашен макро
      лост</b>: лихвената политика е на ЕЦБ.
    </p>
    <p>
      <b>Салдото</b> е показателят B9 („нето кредитиране (+) / нето заемане
      (−)"), т.е. <b>плюсът е излишък</b>. Сезонно изгладен вариант за България
      <b>няма</b>, а суровото тримесечие е сезонен трион (дупки в Q4), затова
      прочитът е <b>4-тримесечна плъзгаща</b> — същата конвенция като при
      текущата сметка; суровото остава тънка прекъсната линия на графиката.
    </p>
    <p>
      <b>Дългът</b> се чете като <b>ниво</b>, но score-ът мери <b>дрейфа</b>:
      робастният <code>z</code> спрямо плъзгащата 10-годишна медиана вече казва
      „нивото се откъсна от десетилетието си", без шума на тримесечната делта.
      Затова и честността, която върви с числото: <b>абсолютните проценти са
      сред най-ниските в ЕС</b> — уредът мери движението спрямо собствената
      норма, не европейската класация. Маастрихтските прагове (3% дефицит, 60%
      дълг) са <b>контекст за четенето, не прагове в скоринга</b>.
    </p>

    <h4>As-of дисциплина</h4>
    <p>
      „Данни към" е най-скорошното НАБЛЮДЕНИЕ, не времето на генериране. Всеки
      ред показва своя период; <span class="stale">⚠</span> означава наблюдение
      по-старо от двойния очакван ритъм на публикуване (месечни &gt; 2 месеца,
      тримесечни &gt; 6 месеца). Имената на индикаторите водят към набора в
      Eurostat databrowser, а кредитните серии — към серията в ECB Data Portal.
    </p>

    <h4>Дългата кредитна памет</h4>
    <p>
      Кредитните серии са <b>тримесечни</b>: БНБ „Кредитна динамика" от
      <b>2005Q4</b> (суровината е комитната в репото) зашита с набора BSI на ЕЦБ,
      който тръгва от <b>01.2022</b>. Шевът се проверява автоматично — разликата
      между двата източника на всички общи тримесечия трябва да е под
      <code>0.5%</code>, иначе дашбордът не се генерира. Затова нормата тук вече
      е пълна 10-годишна, а не „изцяло бум период". Цената: последната точка е
      тримесечна и частичното текущо тримесечие не влиза.
    </p>

    <h4>Цената на кредита</h4>
    <p>
      „Лихва по нови фирмени кредити" е ставката по <b>нов бизнес</b> (ЕЦБ, набор
      MIR) — какво плаща фирмата, която тегли <b>днес</b>, а не средното по
      всички стари договори. Затова реагира бързо на трансмисията, докато
      салдата изостават. Историята е пълна от <b>01.2007</b>. В лещата тя е
      трета отделна peer-група (<code>lending_cost</code>) до цената на държавния
      дълг (<code>yields</code>) и обема на кредита (<code>lending</code>) —
      трите крака често сочат в различни посоки.
    </p>

    <h4>Филмът на композита</h4>
    <p>
      Линията НЕ е запис на това, което дашбордът е показвал тогава. Тя е
      <b>реконструкция</b>: днешният уред — днешните дефиниции, днешните лещи и
      тегла — пуснат върху днешните (вече <b>ревизирани</b>) данни, рязани по
      периодната дата. Затова етикетът казва „не point-in-time": реален
      наблюдател през 2009 е виждал други числа, друг състав и по-малко серии.
      Решетката тръгва от <b>2005Q4</b>, защото там се ражда кредитният seed на
      БНБ — по-рано кредитната леща пада до една серия и „историята" би мерила
      друг уред. Ранните точки стъпват на <b>по-къси норми</b> (когато в
      10-годишния прозорец няма 36 наблюдения, скорерът минава на пълната
      история), затова всеки ред носи <code>n_lenses</code> и
      <code>n_series</code> — те казват колко уред реално стои зад точката.
      Живият запис е ДРУГ файл: <code>data/score_journal.csv</code> получава по
      един ред на всеки ритуален пуск и оттам идва делтата „какво се смени тази
      седмица".
    </p>

    <h4>Къс прозорец</h4>
    <p>
      <span class="thin">⚠</span> до скора значи, че нормата НЕ е върху 10 години
      — етикетът на серията казва откога тече вместо да твърди „10г", защото
      <code>z</code>-ът върху къс, еднопосочен период подценява екстремността.
    </p>
  </details>

  <!-- Module Bars -->
  <div class="modules-card">
    <h2>Компоненти на резултата</h2>
    {module_bars}
  </div>
{anchor_card}
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
  Данните са от <a href="https://ec.europa.eu/eurostat" target="_blank">Eurostat</a> (НСИ и БНБ репортинг)
  и <a href="https://data.ecb.europa.eu/data/datasets/BSI" target="_blank">ЕЦБ Data Portal</a> (набори BSI и MIR) ·
  Генериран {generated_str} · Данни към {as_of_str} ·
  <a href="https://github.com/tsvetoslavtsachev/bg-macro-dashboard" target="_blank">GitHub</a>
</footer>

<script>
const CHART_DATA = {json.dumps(chart_data, ensure_ascii=False)};

// Един речник за палитрата (config.py) — CSS баджовете, линиите и запълването
// не се разминават, а нова леща не иска пипане на три места.
const LENS_COLORS = {json.dumps(line_colors, ensure_ascii=False)};

const LENS_BG = {json.dumps(lens_fill_colors, ensure_ascii=False)};

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
      name: data.raw_name || "тримесечно",
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

// ── Филмът на композита (мандат №45) ────────────────────────────────────────
// FILM_DATA/WOW_DATA идват ГОТОВИ от Python — тук само се рисува.
const FILM_DATA = {json.dumps(film_data, ensure_ascii=False)};
const WOW_DATA = {json.dumps(wow_data, ensure_ascii=False)};

(function() {{
  const el = document.getElementById("film-chart");
  if (!el || !FILM_DATA.dates || !FILM_DATA.dates.length) return;

  // Режимните ленти — праговете на композита като бледи хоризонтални полета
  const shapes = (FILM_DATA.bands || []).map(b => ({{
    type: "rect", xref: "paper", yref: "y",
    x0: 0, x1: 1, y0: b.y0, y1: b.y1,
    fillcolor: b.color, opacity: 0.06, line: {{ width: 0 }}, layer: "below"
  }}));

  const traces = [{{
    x: FILM_DATA.dates,
    y: FILM_DATA.values,
    type: "scatter",
    mode: "lines",
    name: "композит",
    line: {{ color: "#7c6af7", width: 2.5 }},
    hovertemplate: "%{{x|%b %Y}}: <b>%{{y:.1f}}</b><extra></extra>"
  }}];

  if (FILM_DATA.live) {{
    traces.push({{
      x: [FILM_DATA.live.date],
      y: [FILM_DATA.live.value],
      type: "scatter",
      mode: "markers",
      name: "днес",
      marker: {{ color: "#7c6af7", size: 11, line: {{ color: "#0f1117", width: 2 }} }},
      hovertemplate: "%{{x|%b %Y}} (живо): <b>%{{y:.1f}}</b><extra></extra>"
    }});
  }}

  const layout = {{
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: {{ color: "#8892a4", family: "-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" }},
    margin: {{ t: 10, r: 16, b: 40, l: 44 }},
    xaxis: {{ showgrid: false, zeroline: false, color: "#8892a4" }},
    yaxis: {{ range: [0, 100], gridcolor: "#1e2130", color: "#8892a4", dtick: 25 }},
    shapes: shapes,
    hovermode: "x unified",
    showlegend: false
  }};

  // Температурната лента: отделен под-panel под композита, обща x-ос.
  // Стойностите и цветовете идват ГОТОВИ от Python — тук само се рисува.
  if (FILM_DATA.temp) {{
    traces.push({{
      x: FILM_DATA.dates,
      y: FILM_DATA.temp.values,
      type: "bar",
      name: "прегряване",
      yaxis: "y2",
      marker: {{ color: FILM_DATA.temp.colors }},
      hovertemplate: "%{{x|%b %Y}}: <b>%{{y}}</b> бум-серии над зоната<extra></extra>"
    }});
    layout.yaxis.domain = [0.30, 1.0];
    layout.yaxis2 = {{
      domain: [0.0, 0.20],
      range: [0, FILM_DATA.temp.max],
      dtick: FILM_DATA.temp.max,
      gridcolor: "#1e2130",
      color: "#8892a4",
      anchor: "x"
    }};
    layout.xaxis.anchor = "y2";
    layout.bargap = 0.25;
    const note = document.getElementById("film-temp-note");
    if (note) note.textContent = FILM_DATA.temp.note;
  }}

  Plotly.newPlot("film-chart", traces, layout, {{displayModeBar: false, responsive: true}});
}})();

(function() {{
  const box = document.getElementById("wow-body");
  if (!box) return;

  if (!WOW_DATA.available) {{
    box.innerHTML = '<div class="wow-note">' + WOW_DATA.empty_note + '</div>';
    return;
  }}

  let h = '<div class="wow-since">' + WOW_DATA.since + '</div>';
  h += '<div class="wow-head"><span class="label">Композит</span>' +
       '<span class="val ' + WOW_DATA.composite_cls + '">' +
       WOW_DATA.composite_delta_str + '</span></div>';
  for (const r of WOW_DATA.rows) {{
    h += '<div class="wow-row"><span class="label">' + r.name + '</span>' +
         '<span class="val ' + r.cls + '">' + r.delta_str + '</span></div>';
  }}
  if (WOW_DATA.composition_changed) {{
    h += '<div class="wow-warn">' + WOW_DATA.composition_note + '</div>';
  }}
  box.innerHTML = h;
}})();

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
