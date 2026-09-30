# Agent Cost Profiler

Every token attributed: what each mission and agent spent, what it produced,
and what burned money with nothing to show. The router decides; the profiler measures.

`acp` validates run logs, prices usage, and reports spend by mission or agent.
It runs on CPU with the Python standard library, without network calls or model APIs.

## Quickstart

Requires Python 3.10 or later. Install from local sources with an existing setuptools
installation; the CLI itself has no runtime dependencies:

```powershell
python -m pip install --no-build-isolation --no-deps -e .
acp fixtures --out demo
acp ingest demo/runs.jsonl --prices demo/prices.json --store demo/store
acp report --by mission --store demo/store
acp outliers --threshold 10.0 --store demo/store
python -m pytest -q
```

Pytest is required only for development. All commands also work via
`python -m acp.cli` instead of `acp`. On Windows, a user install may put
`acp.exe` in a Scripts directory outside PATH; use the module invocation or add
that directory to PATH. Shipped fixture files are in `fixtures/`.

## Architecture

```text
CLI -> fixtures -> synthetic JSONL + illustrative prices
CLI -> prices -> validated price table
CLI -> ingest -> validate every row -> price -> atomic store/runs.json
CLI -> report -> stored rows -> mission or agent attribution
CLI -> outliers -> stored rows -> mission cost per success + NO-OUTCOME
```

Modules correspond to these commands. The store is a single UTF-8 JSON snapshot
containing the price table and enriched rows. No database or service is required.

## Row schema and ingestion

Each data line is a JSON object with these required fields:

```json
{"agent":"alpha","mission":"research","tokens_in":1000,"tokens_out":1000,"api_calls":1,"wall_s":3600.0,"outcome":"success","ts":"2026-09-30T00:00:00Z"}
```

| Field | Validation |
| --- | --- |
| agent, mission, ts | Nonempty strings; Unicode supported |
| tokens_in, tokens_out, api_calls | Nonnegative integers; booleans rejected |
| wall_s | Finite nonnegative number; booleans rejected |
| outcome | `success`, `failed`, or `null` |

`ts` is retained as an opaque string, without timestamp parsing. Additional fields
are ignored. Blank lines and malformed JSON are errors. Fixture JSONL starts with
`# SYNTHETIC`; ingest accepts such header lines as an explicit extension to JSONL.
Physical line numbers include the header. All other lines must be JSON objects.

`SchemaError` names the offending field and line. Ingest aborts on the first bad
row, validates everything before writing, and atomically replaces the snapshot.
An unsuccessful ingest leaves an existing snapshot untouched and creates no new
store. Repeating ingest replaces rather than appends, so spend never doubles.

## Prices and cost formula

The shipped `prices.json` uses these illustrative USD rates:

| Component | Rate |
| --- | ---: |
| 1,000 input tokens | 0.01 |
| 1,000 output tokens | 0.03 |
| API call | 0.02 |
| Wall hour | 0.50 |

```text
cost = tokens_in / 1000 * per_1k_input_usd
     + tokens_out / 1000 * per_1k_output_usd
     + api_calls * per_api_call_usd
     + wall_s / 3600 * per_wall_hour_usd
```

For the schema example: `0.01 + 0.03 + 0.02 + 0.50 = USD 0.5600`.
Rates must be finite nonnegative numbers and a nonempty `note` is required.
Invalid tables raise `PriceError`. Pricing uses Decimal arithmetic, rounds each
row to four decimal places with half-even rounding, and stores the result as a
JSON number. Aggregation converts those stored numbers back to Decimal.
Ten-billion-token counts are supported. JSON floats and finite Decimal context
precision are not arbitrary precision accounting: very large numbers can lose
precision, and unrepresentable costs are rejected. Use this tool for attribution,
not invoice reconciliation.

## Attribution semantics

Reports show runs, total USD, successes, failures, unattributed USD, and USD per
success. Groups sort by total cost descending, then name. Null outcomes are
included in total spend and flagged with a separate `UNATTRIBUTED` line.

The brief contains conflicting requirements: total cost divided by successes,
and a test requiring null-outcome spend to be excluded from per-success cost.
This implementation follows the explicit test requirement:

```text
cost per successful outcome = (total cost - unattributed spend) / successes
```

Failed-run spend remains in that numerator. Zero successes display `n/a`.
Outliers use a strict greater-than threshold and sort by per-success cost descending,
then name. Zero-success missions appear separately under `NO-OUTCOME`.
All money displays four decimal places. Identical inputs produce identical UTF-8
report text, without clocks or environment-specific metadata.

## CLI reference

| Command | Options and behavior |
| --- | --- |
| `acp ingest SOURCE` | `--prices FILE` required; `--store DIR` defaults to `store`; replaces snapshot |
| `acp report` | `--by mission` or `--by agent`; `--store DIR` |
| `acp outliers` | `--threshold 10.0`; `--store DIR`; finite nonnegative threshold |
| `acp prices` | Prints defaults and note; optional `--prices FILE` validates a custom table |
| `acp fixtures` | `--out DIR` required; writes synthetic runs and example prices |

Every subcommand supports `--help`. Invalid grouping raises `GroupingError` listing
`mission, agent`. Expected data or filesystem errors return status 2 with a named
error on stderr; successful commands return 0.

## Fixtures and measured baseline

The generator uses fixed seed **41**, 120 rows, six missions, three agents, and
20 runs per mission. Each mission has 12 successes, four failures and four null
outcomes. Every generated file carries a SYNTHETIC header: a comment for run logs
and a `_header` JSON property for prices. The deliberately expensive missions use
large input-token counts. All timestamps and usage are invented.

The shipped fixture report, checked independently with Decimal cost calculations:

| Mission | Total USD | Unattributed USD | USD per success |
| --- | ---: | ---: | ---: |
| expensive-planning | 401.4572 | 80.2841 | 26.7644 |
| expensive-search | 201.6264 | 40.3416 | 13.4404 |
| summarise | 1.8897 | 0.3224 | 0.1306 |
| index | 1.6911 | 0.3612 | 0.1108 |
| triage | 1.6478 | 0.3268 | 0.1101 |
| research | 1.5052 | 0.2232 | 0.1068 |

At threshold USD 10.0000, the outliers are exactly `expensive-planning` followed
by `expensive-search`. Total spend is USD 609.8174. The first improvement signal,
derived after running the fixture report, is the highest unattributed mission:
`expensive-planning`, USD 80.2841, **13.1653% of total spend**. Every report now
computes this line from its input, including when grouped by agent. This locates
where outcome logging is weakest in the synthetic demonstration.

## HONESTY BOUNDARY

The shipped price table is illustrative, not real vendor pricing. Its note says:
"Example prices for demonstration. Not real vendor rates."
`acp prices` prints that note. Every report and outlier listing carries:
"Prices are illustrative examples, not real vendor rates. Run data is synthetic."

Fixture run logs are synthetic. Cost per outcome is a property of the input data
and example prices, not a claim about any real system. There are no invented
customers, invoices, or savings claims. All baseline numbers above are synthetic.
The banner remains explicit on every report, including user-supplied data; users
should not interpret it as automatic provenance detection.

Future real-data use, not shipped: an operator supplies their own run logs in the
documented schema and a real price table. The tool attributes what those logs
claim. Avoiding double-counted wall time across parallel agents is the operator's
responsibility. This project does not claim to have collected real usage data.

## Validation, positioning, and lessons

The pytest suite covers literal hand-computed row costs, a 12-row attribution
sample, abort-first atomicity, invalid schemas and prices, large token counts,
Unicode, replacement ingestion, deterministic fixtures, strict outlier boundaries,
zero-success missions, honesty labels, every CLI subcommand, and end-to-end
independent fixture pricing.

Verdict: maintain as portfolio evidence and pair with the router. Commercialise
only as part of a larger agent-ops offering, not standalone. For KOML, log usage
per mission from day one, price it with written-down numbers, and review cost per
outcome regularly. Unattributed spend is the signal of missing outcome logging.
