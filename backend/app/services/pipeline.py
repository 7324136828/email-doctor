"""Email audit pipeline orchestrator.

Runs the five stages against an isolated job directory and reports progress on
stdout using machine-readable prefixes consumed by the parent process:

    [STAGE] <name>       current pipeline stage
    [PROGRESS] <0-100>   percent complete
    [LOG] <text>         informational log line
    [ERROR] <text>       fatal error details

Can also be invoked directly:

    python -m app.services.pipeline --job-dir <path>
"""
import argparse
import shutil
import sys
import traceback
from pathlib import Path

from .stages import email_briefing, eml_extract, gen_report, inbox_summary, rebrand, worklist


class PipelineError(Exception):
    pass


def emit(kind: str, msg) -> None:
    print(f"[{kind}] {msg}", flush=True)


def run_pipeline(job_dir: Path, days: int | None = None, event=emit) -> None:
    job_dir = Path(job_dir)
    inputs = job_dir / "inputs"
    work = job_dir / "work"
    outputs = job_dir / "outputs"
    report_dir = outputs / "report"
    for d in (inputs, work, outputs, report_dir):
        d.mkdir(parents=True, exist_ok=True)

    def pipeline_log(msg) -> None:
        event("LOG", msg)

    event("STAGE", "extract")
    event("PROGRESS", 5)
    from ..utils.temp_manager import prepare_inputs

    prepare_inputs(job_dir)
    count = eml_extract.run(inputs, work / "messages.jsonl", log=pipeline_log)
    if count == 0:
        raise PipelineError(
            "No parseable .eml or .mbox messages were found in the upload."
        )
    pipeline_log(f"Parsed {count} messages")
    event("PROGRESS", 40)

    event("STAGE", "group")
    rebrand.run(
        inputs,
        work / "messages.jsonl",
        work / "messages_grouped.jsonl",
        work / "_domain_aliases.json",
        log=pipeline_log,
    )
    event("PROGRESS", 55)

    event("STAGE", "summarize")
    inbox_summary.run(work / "messages_grouped.jsonl", report_dir, log=pipeline_log)
    email_briefing.run(work / "messages_grouped.jsonl", report_dir, days, log=pipeline_log)
    event("PROGRESS", 75)

    event("STAGE", "worklist")
    worklist.run(inputs, work / "messages_grouped.jsonl", outputs, log=pipeline_log)
    event("PROGRESS", 88)

    event("STAGE", "report")
    gen_report.run(
        report_dir / "summary.json",
        outputs / "worklist.json",
        outputs / "inbox_audit.html",
        log=pipeline_log,
    )

    # Publish intermediate artifacts alongside the reports.
    for name in ("messages.jsonl", "messages_grouped.jsonl", "_domain_aliases.json"):
        src = work / name
        if src.is_file():
            shutil.copy2(src, outputs / name)
    event("PROGRESS", 97)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="email-doctor audit pipeline")
    parser.add_argument("--job-dir", required=True, help="Isolated job directory")
    parser.add_argument("--days", type=int, default=None)
    args = parser.parse_args(argv)
    try:
        run_pipeline(Path(args.job_dir), days=args.days)
    except Exception:
        emit("ERROR", traceback.format_exc(limit=10))
        return 1
    emit("STAGE", "done")
    emit("PROGRESS", 100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
