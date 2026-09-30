"""Command line interface."""
import argparse
import json
import sys
from .ingest import ingest, read_store
from .prices import load_prices
from .report import render_report
from .outliers import render_outliers
from .fixtures import write_fixtures

def main(argv=None):
    parser = argparse.ArgumentParser(prog="acp", description="Cost attribution with illustrative prices and synthetic demo data")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("ingest", help="Validate and atomically replace stored rows")
    p.add_argument("source")
    p.add_argument("--prices", required=True)
    p.add_argument("--store", default="store")
    p = commands.add_parser("report", help="Report usage attribution")
    p.add_argument("--by", default="mission")
    p.add_argument("--store", default="store")
    p = commands.add_parser("outliers", help="Rank expensive missions")
    p.add_argument("--threshold", type=float, default=10.0)
    p.add_argument("--store", default="store")
    p = commands.add_parser("prices", help="Display price table and honesty note")
    p.add_argument("--prices")
    p = commands.add_parser("fixtures", help="Generate SYNTHETIC seed 41 fixtures")
    p.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "ingest":
            rows = ingest(args.source, args.prices, args.store)
            print(f"Stored {len(rows)} runs (replaced previous snapshot).")
        elif args.command == "report":
            print(render_report(read_store(args.store), args.by), end="")
        elif args.command == "outliers":
            print(render_outliers(read_store(args.store), args.threshold), end="")
        elif args.command == "prices":
            print(json.dumps(load_prices(args.prices), sort_keys=True, indent=2))
        else:
            write_fixtures(args.out)
            print("SYNTHETIC fixtures written; seed 41; 120 runs.")
    except (ValueError, OSError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    sys.exit(main())
