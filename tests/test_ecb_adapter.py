"""
tests/test_ecb_adapter.py
=========================
ECB Data Portal адаптерът (мандат №39 §А1).

Всичко тук е върху ФИКСТУРА, не върху живия API — тестът пази parser-а и
адресната конвенция, а не наличността на ЕЦБ. Живата сверка е задача на
`run.py --status --refresh`.
"""
import pandas as pd
import pytest

from sources.ecb_adapter import EcbAdapter, parse_ecb_period, parse_sdmx_json


def _payload(periods, values):
    """Минималната SDMX-JSON 1.0 форма, която порталът връща."""
    return {
        "dataSets": [{
            "series": {
                "0:0:0": {"observations": {str(i): [v] for i, v in enumerate(values)}}
            }
        }],
        "structure": {
            "dimensions": {"observation": [{"values": [{"id": p} for p in periods]}]}
        },
    }


# ── Периоди ──────────────────────────────────────────────────────────────────

def test_monthly_period_becomes_the_first_of_the_month():
    assert parse_ecb_period("2026-05") == pd.Timestamp("2026-05-01")


def test_quarterly_period_becomes_the_first_of_the_quarter():
    assert parse_ecb_period("2026-Q1") == pd.Timestamp("2026-01-01")
    assert parse_ecb_period("2026-Q4") == pd.Timestamp("2026-10-01")


def test_annual_and_daily_periods_parse():
    assert parse_ecb_period("2026") == pd.Timestamp("2026-01-01")
    assert parse_ecb_period("2026-05-15") == pd.Timestamp("2026-05-15")


def test_unknown_period_returns_none_instead_of_raising():
    for bad in ("", "   ", "не-период", None):
        assert parse_ecb_period(bad) is None


# ── Parser ───────────────────────────────────────────────────────────────────

def test_parser_reads_the_bsi_fixture_into_a_dated_series():
    payload = _payload(["2022-01", "2022-02", "2022-03"],
                       [19404.92, 19703.12, 19932.95])
    s = parse_sdmx_json(payload)

    assert len(s) == 3
    assert s.index[0] == pd.Timestamp("2022-01-01")
    assert s.iloc[-1] == pytest.approx(19932.95)
    assert s.index.is_monotonic_increasing


def test_parser_skips_null_observations():
    payload = _payload(["2026-03", "2026-04", "2026-05"], [28520.14, None, 28757.69])
    s = parse_sdmx_json(payload)

    assert len(s) == 2
    assert pd.Timestamp("2026-04-01") not in s.index


def test_parser_returns_empty_series_for_an_empty_response():
    assert parse_sdmx_json({}).empty
    assert parse_sdmx_json({"dataSets": []}).empty
    assert parse_sdmx_json({"dataSets": [{"series": {}}]}).empty


def test_parser_raises_when_the_observation_dimension_is_missing():
    payload = {
        "dataSets": [{"series": {"0:0:0": {"observations": {"0": [1.0]}}}}],
        "structure": {"dimensions": {}},
    }
    with pytest.raises(ValueError):
        parse_sdmx_json(payload)


def test_parser_rejects_a_non_object_payload():
    with pytest.raises(ValueError):
        parse_sdmx_json([1, 2, 3])


def test_parser_ignores_observations_beyond_the_period_list():
    payload = _payload(["2026-05"], [28757.69])
    payload["dataSets"][0]["series"]["0:0:0"]["observations"]["7"] = [999.0]
    s = parse_sdmx_json(payload)

    assert len(s) == 1
    assert s.iloc[0] == pytest.approx(28757.69)


# ── Адрес ────────────────────────────────────────────────────────────────────

def test_url_splits_the_catalog_id_into_dataset_and_key(tmp_path):
    adapter = EcbAdapter(cache_path=str(tmp_path / "ecb_cache.json"))
    url = adapter._build_url("BSI/M.BG.N.A.A20.A.1.U6.2240.Z01.E")

    assert url.endswith(
        "/data/BSI/M.BG.N.A.A20.A.1.U6.2240.Z01.E?format=jsondata"
    )
    assert url.startswith("https://data-api.ecb.europa.eu/service")


def test_url_rejects_an_id_without_a_dataset(tmp_path):
    adapter = EcbAdapter(cache_path=str(tmp_path / "ecb_cache.json"))
    for bad in ("M.BG.N.A.A20.A.1.U6.2240.Z01.E", "BSI/", "/key", ""):
        with pytest.raises(ValueError):
            adapter._build_url(bad)


def test_adapter_caches_into_its_own_file(tmp_path):
    """Eurostat и ЕЦБ не си делят кеша — различни TTL, различни ключове."""
    adapter = EcbAdapter(cache_path=str(tmp_path / "ecb_cache.json"))
    assert adapter.cache_path.name == "ecb_cache.json"
    assert adapter.SOURCE_NAME == "ecb"


# ── Грешки по мрежата ────────────────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_a_404_is_a_verdict_on_the_key_and_is_not_retried(tmp_path, monkeypatch):
    adapter = EcbAdapter(cache_path=str(tmp_path / "c.json"), retry_backoff=[0, 0])
    calls = []
    monkeypatch.setattr(
        adapter._session, "get",
        lambda url, timeout=None: calls.append(url) or _FakeResponse(404, text="nope"),
    )

    with pytest.raises(ValueError):
        adapter.fetch_series("BSI/M.BG.BAD.KEY")
    assert len(calls) == 1


def test_a_server_error_is_retried_then_surfaces(tmp_path, monkeypatch):
    adapter = EcbAdapter(cache_path=str(tmp_path / "c.json"), retry_backoff=[0, 0])
    calls = []
    monkeypatch.setattr(
        adapter._session, "get",
        lambda url, timeout=None: calls.append(url) or _FakeResponse(503, text="down"),
    )

    with pytest.raises(RuntimeError):
        adapter.fetch_series("BSI/M.BG.N.A.A20.A.1.U6.2240.Z01.E")
    assert len(calls) == 3          # първи опит + два ретрая


def test_invalid_json_is_a_runtime_error_not_a_silent_empty(tmp_path, monkeypatch):
    adapter = EcbAdapter(cache_path=str(tmp_path / "c.json"), retry_backoff=[])
    monkeypatch.setattr(
        adapter._session, "get",
        lambda url, timeout=None: _FakeResponse(200, payload=None),
    )

    with pytest.raises(RuntimeError):
        adapter.fetch_series("BSI/M.BG.N.A.A20.A.1.U6.2240.Z01.E")


def test_a_good_response_becomes_a_series(tmp_path, monkeypatch):
    adapter = EcbAdapter(cache_path=str(tmp_path / "c.json"), retry_backoff=[])
    payload = _payload(["2026-04", "2026-05"], [28644.45, 28757.69])
    monkeypatch.setattr(
        adapter._session, "get",
        lambda url, timeout=None: _FakeResponse(200, payload=payload),
    )

    s = adapter.fetch_series("BSI/M.BG.N.A.A20.A.1.U6.2240.Z01.E")
    assert len(s) == 2
    assert s.iloc[-1] == pytest.approx(28757.69)
