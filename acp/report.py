"""Stable cost attribution summaries."""
from decimal import Decimal

BANNER = "Prices are illustrative examples, not real vendor rates. Run data is synthetic."

class GroupingError(ValueError):
    """Unsupported grouping."""

def aggregate(rows, by="mission"):
    if by not in ("mission", "agent"):
        raise GroupingError("--by: legal values are mission, agent")
    groups = {}
    for row in rows:
        group = groups.setdefault(row[by], dict(name=row[by], runs=0, total=Decimal(0), successes=0, failures=0, unattributed=Decimal(0)))
        cost = Decimal(str(row["cost_usd"]))
        group["runs"] += 1
        group["total"] += cost
        if row["outcome"] is None:
            group["unattributed"] += cost
        else:
            group["successes" if row["outcome"] == "success" else "failures"] += 1
    for group in groups.values():
        group["per_success"] = ((group["total"] - group["unattributed"]) / group["successes"] if group["successes"] else None)
    return sorted(groups.values(), key=lambda g: (-g["total"], g["name"]))

def money(value):
    return "n/a" if value is None else f"{value:.4f}"

def render_report(rows, by="mission"):
    groups = aggregate(rows, by)
    lines = [BANNER, f"By {by} | USD", "name | runs | total | successes | failures | unattributed | per success"]
    for g in groups:
        lines.append(f'{g["name"]} | {g["runs"]} | {money(g["total"])} | {g["successes"]} | {g["failures"]} | {money(g["unattributed"])} | {money(g["per_success"])}')
        if g["unattributed"]:
            lines.append(f'UNATTRIBUTED | {g["name"]} | USD {money(g["unattributed"])}')
    missions = aggregate(rows, "mission")
    if missions:
        weakest = sorted(missions, key=lambda g: (-g["unattributed"], g["name"]))[0]
        total = sum(g["total"] for g in missions)
        share = weakest["unattributed"] / total * 100 if total else Decimal(0)
        lines.append(f'Highest unattributed spend: {weakest["name"]} | USD {money(weakest["unattributed"])} | {share:.4f}% of total spend')
    return "\n".join(lines) + "\n"
