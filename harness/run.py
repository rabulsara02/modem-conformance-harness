"""
run.py — Run all YAML test plans against a modem and write a JSON summary.

Usage:
  python -m harness.run [--host H] [--port P] [--plans DIR] [--out FILE]

Assumes a simulator is reachable (start one with `python -m simulator.server`
or `docker compose up`). Exit code: 0 if all cases passed, 1 if any failed.
"""

import argparse
import logging
import sys
from pathlib import Path

from harness.testplan import load_plan
from harness.transport import TcpTransport
from harness.runner import run_case
from harness.report import build_summary, write_summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run modem conformance test plans.")
    parser.add_argument("--host", default="127.0.0.1", help="modem host")
    parser.add_argument("--port", type=int, default=5050, help="modem port")
    parser.add_argument("--plans", default="testplans", help="folder of YAML plans")
    parser.add_argument("--out", default="results/summary.json", help="summary output")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    plan_paths = sorted(Path(args.plans).glob("*.yaml"))
    if not plan_paths:
        print(f"No plans found in {args.plans!r}", file=sys.stderr)
        return 2

    results = []
    for plan_path in plan_paths:
        plan = load_plan(plan_path)
        transport = TcpTransport(args.host, args.port)
        transport.open()                       # one connection per plan
        try:
            transport.send("ATE0")             # clean, echo-free responses
            for case in plan.cases:
                results.append(run_case(case, transport))
        finally:
            transport.close()

    summary = build_summary(results)
    out = write_summary(summary, args.out)

    t = summary["totals"]
    print("\n=== Conformance summary ===")
    print(f"cases={t['cases']} passed={t['passed']} failed={t['failed']} "
          f"timed_out={t['timed_out']} retries={t['total_retries']} "
          f"pass_rate={t['pass_rate_pct']}% duration={t['total_duration_ms']}ms")
    print(f"wrote {out}")

    # Exit non-zero if anything failed, so CI / scripts can gate on it.
    return 0 if t["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())