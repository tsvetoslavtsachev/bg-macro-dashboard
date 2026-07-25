# AGENT.md — Bulgarian Macro Dashboard

Техническа документация за AI агенти и разработчици.

## Архитектура

```
catalog/series.py       → Каталог от 13 серии с metadata
catalog/polarity.py     → Полярност: +1 / −1 / ("U","target",X)
sources/eurostat_adapter.py → Eurostat JSON-stat 2.0 клиент с кеш
sources/ecb_adapter.py  → ECB Data Portal SDMX-JSON клиент с кеш + ретраи
core/primitives.py      → трансформации + robust_stats_latest (median/MAD)
core/scorer.py          → робастен z scoring, лещова агрегация, композит
core/display.py         → ФОРМА-КАНОН примитиви (линк, стойност, staleness, извод)
export/weekly_briefing.py → HTML дашборд с Plotly.js
export/briefing_context.py → Markdown context за LLM (--export-context)
run.py                  → CLI entry point
```

## Добавяне на нова серия

1. Намери id-то на серията:
   - Eurostat → `sts_inpr_m?geo=BG&...`, `source: "eurostat"`
   - ЕЦБ → `<набор>/<ключ>`, напр. `BSI/M.BG.N.A.A20.A.1.U6.2240.Z01.E`,
     `source: "ecb"`
2. Добави в `catalog/series.py` → `SERIES_CATALOG` (задължително `lens`,
   `peer_group`, `transform`, `narrative_hint`)
3. Реши `peer_group` **съзнателно**: серии в една група дават ЕДИН сигнал
   (средно), лещата претегля групите. Два близки индикатора в една група ≠
   двойно тегло.
4. Добави **изричен** запис в `catalog/polarity.py` → `POLARITY`
   (`test_every_catalog_series_has_an_explicit_polarity` пази това)
5. Тествай: `python run.py --status --refresh` + `pytest -q`

## Eurostat API

Базов URL: `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset_id}`

Формат: JSON-stat 2.0. Периодите са в `dimension.time.category.index`.

## ECB Data Portal API (набор BSI — БНБ кредитната статистика)

Базов URL: `https://data-api.ecb.europa.eu/service/data/{flowref}/{key}?format=jsondata`

Формат: SDMX-JSON 1.0 — наблюденията са в
`dataSets[0].series[<ключ>].observations`, а периодите в
`structure.dimensions.observation[0].values` (месечните са `"YYYY-MM"`).

Уловки:
- Историята за България в BSI започва **01.2022** — преди това порталът е празен
  (проверено с wildcard + `startPeriod`).
- Adjusted-growth ключовете (`A20T` / `A20I` / `A20A`) връщат **404** за БГ —
  затова четем стокове в млн. EUR и правим `yoy_pct` сами.
- Няма редономинационен скок около 01.2026 — сериите са в евро през целия период.
- Линкът към серията иска ключа **с префикса на набора**:
  `/data/datasets/BSI/BSI.M.BG.…`. Без префикса адресът е 404
  (`core/display.py::ecb_series_url`).

## Къс прозорец (`thin_window`)

`core/scorer.py` сравнява реалния обхват на прозореца с `window_years`. Под
`THIN_WINDOW_FRACTION` (0.70) → `percentile_window` става
`"къс прозорец (от YYYY-MM)"` вместо `"10г"` и се вдига `thin_window: True`.
Флагът пътува до HTML таблицата (⚠ + tooltip) и до бележките в
`--export-context`. Скорът НЕ се коригира — флагът е честност за прозореца.

## Composite Score логика

Фамилният примитив (същият като us / eu / china) — реф.
`dashboards/macro-satellite/LENS_SCORING_METHODOLOGY.md`:

1. Каталожна трансформация (`level` / `yoy_pct` / `roll4q_mean`) ПРЕДИ скоринга
2. Робастен z спрямо плъзгащ **10-годишен** прозорец:
   `z = (x − median₁₀) / (1.4826 · MAD₁₀)`, `MIN_OBS = 36`
3. Полярност → health-z: `+1` / `−1` / U-форма около 2% за инфлацията
   (`U_BAND = 1.0`, `z_h = U_BAND − |z_dev|`)
4. `score = 50 · (1 + tanh(z_h / 2))` — **50 = близката норма**
5. Серия → peer-група (средно) → леща (претеглено; всички тегла 1.0).
   Кредит = 3 серии в 2 групи (`yields` · `lending` = двата заема заедно);
   външен = 2 серии в 2 групи (`current_account` · `trade`).
6. Composite = weighted average по `MODULE_WEIGHTS`, **ренормализиран** —
   леща без данни изпада, не се брои като 50

**Пазачи:** `MAD = 0` в прозореца → норма от пълната история с клип ±6σ
(`scale_fallback`); без вариация и там → `degenerate` (неутрално + флаг).
Percentile остава в изхода само като второстепенен контекст.

## Тегла (config.py)

```python
MODULE_WEIGHTS = {
    "inflation": 0.25,  # Ключово за Еврозоната
    "labor":     0.20,
    "growth":    0.20,
    "credit":    0.15,
    "external":  0.20,  # Отворена икономика
}
```

## Кеш

Данните се кешират в `data/eurostat_cache.json` и `data/ecb_cache.json` —
отделни файлове на източник, и двата се комитват.
TTL: monthly=10 дни, quarterly=30 дни, weekly=3 дни.
