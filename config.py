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

# ─── Cross-reference SIDs за derived computations ────────────────────────────
CORE_DEFLATOR_KEY = "BG_HICP_CORE"      
HEADLINE_DEFLATOR_KEY = "BG_HICP"  
NOMINAL_10Y_KEY = "BG_LT_RATE"         
