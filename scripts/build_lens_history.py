"""
scripts/build_lens_history.py
=============================
Ръчният билд на реконструираната лещова история (мандат №45, П1).

Тънък CLI около `analysis/lens_history.py`: snapshot по СЪЩИЯ път като всички
останали команди (`_build_snapshot` + `splice_loans`), после решетката и
записът в `data/lens_history.parquet`.

⚠ БЕЗ журнален запис. Живият журнал (`data/score_journal.csv`) е ЗАПИС НА
РИТУАЛНИЯ МОМЕНТ и се пише само от `run.py --briefing`. Ако този скрипт
дописваше журнала, всеки експериментален билд щеше да ражда фалшив „запис от
днес" и WoW делтата щеше да лъже.

Пуск:
    PYTHONUTF8=1 python scripts/build_lens_history.py
    PYTHONUTF8=1 python scripts/build_lens_history.py --refresh   # дърпа данни
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from analysis.lens_history import (  # noqa: E402
    HISTORY_PATH,
    HONESTY_LABEL,
    build_history,
    history_stats,
    write_history,
)
from catalog.series import SERIES_CATALOG  # noqa: E402
from run import _build_snapshot  # noqa: E402
from sources import build_adapters  # noqa: E402
from sources.manual_seed import splice_loans  # noqa: E402


def _fmt(v) -> str:
    return f"{v:.1f}" if v is not None else "—"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Билд на реконструираната лещова история (parquet)."
    )
    parser.add_argument("--refresh", action="store_true",
                        help="Форсира обновяване на данните преди билда")
    parser.add_argument("--out", default=str(HISTORY_PATH),
                        help=f"Изходен parquet (по подразбиране {HISTORY_PATH})")
    args = parser.parse_args()

    snapshot = _build_snapshot(build_adapters(), force=args.refresh)
    snapshot = splice_loans(snapshot)

    df = build_history(SERIES_CATALOG, snapshot)
    if df.empty:
        print("⚠ Празна решетка — няма нито една серия с данни.")
        return 1

    path = write_history(df, args.out)
    stats = history_stats(df)

    print(f"\n✅ Лещовата история е записана: {path}")
    print(f"   {HONESTY_LABEL}")
    print(f"\n   Редове: {len(df)} "
          f"({int((df['row_type'] == 'quarter').sum())} тримесечни + "
          f"{int((df['row_type'] == 'live').sum())} жив)")
    print(f"   Обхват: {df.index[0].date()} → {df.index[-1].date()}")
    if stats:
        print(f"   Композит min: {_fmt(stats['min_value'])} на {stats['min_date']}")
        print(f"   Композит max: {_fmt(stats['max_value'])} на {stats['max_date']}")
        print(f"   Текущият композит е над {_fmt(stats['percentile'])}% "
              f"от {stats['n_quarters']} тримесечни точки")

    last = df.iloc[-1]
    lens_bits = " · ".join(
        f"{col[len('score_'):]} {_fmt(last[col])}"
        for col in df.columns if col.startswith("score_")
    )
    print(f"\n   Последен ред ({df.index[-1].date()}, {last['row_type']}): "
          f"композит {_fmt(last['composite'])}")
    print(f"   {lens_bits}")
    print(f"   n_series={last['n_series']} · n_lenses={last['n_lenses']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
