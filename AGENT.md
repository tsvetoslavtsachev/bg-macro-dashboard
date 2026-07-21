# AGENT.md — Bulgarian Macro Dashboard

Техническа документация за AI агенти и разработчици.

## Архитектура

```
catalog/series.py       → Каталог от 10+ серии с metadata
catalog/polarity.py     → Посока на сериите (висок = добре/зле)
sources/eurostat_adapter.py → Eurostat JSON-stat 2.0 клиент с кеш
core/primitives.py      → YoY, MoM, Z-score трансформации
core/scorer.py          → Percentile scoring и composite score
export/weekly_briefing.py → HTML дашборд с Plotly.js
run.py                  → CLI entry point
```

## Добавяне на нова серия

1. Намери Eurostat dataset ID (напр. `sts_inpr_m?geo=BG&...`)
2. Добави в `catalog/series.py` → `SERIES_CATALOG`
3. Ако е "обратна" серия (висок = зле), добави в `catalog/polarity.py` → `INVERTED_SERIES`
4. Тествай: `python run.py --status --refresh`

## Eurostat API

Базов URL: `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset_id}`

Формат: JSON-stat 2.0. Периодите са в `dimension.time.category.index`.

## Composite Score логика

1. Всяка серия се трансформира (level / yoy_pct / z_score)
2. Изчислява се percentile rank спрямо историята от 2000г
3. Ако серията е "обратна", скорът = 100 - percentile
4. Серии се групират по lens (growth, inflation, labor, credit, external)
5. Lens score = средно от сериите в лещата
6. Composite = weighted average с тегла от `config.py`

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

Данните се кешират в `data/eurostat_cache.json`.
TTL: monthly=10 дни, quarterly=30 дни, weekly=3 дни.
