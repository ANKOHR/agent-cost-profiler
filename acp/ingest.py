"""Abort-first validation with atomic replacement of a complete store."""
import json
import math
import os
import tempfile
from pathlib import Path
from .prices import load_prices, row_cost

class SchemaError(ValueError):
    """A malformed JSONL row, with its physical line number."""

FIELDS = {"agent", "mission", "tokens_in", "tokens_out", "api_calls", "wall_s", "outcome", "ts"}

def validate_row(row, line):
    def fail(message):
        raise SchemaError(f"line {line}: {message}")
    if not isinstance(row, dict):
        fail("expected object")
    for key in sorted(FIELDS):
        if key not in row:
            fail(f"missing field {key}")
    for key in ("agent", "mission", "ts"):
        if not isinstance(row[key], str) or not row[key].strip():
            fail(f"{key}: expected nonempty string")
    for key in ("tokens_in", "tokens_out", "api_calls"):
        if type(row[key]) is not int or row[key] < 0:
            fail(f"{key}: expected nonnegative integer")
    if type(row["wall_s"]) not in (int, float) or not math.isfinite(row["wall_s"]) or row["wall_s"] < 0:
        fail("wall_s: expected finite nonnegative number")
    if row["outcome"] is not None and row["outcome"] not in ("success", "failed"):
        fail("outcome: expected success, failed, or null")
    return {key: row[key] for key in sorted(FIELDS)}

def ingest(source, prices_path, store):
    prices = load_prices(prices_path)
    rows = []
    with Path(source).open(encoding="utf-8") as stream:
        for line, text in enumerate(stream, 1):
            if text.startswith("# SYNTHETIC"):
                continue
            try:
                row = json.loads(text)
            except ValueError as exc:
                raise SchemaError(f"line {line}: invalid JSON") from exc
            row = validate_row(row, line)
            row["cost_usd"] = row_cost(row, prices)
            rows.append(row)
    payload = json.dumps({"prices": prices, "rows": rows}, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    directory = Path(store)
    directory.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".acp-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
        os.replace(temporary, directory / "runs.json")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return rows

def read_store(store):
    return json.loads((Path(store) / "runs.json").read_text(encoding="utf-8"))["rows"]
