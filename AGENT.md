# AGENT.md — Bulgarian Macro Dashboard

Техническа документация за AI агенти и разработчици.

## Архитектура

```
catalog/series.py       → Каталог от 14 серии с metadata
catalog/polarity.py     → Полярност: +1 / −1 / ("U","target",X)
sources/eurostat_adapter.py → Eurostat JSON-stat 2.0 клиент с кеш
sources/ecb_adapter.py  → ECB Data Portal SDMX-JSON клиент с кеш + ретраи
sources/manual_seed.py  → БНБ seed + тримесечният сплайс на кредитните серии
scripts/extract_bnb_seed.py → еднократна екстракция на seed-а от суровия .xlsx
core/primitives.py      → трансформации + robust_stats_latest (median/MAD)
core/scorer.py          → робастен z scoring, лещова агрегация, композит
core/display.py         → ФОРМА-КАНОН примитиви (линк, стойност, staleness, извод)
export/weekly_briefing.py → HTML дашборд с Plotly.js
export/briefing_context.py → Markdown context за LLM (--export-context)
run.py                  → CLI entry point
```

Редът в `run.py::_score_everything` е фиксиран:
`_build_snapshot` → **`splice_loans`** → `compute_lens_reports` → композит.
Сплайсът стои на ЕДНО място, за да получат `--status`, `--briefing` и
`--export-context` едно и също число.

## Добавяне на нова серия

1. Намери id-то на серията:
   - Eurostat → `sts_inpr_m?geo=BG&...`, `source: "eurostat"`
   - ЕЦБ → `<набор>/<ключ>`, напр. `BSI/M.BG.N.A.A20.A.1.U6.2240.Z01.E` или
     `MIR/M.BG.B.A2A.A.R.A.2240.EUR.N`, `source: "ecb"`. Наборът е свободен —
     адаптерът и линк-функцията са generic по flow, не зашити за BSI.
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

## ECB Data Portal API (набори BSI и MIR — БНБ кредитната статистика)

Базов URL: `https://data-api.ecb.europa.eu/service/data/{flowref}/{key}?format=jsondata`

Формат: SDMX-JSON 1.0 — наблюденията са в
`dataSets[0].series[<ключ>].observations`, а периодите в
`structure.dimensions.observation[0].values` (месечните са `"YYYY-MM"`).

Уловки:
- Историята за България в BSI започва **01.2022** — преди това порталът е празен
  (проверено с wildcard + `startPeriod`). Дългата памет идва от БНБ seed-а — виж
  секцията по-долу.
- Adjusted-growth ключовете (`A20T` / `A20I` / `A20A`) връщат **404** за БГ —
  затова четем стокове в млн. EUR и правим `yoy_pct` сами.
- Няма редономинационен скок около 01.2026 — сериите са в евро през целия период.
- Линкът към серията иска ключа **с префикса на набора**:
  `/data/datasets/BSI/BSI.M.BG.…`. Без префикса адресът е 404
  (`core/display.py::ecb_series_url`). Функцията е **generic по набор** — живо
  проверена и за MIR (`/data/datasets/MIR/MIR.M.BG.B.A2A.A.R.A.2240.EUR.N` → 200,
  26.07.2026).

### Набор MIR — лихвената статистика (мандат №42)

`MIR/M.BG.B.A2A.A.R.A.2240.EUR.N` = годишно приведена ставка (AAR/NDER) по
**нов бизнес**, кредити различни от револвиращи и овърдрафт, към нефинансови
предприятия (counterpart 2240), в EUR, месечна.

- За разлика от BSI, MIR носи **цялата история** в API-то: 2007-01 → 2026-05
  (n=233 на 26.07.2026). Никакъв seed, никакъв сплайс — серията се чете директно.
- Салда вариантът (`…A2A…O`) НЕ се ползва: ЕЦБ го държи чак от **2019-12**
  (n=78) и включва овърдрафтите. Публикуваният файл на БНБ
  `s_ir_loan_oa_nfc_bg.xlsx` е салда само по евро-деноминираните кредити —
  разминава се **дефиниционно** (0.3–2.2 пп) с всички API варианти и остава
  референция за ръчна сверка, не източник.
- `transform: "level"`, `is_rate: True`, полярност **−1**, peer-група
  `lending_cost` (отделна от `yields` — различен канал).

## `data/manual/` — БНБ seed-ът и сплайсът (мандат №41)

```
data/manual/raw/cred_q_dyn_type_eur_bg_2026-07-25.xlsx  ← суровината (PIT)
data/manual/bnb_loans_history.csv                        ← date, series, value_meur
```

**Какво е:** БНБ „Кредитна динамика“, лист `PUB_Q_DYN_CRED_TYPE` — тримесечни
кредитни салда от **2005Q4**. Редовете `Нефинансови предприятия` (BSI
counterpart 2240) и `Домакинства и НТООД` (2250); `Финансови предприятия` е
отделна секция и НЕ влиза.

**Как се обновява:** **не се обновява.** ЕЦБ BSI поема напред; seed-ът е
замразена дълга памет. Нов екстракт се прави само при **ревизия на историята**
от БНБ — нов файл в `raw/` с ново име (старият не се презаписва) и
`python scripts/extract_bnb_seed.py --raw <новия файл>`. Екстракторът намира
редовете **по етикет** и сверява колона B срещу `хил. евро`; при разминаване
вдига `ValueError`.

**Сплайсът (`sources/manual_seed.py::splice_loans`):**
1. Месечните API наблюдения → тримесечни: само месеци **3/6/9/12**. Частичното
   текущо тримесечие изпада само (щом месец 6 го няма, Q2 не се появява).
2. Seed тримесечията **преди** първото API тримесечие се слагат отпред.
3. **Валидация на шева на ВСИЧКИ общи тримесечия:** `|seed − api| / |api| ≤ 0.005`.
   Нарушение → `ValueError` с квартала и двете стойности. Нула припокриване →
   също грешка (шев без проверка). Живото състояние на 25.07.2026: 17 общи
   тримесечия на серия, max отклонение 0.0003% (закръгление).

Следствие за каталога: `release_schedule = "quarterly"`,
`historical_start = "2005-12-01"`. `yoy_pct` разпознава тримесечния индекс през
`pd.infer_freq` (`QS-DEC`) и ползва `pct_change(4)`.

## Къс прозорец (`thin_window`)

`core/scorer.py` сравнява реалния обхват на прозореца с `window_years`. Под
`THIN_WINDOW_FRACTION` (0.70) → `percentile_window` става
`"къс прозорец (от YYYY-MM)"` вместо `"10г"` и се вдига `thin_window: True`.
Флагът пътува до HTML таблицата (⚠ + tooltip) и до бележките в
`--export-context`. Скорът НЕ се коригира — флагът е честност за прозореца.

Механизмът е жив, но след №41 **нито една серия не го вдига**: кредитните
серии, заради които беше построен, вече стоят на пълния 10-годишен прозорец.
Бележката в експорта е динамична — появява се сама, ако утре нова серия влезе
къса.

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
   Кредит = 4 серии в 3 групи (`yields` · `lending` = двата заема заедно ·
   `lending_cost` = лихвата по нов бизнес); външен = 2 серии в 2 групи
   (`current_account` · `trade`).
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

**Планираният GitHub Actions пуск ВИНАГИ форсира** (`--refresh`, мандат №42):
тримесечен TTL 30 дни + седмичен cron без force = ново тримесечие може да чака
до ~30 дни на дашборда. Fetch-ът на всички серии е секунди, така че цената на
force-а е нула. Ръчният пуск пази input-а `force_refresh`.
