"""
run.py
======
Entry point за Bulgarian Macro Dashboard.
"""
import argparse
import sys
import logging
from datetime import date
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
from sources.manual_seed import splice_loans
from analysis.temperature import temperature
from analysis.tension import annihilation, ratio_str
from catalog.series import SERIES_CATALOG, series_by_source, validate_catalog
from core.primitives import apply_transform
from core.scorer import (
    compute_composite_score,
    compute_lens_reports,
    get_regime,
)

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


def _score_everything(force: bool = False) -> tuple[dict, dict, float | None, dict]:
    """snapshot → лещови доклади → композит → режим. Единният път на всички команди."""
    adapters = build_adapters()
    snapshot = _build_snapshot(adapters, force=force)
    # Дългата кредитна памет — ЕДНО място за всички консуматори (status, HTML,
    # context export): БНБ seed 2005Q4+ отпред, завършените ЕЦБ BSI тримесечия
    # отзад, шевът валидиран (sources/manual_seed.py).
    snapshot = splice_loans(snapshot)
    lens_reports = compute_lens_reports(SERIES_CATALOG, snapshot)
    module_scores = {lens: rep["score"] for lens, rep in lens_reports.items()}
    composite = compute_composite_score(module_scores)
    regime = get_regime(composite)
    return snapshot, lens_reports, composite, regime


def _fmt(score) -> str:
    return f"{score:.1f}" if score is not None else "—"


def cmd_status(args):
    """Показва статуса на данните."""
    print(f"📊 Catalog: {len(SERIES_CATALOG)} series")

    snapshot, lens_reports, composite, regime = _score_everything(force=args.refresh)

    print(f"\n📈 Извлечени: {len(snapshot)} / {len(SERIES_CATALOG)} серии")

    print("\n" + "="*40)
    print(f"🌍 ТЕКУЩ МАКРО РЕЖИМ: {regime['name']} (Score: {_fmt(composite)}/100)")
    print("="*40)
    print("Скала: 50 = близката 10-годишна норма (робастен z, tanh); "
          "инфлацията се мери като отклонение от 2%.")

    # Температурният слой (мандат №47) — колко бум-серии са над зоната си.
    temp = temperature(SERIES_CATALOG, snapshot)
    hot_str = " · ".join(
        f"{e['key']} {e['value']:.1f} > {e['hi']:.0f}" for e in temp["hot"]
    ) or "нито една над зоната си"
    print(f"🌡 Прегряване: {temp['n_hot']}/{temp['n_total']} ({hot_str})")

    # Тензионният слой (мандат №51) — колко от лещовата енергия се погасява.
    tension = annihilation(lens_reports)
    print(f"⚖ Погасяване (К1): {ratio_str(tension)} — {tension['sentence']}")

    for lens, rep in lens_reports.items():
        z = rep["health_z"]
        z_str = f"z={z:+.2f}" if z is not None else "няма данни"
        n = rep["n_series"]
        print(f"  • {lens.capitalize():<10}: {_fmt(rep['score']):>5}   ({z_str}, "
              f"{n} {'серия' if n == 1 else 'серии'})")

    print("\nПоследни данни по серии (след трансформацията от каталога):")
    for key, spec in SERIES_CATALOG.items():
        res = next(
            (s for rep in lens_reports.values() for s in rep["series"] if s["key"] == key),
            None,
        )
        if key in snapshot and not snapshot[key].empty:
            s = apply_transform(snapshot[key], spec["transform"]).dropna()
            if s.empty:
                print(f"  ✗ {key:<15} | {spec['name_bg']:<50} | ЛИПСВАТ ДАННИ")
                continue
            last_date = s.index[-1].strftime("%Y-%m-%d")
            last_val = s.iloc[-1]
            n_raw = len(snapshot[key].dropna())
            score_str = _fmt(res["score"]) if res else "—"
            print(f"  ✓ {key:<15} | {spec['name_bg']:<50} | {last_date}: {last_val:>8.2f} "
                  f"| score={score_str:>5} | n={n_raw}")
        else:
            print(f"  ✗ {key:<15} | {spec['name_bg']:<50} | ЛИПСВАТ ДАННИ")

    return 0


def cmd_briefing(args):
    """Генерира HTML дашборда + обновява историята и живия журнал."""
    from export.weekly_briefing import generate_html
    from analysis.lens_history import (
        append_journal, build_history, load_journal, wow_delta, write_history,
    )

    snapshot, lens_reports, composite, regime = _score_everything(force=args.refresh)

    # Реконструираната история се пресмята от СЪЩИЯ snapshot — последният ѝ ред
    # е тъждествен на живото изчисление отгоре (вкл. `temp_count`).
    history = build_history(SERIES_CATALOG, snapshot)
    write_history(history)

    temp = temperature(SERIES_CATALOG, snapshot)

    # РЕДЪТ Е ВАЖЕН: append ПРЕДИ wow. Записът за днес се ЗАМЕНЯ при повторен
    # пуск, а делтата се чете спрямо предишната ДАТА — така вторият пуск в
    # същия ден показва същото, а не нула.
    append_journal(lens_reports, composite, temp=temp)
    wow = wow_delta(load_journal())

    output_file = BASE_DIR / "output" / "index.html"
    generate_html(snapshot, lens_reports, composite, regime, str(output_file),
                  history=history, wow=wow, temp=temp,
                  tension=annihilation(lens_reports))
    return 0


def cmd_export_context(args):
    """Markdown context за LLM анализ (горивото на macro-deep-brief-bg)."""
    from export.briefing_context import generate_briefing_context
    from analysis.lens_history import build_history, load_journal, wow_delta

    snapshot, lens_reports, composite, regime = _score_everything(force=args.refresh)
    if not snapshot:
        print("⚠ Snapshot е празен. Пусни `python run.py --status --refresh` първо.")
        return 1

    # Историята се смята in-memory и НЕ се записва, журналът се ЧЕТЕ и НЕ се
    # дописва: записът е на ритуалния момент (`--briefing`), а експортът на
    # контекста е четец. Иначе двете команди щяха да раждат по един запис на ден
    # и WoW делтата щеше да сравнява себе си със себе си.
    history = build_history(SERIES_CATALOG, snapshot)
    wow = wow_delta(load_journal())

    today = date.today()
    output_file = BASE_DIR / "output" / f"briefing_context_{today.isoformat()}.md"
    generate_briefing_context(
        snapshot=snapshot,
        lens_reports=lens_reports,
        composite=composite,
        regime=regime,
        output_path=str(output_file),
        today=today,
        history=history,
        wow=wow,
        temp=temperature(SERIES_CATALOG, snapshot),
        tension=annihilation(lens_reports),
    )
    return 0


def main():
    parser = argparse.ArgumentParser(description="Bulgarian Macro Dashboard")
    parser.add_argument("--status", action="store_true", help="Показва статуса на данните")
    parser.add_argument("--briefing", action="store_true", help="Генерира HTML дашборд")
    parser.add_argument("--export-context", action="store_true",
                        help="Генерира output/briefing_context_YYYY-MM-DD.md за LLM анализ")
    parser.add_argument("--refresh", action="store_true", help="Форсира обновяване на данните")

    args = parser.parse_args()

    catalog_errors = validate_catalog()
    if catalog_errors:
        print("❌ Каталогът не е валиден:")
        for err in catalog_errors:
            print(f"  • {err}")
        return 1

    if args.briefing:
        return cmd_briefing(args)

    if args.export_context:
        return cmd_export_context(args)

    return cmd_status(args)

if __name__ == "__main__":
    sys.exit(main())
