import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
import pytest
from acp.prices import DEFAULT, NOTE, PriceError, load_prices, row_cost
from acp.ingest import SchemaError, ingest, read_store
from acp.report import BANNER, GroupingError, aggregate, render_report
from acp.outliers import render_outliers
from acp.fixtures import generate_rows, write_fixtures


def row(**changes):
    value = dict(agent="a", mission="m", tokens_in=1000, tokens_out=1000,
                 api_calls=1, wall_s=3600.0, outcome="success", ts="2026-09-30T00:00:00Z")
    value.update(changes)
    return value


def write_rows(tmp_path, rows):
    source = tmp_path / "input.jsonl"
    source.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    prices = tmp_path / "prices.json"
    prices.write_text(json.dumps(DEFAULT), encoding="utf-8")
    return source, prices


def test_cost_math_hand_computed():
    # 0.01 + 0.03 + 0.02 + 0.5 = 0.56
    # 0.02 + 0.015 + 0.06 + 0.25 = 0.345
    # All zero usage costs zero.
    assert row_cost(row(), DEFAULT) == 0.5600
    assert row_cost(row(tokens_in=2000, tokens_out=500, api_calls=3, wall_s=1800), DEFAULT) == 0.3450
    assert row_cost(row(tokens_in=0, tokens_out=0, api_calls=0, wall_s=0), DEFAULT) == 0.0000


@pytest.mark.parametrize("change,field", [({"tokens_in": "1"}, "tokens_in"), ({"outcome": "unknown"}, "outcome"), ({"agent": None}, "agent")])
def test_ingest_validates_schema(tmp_path, change, field):
    source, prices = write_rows(tmp_path, [row(), row(**change)])
    with pytest.raises(SchemaError, match=f"line 2: {field}"):
        ingest(source, prices, tmp_path / "store")


def test_missing_field(tmp_path):
    bad = row(); del bad["mission"]
    source, prices = write_rows(tmp_path, [bad])
    with pytest.raises(SchemaError, match="line 1: missing field mission"):
        ingest(source, prices, tmp_path / "store")


def test_ingest_aborts_on_bad_row(tmp_path):
    source, prices = write_rows(tmp_path, [row(), row(tokens_in=-1)])
    store = tmp_path / "store"
    with pytest.raises(SchemaError, match="line 2"):
        ingest(source, prices, store)
    assert not store.exists()
    source, prices = write_rows(tmp_path, [row()])
    ingest(source, prices, store)
    before = (store / "runs.json").read_bytes()
    source, prices = write_rows(tmp_path, [row(), row(tokens_in=-1)])
    with pytest.raises(SchemaError):
        ingest(source, prices, store)
    assert (store / "runs.json").read_bytes() == before


@pytest.fixture
def sample():
    # Each mission: 2 successes, 1 failure, 1 null. Costs 1,2,3,4.
    return [dict(row(agent="a" if i % 2 == 0 else "b", mission=m,
                     outcome=("success", "success", "failed", None)[i]), cost_usd=i+1)
            for m in ("one", "two", "three") for i in range(4)]


def test_report_by_mission(sample):
    groups = aggregate(sample)
    assert [g["name"] for g in groups] == ["one", "three", "two"]
    for g in groups:
        assert (g["runs"], g["total"], g["successes"], g["failures"], g["unattributed"], g["per_success"]) == (4, 10, 2, 1, 4, 3)


def test_report_by_agent(sample):
    groups = {g["name"]: g for g in aggregate(sample, "agent")}
    assert groups["a"]["total"] == 12
    assert groups["a"]["successes"] == 3
    assert groups["a"]["per_success"] == 4
    assert groups["b"]["total"] == 18
    assert groups["b"]["unattributed"] == 12
    assert groups["b"]["per_success"] == 2


def test_unattributed_flagged(sample):
    assert "UNATTRIBUTED | one | USD 4.0000" in render_report(sample)
    assert aggregate(sample)[0]["per_success"] == 3


def test_outliers_threshold(tmp_path):
    write_fixtures(tmp_path)
    rows = ingest(tmp_path / "runs.jsonl", tmp_path / "prices.json", tmp_path / "store")
    text = render_outliers(rows, 10.0)
    ranked = text.split("OUTLIERS | mission | USD per success\n")[1].split("NO-OUTCOME")[0].splitlines()
    assert [line.split(" | ")[0] for line in ranked] == ["expensive-planning", "expensive-search"]
    boundary = [dict(row(mission="boundary"), cost_usd=10.0)]
    assert "boundary" not in render_outliers(boundary, 10.0)


def test_no_success_missions_listed_separately():
    rows = [dict(row(outcome="failed"), cost_usd=20)]
    assert aggregate(rows)[0]["per_success"] is None
    assert "n/a" in render_report(rows)
    assert render_outliers(rows).endswith("NO-OUTCOME | mission | USD total\nm | 20.0000\n")


def test_prices_carries_honesty_note():
    assert load_prices()["note"] == NOTE
    assert load_prices("prices.json")["note"] == NOTE


def test_report_carries_honesty_banner(sample):
    assert render_report(sample).startswith(BANNER)
    assert render_outliers(sample).startswith(BANNER)


def test_fixtures_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    write_fixtures(a); write_fixtures(b)
    for name in ("runs.jsonl", "prices.json"):
        assert (a / name).read_bytes() == (b / name).read_bytes()
        assert "SYNTHETIC" in (a / name).read_text(encoding="utf-8").splitlines()[0 if name.endswith('jsonl') else 1]
    rows = generate_rows()
    assert len(rows) == 120
    assert len({r["mission"] for r in rows}) == 6
    assert len({r["agent"] for r in rows}) == 3
    assert any(r["outcome"] is None for r in rows)


@pytest.mark.parametrize("changes", [{"tokens_in": -1}, {"tokens_out": True}, {"api_calls": 1.2}, {"wall_s": float("nan")}, {"wall_s": -1}, {"mission": ""}])
def test_adversarial_schema(tmp_path, changes):
    source, prices = write_rows(tmp_path, [row(**changes)])
    with pytest.raises(SchemaError, match="line 1"):
        ingest(source, prices, tmp_path / "store")


def test_large_token_counts(tmp_path):
    source, prices = write_rows(tmp_path, [row(tokens_in=10_000_000_000, tokens_out=10_000_000_000)])
    assert ingest(source, prices, tmp_path / "store")[0]["cost_usd"] == 400000.5200


def test_unicode_and_replacement(tmp_path):
    source, prices = write_rows(tmp_path, [row(agent="代理🤖", mission="évaluation")])
    store = tmp_path / "store"
    ingest(source, prices, store)
    before = (store / "runs.json").read_bytes()
    report = render_report(read_store(store)).encode("utf-8")
    ingest(source, prices, store)
    assert (store / "runs.json").read_bytes() == before
    assert len(read_store(store)) == 1
    assert render_report(read_store(store)).encode("utf-8") == report
    assert "代理🤖" in before.decode("utf-8")


def test_unknown_grouping(sample):
    with pytest.raises(GroupingError, match="legal values are mission, agent"):
        aggregate(sample, "wrong")


@pytest.mark.parametrize("value", [-1, True, float("inf"), "0.1"])
def test_negative_invalid_prices(tmp_path, value):
    prices = dict(DEFAULT, per_api_call_usd=value)
    path = tmp_path / "p.json"; path.write_text(json.dumps(prices))
    with pytest.raises(PriceError):
        load_prices(path)


def test_invalid_json_line_number(tmp_path):
    source, prices = write_rows(tmp_path, [row()])
    source.write_text(source.read_text() + "bad\n")
    with pytest.raises(SchemaError, match="line 2: invalid JSON"):
        ingest(source, prices, tmp_path / "store")


def cli(*args):
    return subprocess.run([sys.executable, "-m", "acp.cli", *map(str, args)], capture_output=True, text=True, encoding="utf-8")


@pytest.mark.parametrize("command", ["ingest", "report", "outliers", "prices", "fixtures"])
def test_cli_help(command):
    result = cli(command, "--help")
    assert result.returncode == 0
    assert "usage:" in result.stdout


def test_cli_smoke_end_to_end(tmp_path):
    assert cli("fixtures", "--out", tmp_path).returncode == 0
    result = cli("ingest", tmp_path / "runs.jsonl", "--prices", tmp_path / "prices.json", "--store", tmp_path / "store")
    assert result.returncode == 0 and "120" in result.stdout
    report = cli("report", "--by", "mission", "--store", tmp_path / "store")
    assert report.returncode == 0 and BANNER in report.stdout and "UNATTRIBUTED" in report.stdout
    assert cli("report", "--by", "agent", "--store", tmp_path / "store").returncode == 0
    assert cli("outliers", "--threshold", "10.0", "--store", tmp_path / "store").returncode == 0
    assert NOTE in cli("prices").stdout
    bad = cli("report", "--by", "wrong", "--store", tmp_path / "store")
    assert bad.returncode == 2 and "GroupingError" in bad.stderr and "mission, agent" in bad.stderr
    # Independently price fixture usage with Decimal and compare every group.
    rows = read_store(tmp_path / "store")
    for g in aggregate(rows):
        selected = [r for r in generate_rows() if r["mission"] == g["name"]]
        costs = [(Decimal(r["tokens_in"])/1000*Decimal("0.01") + Decimal(r["tokens_out"])/1000*Decimal("0.03") + Decimal(r["api_calls"])*Decimal("0.02") + Decimal(str(r["wall_s"]))/3600*Decimal("0.5")).quantize(Decimal("0.0001")) for r in selected]
        total = sum(costs)
        null = sum(c for r, c in zip(selected, costs) if r["outcome"] is None)
        successes = sum(r["outcome"] == "success" for r in selected)
        assert g["total"] == total and g["unattributed"] == null
        assert g["per_success"] == (total-null)/successes
    assert report.stdout == cli("report", "--store", tmp_path / "store").stdout


@pytest.mark.parametrize("limit", [-1, float("nan"), float("inf")])
def test_invalid_threshold(limit):
    with pytest.raises(ValueError, match="threshold"):
        render_outliers([], limit)


def test_empty_report():
    assert BANNER in render_report([])
    assert "NO-OUTCOME" in render_outliers([])
