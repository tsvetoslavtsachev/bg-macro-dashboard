"""
tests/test_docs.py
==================
Пазачи срещу мандат-док дрейфа (док-одитът 29.07.2026).

Класът на грешката: мандатът сменя кода, а README/AGENT.md остават на старата
снимка — „тихата неистина живее мандат-два". Прецедентите, които родиха всеки
пин, стоят в докстринга му. Моделът е №47 (`test_polarity.py` чете README) и
№52 (`test_catalog.py` брои от каталога): пазачът чете ЖИВИЯ код и съди текста,
не преписано число.
"""
import re
from pathlib import Path

from analysis.lens_history import history_columns
from config import MODULE_WEIGHTS

ROOT = Path(__file__).parents[1]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_the_docs_describe_the_composition_format_not_a_snapshot():
    """№51 смени тага 20s7l → 21s7l и двата документа лъгаха до док-одита.

    Форматът е динамичен (`composition_tag` го строи от каталога и теглата),
    затова документите описват ФОРМАТА `<N>s<M>l-<sha1[:8]>` — снимка-литерал
    се чупи тихо при всеки мандат, който пипа състава.
    """
    for name in ("README.md", "AGENT.md"):
        text = _read(name)
        assert "<N>s<M>l-" in text, name
        assert re.search(r"\b\d+s\d+l-", text) is None, (
            f"{name} държи снимка на тага вместо формата"
        )


def test_the_readme_lists_every_history_column():
    """№47 и №51 добавиха колони на решетката; README ги научи чак на одита.

    Родовите `z_<леща>` / `score_<леща>` се покриват от описанието им, всичко
    останало се изброява поименно — новата колона на следващия мандат ще падне
    тук, не в тихо разминаване.
    """
    readme = _read("README.md")
    generated = {f"z_{lens}" for lens in MODULE_WEIGHTS} | {
        f"score_{lens}" for lens in MODULE_WEIGHTS
    }
    for col in history_columns():
        if col in generated:
            continue
        assert f"`{col}`" in readme, col


def test_agent_md_knows_every_module():
    """№51 роди `analysis/tension.py`; архитектурата в AGENT.md го научи чак
    на док-одита. Пазачът: всеки публичен модул присъства в AGENT.md по име
    (private `_`-модулите и `__init__` са вътрешна кухня и не се изброяват).
    """
    agent = _read("AGENT.md")
    packages = ("catalog", "analysis", "sources", "core", "export", "scripts")
    modules = [
        p.name
        for pkg in packages
        for p in sorted((ROOT / pkg).glob("*.py"))
        if not p.name.startswith("_")
    ]
    modules += ["run.py", "config.py"]
    for name in modules:
        assert name in agent, name
