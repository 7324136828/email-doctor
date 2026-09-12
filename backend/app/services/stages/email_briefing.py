"""Create a human-readable inventory of the recent emails being audited."""

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _date(value: str | None):
    try:
        return datetime.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def run(messages_path: Path, report_dir: Path, days: int | None, log=print) -> int:
    records = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    with messages_path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            record = json.loads(line)
            sent = _date(record.get("date"))
            if sent and sent.tzinfo is None:
                sent = sent.replace(tzinfo=timezone.utc)
            if cutoff and sent and sent < cutoff:
                continue
            record["_sent"] = sent
            records.append(record)
    records.sort(
        key=lambda item: item["_sent"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    report_dir.mkdir(parents=True, exist_ok=True)

    with (report_dir / "recent_emails.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["date", "from", "sender_group", "subject", "snippet"])
        for item in records:
            writer.writerow(
                [
                    item.get("date") or "",
                    item.get("from_name") or item.get("from_addr") or "(unknown)",
                    item.get("sender_group") or "(unknown)",
                    item.get("subject") or "(no subject)",
                    item.get("snippet") or "",
                ]
            )

    senders = Counter(item.get("sender_group") or "(unknown)" for item in records)
    by_day = defaultdict(list)
    for item in records:
        key = item["_sent"].date().isoformat() if item["_sent"] else "Unknown date"
        by_day[key].append(item)
    title = f"Email briefing — last {days} day{'s' if days != 1 else ''}" if days else "Email briefing"
    lines = [f"# {title}", "", f"{len(records)} messages are included.", ""]
    if senders:
        lines += ["## Most active senders", ""]
        lines += [f"- {sender}: {count}" for sender, count in senders.most_common(10)]
        lines.append("")
    lines += ["## What arrived", ""]
    shown = 0
    for day in sorted(by_day, reverse=True):
        lines += [f"### {day}", ""]
        for item in by_day[day]:
            sender = item.get("from_name") or item.get("from_addr") or "Unknown sender"
            subject = item.get("subject") or "(no subject)"
            snippet = item.get("snippet") or "No plain-text preview available."
            lines += [f"- **{subject}** — {sender}", f"  {snippet}"]
            shown += 1
            if shown >= 200:
                lines += ["", "_The briefing preview is limited to 200 messages; see `recent_emails.csv` for all rows._"]
                break
        lines.append("")
        if shown >= 200:
            break
    (report_dir / "email_briefing.md").write_text("\n".join(lines), encoding="utf-8")
    log(f"Created recent-email briefing for {len(records)} messages")
    return len(records)
