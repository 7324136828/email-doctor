"""Stage 4 - generate a per-sender cleanup worklist.

Applies heuristic recommendations (unsubscribe / review / delete / archive /
keep) to every sender group, honoring optional user overrides from an
``annotations.json`` file placed in the job inputs.

annotations.json accepts either shape:
    {"newsletters.example.com": "unsubscribe_and_purge"}
    {"newsletters.example.com": {"action": "keep", "note": " receipts"}}
"""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .inbox_summary import _aggregate, _iter_records

AUTOMATED_PATTERNS = (
    "noreply",
    "no-reply",
    "no_reply",
    "donotreply",
    "do-not-reply",
    "mailer-daemon",
    "newsletter",
    "notifications",
    "notify",
    "bounce",
    "digest",
    "marketing",
    "promo",
    "updates",
)

ACTIONS = (
    "unsubscribe_and_purge",
    "unsubscribe",
    "review_delete",
    "review",
    "archive",
    "keep",
)

HIGH_VOLUME = 10


def _is_automated(group: str, addrs: set[str]) -> bool:
    haystack = " ".join([group, *addrs]).lower()
    return any(p in haystack for p in AUTOMATED_PATTERNS)


def _recommend(group: str, g: dict) -> tuple[str, str]:
    count = g["count"]
    has_unsub = bool(g["unsub"])
    automated = _is_automated(group, g["addrs"])
    if has_unsub and count >= HIGH_VOLUME:
        return "unsubscribe_and_purge", "High-volume sender advertising unsubscribe"
    if has_unsub:
        return "unsubscribe", "Sender advertises an unsubscribe link"
    if automated and count >= 5:
        return "review_delete", "Automated sender without unsubscribe option"
    if automated:
        return "review", "Likely automated sender"
    if count >= HIGH_VOLUME:
        return "archive", "High-volume sender, no unsubscribe detected"
    return "keep", "Low-volume human sender"


def _load_annotations(inputs_dir: Path, log) -> dict[str, dict]:
    notes: dict[str, dict] = {}
    for path in sorted(inputs_dir.rglob("annotations.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            log(f"Ignoring invalid annotations file {path.name}: {exc}")
            continue
        if isinstance(data, dict):
            notes.update(data)
    return notes


def run(inputs_dir: Path, grouped_path: Path, outputs_dir: Path, log=print) -> dict:
    groups = _aggregate(_iter_records(grouped_path))
    ranked = sorted(groups.items(), key=lambda kv: (-kv[1]["count"], kv[0]))
    annotations = _load_annotations(inputs_dir, log)

    items = []
    for group, g in ranked:
        action, reason = _recommend(group, g)
        override = annotations.get(group)
        note = ""
        if isinstance(override, str) and override in ACTIONS:
            action, reason = override, "User annotation override"
        elif isinstance(override, dict):
            if override.get("action") in ACTIONS:
                action = override["action"]
                reason = "User annotation override"
            note = str(override.get("note") or "")
        items.append(
            {
                "sender_group": group,
                "recommended_action": action,
                "message_count": g["count"],
                "total_size_bytes": g["size"],
                "first_seen": g["first"] or "",
                "last_seen": g["last"] or "",
                "has_unsubscribe": bool(g["unsub"]),
                "unsubscribe_link": sorted(g["unsub"])[0] if g["unsub"] else "",
                "addresses": sorted(g["addrs"]),
                "reason": reason,
                "note": note,
            }
        )

    outputs_dir.mkdir(parents=True, exist_ok=True)
    with open(
        outputs_dir / "inbox_cleanup_worklist.csv", "w", newline="", encoding="utf-8"
    ) as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "sender_group",
                "recommended_action",
                "message_count",
                "total_size_bytes",
                "first_seen",
                "last_seen",
                "has_unsubscribe",
                "unsubscribe_link",
                "addresses",
                "reason",
                "note",
            ]
        )
        for it in items:
            w.writerow(
                [
                    it["sender_group"],
                    it["recommended_action"],
                    it["message_count"],
                    it["total_size_bytes"],
                    it["first_seen"],
                    it["last_seen"],
                    "yes" if it["has_unsubscribe"] else "no",
                    it["unsubscribe_link"],
                    ";".join(it["addresses"]),
                    it["reason"],
                    it["note"],
                ]
            )

    action_counts = {a: 0 for a in ACTIONS}
    for it in items:
        action_counts[it["recommended_action"]] += 1
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_senders": len(items),
        "action_counts": action_counts,
        "items": items,
    }
    (outputs_dir / "worklist.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log(f"Worklist generated for {len(items)} sender groups")
    return payload
