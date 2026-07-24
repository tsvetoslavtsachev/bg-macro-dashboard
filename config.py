"""
config.py
=========
Конфигурация за Bulgarian Macro Dashboard.
Съдържа API endpoints, тегла за composite score, прагове за режими и др.
"""
from pathlib import Path
import os

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

# ─── API Endpoints ───────────────────────────────────────────────────────────
EUROSTAT_API_BASE = os.environ.get(
    "EUROSTAT_API_BASE", 
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
)
BNB_EXCHANGE_API = "https://www.bnb.bg/Statistics/StExternalSector/StExchangeRates/StERForeignCurrencies/index.htm?download=xml&lang=BG"
NSI_API_BASE = "https://www.nsi.bg/opendata/getopendata_json.php?l=en&id="

# ─── Кеш ─────────────────────────────────────────────────────────────────────
CACHE_TTL_HOURS_DEFAULT = 12
CACHE_TTL_DAYS_BY_SCHEDULE = {
    "weekly":     3,
    "monthly":   10,
    "quarterly": 30,
    "annually":  90,
}

# ─── Исторически прозорци ────────────────────────────────────────────────────
# За България използваме данни от 2000г нататък, тъй като преди това
# има хиперинфлация (1997) и структурни промени. Валутният борд е от юли 1997.
HISTORY_START = "2000-01-01"            
ANALOG_HISTORY_START = "2000-01-01"     

# ─── Модулни тегла за Composite Macro Score (BG-калибрирани) ─────────────────
# Reasoning:
#   - inflation 0.25 — България е във валутен борд, инфлацията е ключова за Еврозоната
#   - labor 0.20    — Пазарът на труда е ключов двигател на потреблението
#   - growth 0.20   — Стандартна тежест
#   - credit 0.15   — Банковата система е ликвидна, кредитният цикъл е важен
#   - external 0.20 — Отворена икономика, зависима от износ и външни шокове
MODULE_WEIGHTS = {
    "inflation": 0.25,
    "labor":     0.20,
    "growth":    0.20,
    "credit":    0.15,
    "external":  0.20,
}

# ─── Macro режими ────────────────────────────────────────────────────────────
MACRO_REGIMES = [
    (80, "ЕКСПАНЗИОНЕН",   "#00c853"),
    (65, "ЗДРАВ",          "#69f0ae"),
    (50, "СМЕСЕН",         "#ffd600"),
    (35, "ВЛОШАВАЩ СЕ",    "#ff6d00"),
    (0,  "РЕЦЕСИОНЕН",     "#d50000"),
]

# ─── Лещови ленти на СЪЩАТА 0–100 скала ──────────────────────────────────────
# Режимното име носи КОМПОЗИТЪТ. Отделната леща носи само силата си: скор 34.8
# на инфлационната леща значи „далеч от целта", не „рецесионен" — режимният
# речник на композита е безсмислен на лещово ниво (одит 24.07 §4.4).
LENS_BANDS = [
    (80, "МНОГО СИЛНО"),
    (65, "СИЛНО"),
    (50, "ОКОЛО НОРМАТА"),
    (35, "СЛАБО"),
    (0,  "МНОГО СЛАБО"),
]

# ─── Cross-reference SIDs за derived computations ────────────────────────────
CORE_DEFLATOR_KEY = "BG_HICP_CORE"
HEADLINE_DEFLATOR_KEY = "BG_HICP"
NOMINAL_10Y_KEY = "BG_LT_RATE"

# ─── Един речник за лещите (ФОРМА-КАНОН) ─────────────────────────────────────
# Едно и също име за една и съща леща навсякъде: модул-барове, баджове в
# таблицата, извод-изречението, briefing_context. Не се преизмислят по места.
LENS_NAMES_BG = {
    "growth":    "Растеж",
    "inflation": "Инфлация",
    "labor":     "Пазар на труда",
    "credit":    "Кредит и финанси",
    "external":  "Външен сектор",
}

# Късата форма — баджовете до имената на сериите.
LENS_BADGES_BG = {
    "growth":    "растеж",
    "inflation": "инфлация",
    "labor":     "труд",
    "credit":    "кредит",
    "external":  "външен",
}

# Подложна форма (с определителен член) — за детерминистичното извод-изречение.
LENS_SUBJECTS_BG = {
    "growth":    "растежът",
    "inflation": "инфлацията",
    "labor":     "пазарът на труда",
    "credit":    "кредитът",
    "external":  "външният сектор",
}

# ─── Първоизточник: линк на всяко име (ФОРМА-КАНОН) ──────────────────────────
EUROSTAT_DATABROWSER = (
    "https://ec.europa.eu/eurostat/databrowser/view/{dataset}/default/table?lang=en"
)

# ─── Застояло наблюдение: 2× очаквания ритъм на публикуване ──────────────────
STALE_AFTER_MONTHS = {
    "daily":      1,
    "weekly":     1,
    "monthly":    2,
    "quarterly":  6,
    "annually":  24,
}
