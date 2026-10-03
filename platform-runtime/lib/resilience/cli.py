"""Command-line entry for the crosswalk pipeline.

    cd platform-runtime
    python -m lib.resilience.cli run "CPS 230 business continuity testing" --targets BCBS-d516 EU-DORA
    python -m lib.resilience.cli coverage
    python -m lib.resilience.cli pending
    python -m lib.resilience.cli eval      # golden + red-team cases against the live Model Router
    python -m lib.resilience.cli changes
    python -m lib.resilience.cli resolve-change cf-1a2b3c4d5e6f dismissed --note "editorial only"
    python -m lib.resilience.cli review xw-1a2b3c4d5e6f accepted --note "checked paras against PDF"
"""

from __future__ import annotations

import argparse
import sys

from . import audit, change_flags
from .corpus import load_corpus
from .pipeline import Intake, run_crosswalk


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lib.resilience.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="produce a crosswalk")
    run.add_argument("query")
    run.add_argument("--source", dest="source_framework")
    run.add_argument("--profile")
    run.add_argument("--targets", nargs="+")
    run.add_argument("--use", dest="intended_use")
    run.add_argument("--adopted", nargs="+")

    sub.add_parser("coverage", help="clauses held per framework, by text status")
    sub.add_parser("pending", help="crosswalk runs still awaiting a review decision")

    ev = sub.add_parser("eval", help="run the golden / red-team eval cases through the pipeline")
    ev.add_argument("--report-dir")

    sub.add_parser("changes", help="open regulatory change flags")
    rc = sub.add_parser("resolve-change", help="close a change flag")
    rc.add_argument("flag_id")
    rc.add_argument("resolution", choices=sorted(change_flags.RESOLUTIONS))
    rc.add_argument("--note", default="")

    review = sub.add_parser("review", help="record your accept / edit / reject decision")
    review.add_argument("run_id")
    review.add_argument("decision", choices=sorted(audit.REVIEW_DECISIONS))
    review.add_argument("--note", default="")

    args = ap.parse_args(argv)

    if args.cmd == "run":
        intake = Intake(source_framework=args.source_framework, profile=args.profile,
                        targets=args.targets, intended_use=args.intended_use, adopted=args.adopted)
        result = run_crosswalk(args.query, intake)
        print(result.markdown)
        return 0 if result.status == "ok" else 1
    if args.cmd == "coverage":
        for fid, counts in load_corpus().coverage().items():
            print(f"{fid:16} " + "  ".join(f"{k}={v}" for k, v in counts.items()))
        return 0
    if args.cmd == "eval":
        from .evaluate import format_summary, run_evals

        report = run_evals(report_dir=args.report_dir, progress=lambda cid: print(f"… {cid}", flush=True))
        print(format_summary(report))
        return 0 if report["summary"]["passed"] == report["summary"]["total"] else 1
    if args.cmd == "changes":
        for f in change_flags.open_flags():
            print(f"{f.flag_id}  {f.framework_id:16} {f.short()}  {f.url}")
        unwatched = change_flags.unwatched(load_corpus())
        if unwatched:
            print("no change feed for: " + ", ".join(unwatched))
        return 0
    if args.cmd == "resolve-change":
        ok = change_flags.resolve(args.flag_id, args.resolution, args.note)
        print(f"{'closed' if ok else 'not open'}: {args.flag_id}")
        return 0 if ok else 1
    if args.cmd == "pending":
        for run_id in audit.unreviewed_runs():
            print(run_id)
        return 0
    audit.record_review(args.run_id, args.decision, args.note)
    print(f"recorded {args.decision} for {args.run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
