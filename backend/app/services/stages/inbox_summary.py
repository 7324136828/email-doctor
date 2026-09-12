"""Stage 3 - aggregate grouped messages into inbox summary reports.

Produces under outputs/report/:
    senders.csv      - per sender-group totals ranked by message count
    unsubscribe.csv  - sender groups that advertise List-Unsubscribe links
    summary.json     - machine-readable totals
    summary.md       - human-readable summary
"""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

TOP_N_JSON = 10
TOP_N_MD = 20


def _iter_records(path: Path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _aggregate(records) -> dict[str, dict]:
    groups: dict[str, dict] = {}
    for rec in records:
        key = rec.get("sender_group") or "(unknown)"
        g = groups.setdefault(
            key,
            {
                "count": 0,
                "size": 0,
                "addrs": set(),
                "first": None,
                "last": None,
                "unsub": set(),
                "subjects": [],
            },
        )
        g["count"] += 1
        g["size"] += rec.get("size_bytes") or 0
        if rec.get("from_addr"):
            g["addrs"].add(rec["from_addr"])
        date = rec.get("date")
        if date:
            if g["first"] is None or date < g["first"]:
                g["first"] = date
            if g["last"] is None or date > g["last"]:
                g["last"] = date
        if rec.get("list_unsubscribe"):
            g["unsub"].add(rec["list_unsubscribe"])
        if rec.get("subject") and len(g["subjects"]) < 3:
            g["subjects"].append(rec["subject"])
    return groups


def _min_max(values):
    vals = [v for v in values if v]
    return (min(vals), max(vals)) if vals else (None, None)


def run(grouped_path: Path, report_dir: Path, log=print) -> dict:
    records = list(_iter_records(grouped_path))
    groups = _aggregate(records)
    ranked = sorted(groups.items(), key=lambda kv: (-kv[1]["count"], kv[0]))

    report_dir.mkdir(parents=True, exist_ok=True)

    with open(report_dir / "senders.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "rank",
                "sender_group",
                "message_count",
                "total_size_bytes",
                "distinct_addresses",
                "first_seen",
                "last_seen",
                "unsubscribe_available",
                "example_subjects",
            ]
        )
        for rank, (group, g) in enumerate(ranked, start=1):
            w.writerow(
                [
                    rank,
                    group,
                    g["count"],
                    g["size"],
                    len(g["addrs"]),
                    g["first"] or "",
                    g["last"] or "",
                    "yes" if g["unsub"] else "no",
                    " | ".join(g["subjects"]),
                ]
            )

    with open(report_dir / "unsubscribe.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["sender_group", "addresses", "message_count", "unsubscribe_link"])
        for group, g in ranked:
            if g["unsub"]:
                w.writerow(
                    [group, ";".join(sorted(g["addrs"])), g["count"], sorted(g["unsub"])[0]]
                )

    first, last = _min_max(r.get("date") for r in records)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_messages": len(records),
        "unique_senders": len(groups),
        "unique_domains": len({r.get("sender_domain") for r in records if r.get("sender_domain")}),
        "date_range": {"first": first, "last": last},
        "total_size_bytes": sum(r.get("size_bytes") or 0 for r in records),
        "messages_with_unsubscribe": sum(1 for r in records if r.get("list_unsubscribe")),
        "senders_with_unsubscribe": sum(1 for g in groups.values() if g["unsub"]),
        "top_senders": [
            {"sender": group, "messages": g["count"], "size_bytes": g["size"]}
            for group, g in ranked[:TOP_N_JSON]
        ],
    }
    (report_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    lines = [
        "# Inbox Summary",
        "",
        f"- **Messages analyzed:** {summary['total_messages']}",
        f"- **Unique sender groups:** {summary['unique_senders']}",
        f"- **Unique domains:** {summary['unique_domains']}",
        f"- **Total size:** {summary['total_size_bytes']:,} bytes",
        f"- **Messages with unsubscribe links:** {summary['messages_with_unsubscribe']}",
        f"- **Sender groups offering unsubscribe:** {summary['senders_with_unsubscribe']}",
    ]
    if first:
        lines.append(f"- **Date range:** {first[:10]} to {(last or first)[:10]}")
    lines += ["", "## Top senders", "", "| Rank | Sender | Messages | Size (bytes) | Unsubscribe |", "|---:|---|---:|---:|---|"]
    for rank, (group, g) in enumerate(ranked[:TOP_N_MD], start=1):
        lines.append(
            f"| {rank} | {group} | {g['count']} | {g['size']:,} | "
            f"{'yes' if g['unsub'] else 'no'} |"
        )
    lines += [
        "",
        "## Next steps",
        "",
        "See `inbox_cleanup_worklist.csv` for per-sender recommended actions and "
        "`inbox_audit.html` for the full interactive report.",
        "",
    ]
    (report_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    log(f"Aggregated {len(records)} messages across {len(groups)} sender groups")
    return summary
