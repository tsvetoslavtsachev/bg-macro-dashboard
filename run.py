"""
run.py
======
Entry point за Bulgarian Macro Dashboard.
"""
import argparse
import sys
import logging
from pathlib import Path

# Windows конзолата е cp1252 по подразбиране — без това print-овете гърмят.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Add to path
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from sources import build_adapters
from catalog.series import SERIES_CATALOG, series_by_source, validate_catalog
from core.primitives import apply_transform
from core.scorer import compute_module_scores, compute_composite_score, get_regime

def _build_snapshot(adapters: dict, force: bool = False) -> dict:
    """
    Сглобява snapshot от всички серии.
    fetch_many сам решава кеш или мрежа по TTL (_is_stale) — затова минава
    през него ВИНАГИ, не само при липсваща серия.
    """
    snapshot = {}
    for source_name, adapter in adapters.items():
        specs = series_by_source(source_name)
        if not specs:
            continue

        results = adapter.fetch_many(specs, force=force)
        snapshot.update(results)

    return snapshot

def cmd_status(args):
    """Показва статуса на данните."""
    print(f"📊 Catalog: {len(SERIES_CATALOG)} series")
    
    adapters = build_adapters()
    snapshot = _build_snapshot(adapters, force=args.refresh)
    
    print(f"\n📈 Извлечени: {len(snapshot)} / {len(SERIES_CATALOG)} серии")
    
    # Calculate scores
    module_scores = compute_module_scores(SERIES_CATALOG, snapshot)
    composite = compute_composite_score(module_scores)
    regime = get_regime(composite)
    
    print("\n" + "="*40)
    print(f"🌍 ТЕКУЩ МАКРО РЕЖИМ: {regime['name']} (Score: {composite:.1f}/100)")
    print("="*40)
    
    for module, score in module_scores.items():
        print(f"  • {module.capitalize():<10}: {score:.1f}")
        
    print("\nПоследни данни по серии (след трансформацията от каталога):")
    for key, spec in SERIES_CATALOG.items():
        if key in snapshot and not snapshot[key].empty:
            s = apply_transform(snapshot[key], spec["transform"]).dropna()
            if s.empty:
                print(f"  ✗ {key:<15} | {spec['name_bg']:<50} | ЛИПСВАТ ДАННИ")
                continue
            last_date = s.index[-1].strftime("%Y-%m-%d")
            last_val = s.iloc[-1]
            n_raw = len(snapshot[key].dropna())
            print(f"  ✓ {key:<15} | {spec['name_bg']:<50} | {last_date}: {last_val:>8.2f} | n={n_raw}")
        else:
            print(f"  ✗ {key:<15} | {spec['name_bg']:<50} | ЛИПСВАТ ДАННИ")

    return 0

from export.weekly_briefing import generate_html

def main():
    parser = argparse.ArgumentParser(description="Bulgarian Macro Dashboard")
    parser.add_argument("--status", action="store_true", help="Показва статуса на данните")
    parser.add_argument("--briefing", action="store_true", help="Генерира HTML дашборд")
    parser.add_argument("--refresh", action="store_true", help="Форсира обновяване на данните")
    
    args = parser.parse_args()

    catalog_errors = validate_catalog()
    if catalog_errors:
        print("❌ Каталогът не е валиден:")
        for err in catalog_errors:
            print(f"  • {err}")
        return 1

    if args.status or not any(vars(args).values()):
        return cmd_status(args)
        
    if args.briefing:
        adapters = build_adapters()
        snapshot = _build_snapshot(adapters, force=args.refresh)
        module_scores = compute_module_scores(SERIES_CATALOG, snapshot)
        composite = compute_composite_score(module_scores)
        regime = get_regime(composite)
        
        output_file = BASE_DIR / "output" / "index.html"
        generate_html(snapshot, module_scores, composite, regime, str(output_file))
        return 0
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
