"""
run.py
======
Entry point за Bulgarian Macro Dashboard.
"""
import argparse
import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Add to path
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from sources import build_adapters
from catalog.series import SERIES_CATALOG, series_by_source
from core.scorer import compute_module_scores, compute_composite_score, get_regime

def _build_snapshot(adapters: dict, force: bool = False) -> dict:
    """Сглобява snapshot от всички серии."""
    snapshot = {}
    for source_name, adapter in adapters.items():
        specs = series_by_source(source_name)
        if not specs:
            continue
            
        if force:
            results = adapter.fetch_many(specs, force=True)
        else:
            results = adapter.get_snapshot([s["_key"] for s in specs])
            # Fetch missing
            missing = [s for s in specs if s["_key"] not in results]
            if missing:
                new_results = adapter.fetch_many(missing, force=False)
                results.update(new_results)
                
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
        
    print("\nПоследни данни по серии:")
    for key, spec in SERIES_CATALOG.items():
        if key in snapshot and not snapshot[key].empty:
            s = snapshot[key]
            last_date = s.index[-1].strftime("%Y-%m-%d")
            last_val = s.iloc[-1]
            print(f"  ✓ {key:<15} | {spec['name_bg']:<45} | {last_date}: {last_val:.2f}")
        else:
            print(f"  ✗ {key:<15} | {spec['name_bg']:<45} | ЛИПСВАТ ДАННИ")
            
    return 0

from export.weekly_briefing import generate_html

def main():
    parser = argparse.ArgumentParser(description="Bulgarian Macro Dashboard")
    parser.add_argument("--status", action="store_true", help="Показва статуса на данните")
    parser.add_argument("--briefing", action="store_true", help="Генерира HTML дашборд")
    parser.add_argument("--refresh", action="store_true", help="Форсира обновяване на данните")
    
    args = parser.parse_args()
    
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
