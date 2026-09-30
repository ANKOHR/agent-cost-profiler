"""Validated illustrative price tables and usage pricing."""
import json
import math
from decimal import Decimal, InvalidOperation
from pathlib import Path

NOTE = "Example prices for demonstration. Not real vendor rates."
DEFAULT = dict(per_1k_input_usd=0.01, per_1k_output_usd=0.03,
               per_api_call_usd=0.02, per_wall_hour_usd=0.5, note=NOTE)
KEYS = tuple(k for k in DEFAULT if k != "note")

class PriceError(ValueError):
    """Invalid price table."""

def validate_prices(prices):
    if not isinstance(prices, dict):
        raise PriceError("price table must be an object")
    for key in KEYS:
        value = prices.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise PriceError(f"{key}: expected a finite nonnegative number")
    if not isinstance(prices.get("note"), str) or not prices["note"].strip():
        raise PriceError("note: expected nonempty string")
    return prices

def load_prices(path=None):
    try:
        return validate_prices(json.loads(Path(path).read_text(encoding="utf-8")) if path else DEFAULT.copy())
    except (OSError, ValueError) as exc:
        raise PriceError(str(exc)) from exc

def row_cost(row, prices):
    try:
        value = (Decimal(row["tokens_in"]) / 1000 * Decimal(str(prices["per_1k_input_usd"]))
                 + Decimal(row["tokens_out"]) / 1000 * Decimal(str(prices["per_1k_output_usd"]))
                 + Decimal(row["api_calls"]) * Decimal(str(prices["per_api_call_usd"]))
                 + Decimal(str(row["wall_s"])) / 3600 * Decimal(str(prices["per_wall_hour_usd"])))
        result = float(value.quantize(Decimal("0.0001")))
    except (InvalidOperation, OverflowError) as exc:
        raise PriceError("computed cost exceeds supported precision") from exc
    if not math.isfinite(result):
        raise PriceError("computed cost is not finite")
    return result
