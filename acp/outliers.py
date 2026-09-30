"""Mission outliers and explicit zero-success listings."""
from decimal import Decimal
from .report import aggregate, BANNER, money

def render_outliers(rows, threshold=10.0):
    limit = Decimal(str(threshold))
    if not limit.is_finite() or limit < 0:
        raise ValueError("threshold: expected finite nonnegative number")
    groups = aggregate(rows)
    ranked = sorted((g for g in groups if g["per_success"] is not None and g["per_success"] > limit), key=lambda g: (-g["per_success"], g["name"]))
    lines = [BANNER, f"Threshold: USD {money(limit)}", "OUTLIERS | mission | USD per success"]
    lines.extend(f'{g["name"]} | {money(g["per_success"])}' for g in ranked)
    lines.append("NO-OUTCOME | mission | USD total")
    lines.extend(f'{g["name"]} | {money(g["total"])}' for g in groups if g["successes"] == 0)
    return "\n".join(lines) + "\n"
