"""
run.py — Run all YAML test plans against a modem and write a JSON summary.

Usage:
  python -m harness.run [--host H] [--port P] [--plans DIR] [--out FILE]
  python -m harness.run --serial /dev/ttyUSB0     # run against a real modem

Talks to the TCP simulator by default (start one with `python -m simulator.server`
or `docker compose up`), or to a real serial modem with --serial. Exit code: 0 if
all cases passed, 1 if any failed.
"""

import argparse
import logging
import sys
from pathlib import Path

from harness.testplan import load_plan
from harness.transport import TcpTransport
from harness.runner import run_case, run_plan
from harness.report import build_summary, write_summary, write_junit, write_html


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run modem conformance test plans.")
    parser.add_argument("--host", default="127.0.0.1", help="modem host")
    parser.add_argument("--port", type=int, default=5050, help="modem port")
    parser.add_argument("--plans", default="testplans", help="folder of YAML plans")
    parser.add_argument("--out", default="results/summary.json", help="summary output")
    parser.add_argument("--junit", default="results/junit.xml", help="JUnit XML output")
    parser.add_argument("--html", default="results/report.html", help="HTML report output")
    parser.add_argument("--serial", help="talk to a real modem at this serial port "
                                          "(e.g. /dev/ttyUSB0) instead of TCP")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    plan_paths = sorted(Path(args.plans).glob("*.yaml"))
    if not plan_paths:
        print(f"No plans found in {args.plans!r}", file=sys.stderr)
        return 2

    def make_transport():
        # Real hardware if --serial was given, otherwise TCP to the simulator.
        # SerialTransport is imported lazily so pyserial stays an optional dependency.
        if args.serial:
            from harness.transport import SerialTransport
            return SerialTransport(args.serial)
        return TcpTransport(args.host, args.port)

    results = []
    for plan_path in plan_paths:
        plan = load_plan(plan_path)
        transport = make_transport()           # TCP simulator or a real serial modem
        transport.open()                       # one connection per plan
        try:
            results.extend(run_plan(plan, transport)) # originally send ATE0 + loop by hand
        finally:
            transport.close()

    summary = build_summary(results)
    write_summary(summary, args.out)
    write_junit(summary, args.junit)
    write_html(summary, args.html)

    t = summary["totals"]
    print("\n=== Conformance summary ===")
    print(f"cases={t['cases']} passed={t['passed']} failed={t['failed']} "
          f"timed_out={t['timed_out']} retries={t['total_retries']} "
          f"pass_rate={t['pass_rate_pct']}% duration={t['total_duration_ms']}ms")
    print(f"wrote {args.out}, {args.junit}, {args.html}")
    # Exit non-zero if anything failed, so CI / scripts can gate on it.
    return 0 if t["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())