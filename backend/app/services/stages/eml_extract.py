"""Stage 1 - extract structured records from .eml / .mbox inputs.

Scans the job's inputs/ directory for .eml files (including ones unpacked from
uploaded .zip archives) and .mbox mailboxes, then writes one JSON record per
message to work/messages.jsonl.
"""
import json
import mailbox
import re
from email import policy
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime, parseaddr
from pathlib import Path

_UNSUB_URL = re.compile(r"<([^>]+)>")


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        return dt.isoformat() if dt else None
    except Exception:
        return None


def _first_address(value: str | None) -> str:
    if not value:
        return ""
    addrs = getaddresses([value])
    return addrs[0][1] if addrs else ""


def _unsubscribe_link(raw: str | None) -> str:
    if not raw:
        return ""
    match = _UNSUB_URL.search(raw)
    return match.group(1) if match else raw.strip()


def _snippet(msg, limit: int = 300) -> str:
    try:
        parts = msg.walk() if msg.is_multipart() else [msg]
        for part in parts:
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_content_type() != "text/plain":
                continue
            if part.get_content_disposition() == "attachment":
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                payload = str(part.get_payload() or "").encode("utf-8", "replace")
            charset = part.get_content_charset() or "utf-8"
            text = " ".join(payload.decode(charset, "replace").split())
            if text:
                return text[:limit]
    except Exception:
        pass
    return ""


def _has_attachments(msg) -> bool:
    try:
        for part in msg.walk() if msg.is_multipart() else [msg]:
            if part.get_content_disposition() == "attachment" or part.get_filename():
                return True
    except Exception:
        pass
    return False


def _record(msg, source_file: str, size: int, mbox_index: int | None = None) -> dict:
    from_name, from_addr = parseaddr(msg.get("From", ""))
    from_addr = from_addr.lower()
    raw_unsub = msg.get("List-Unsubscribe", "")
    return {
        "source_file": source_file,
        "mbox_index": mbox_index,
        "message_id": (msg.get("Message-ID") or "").strip(),
        "subject": _decode(msg.get("Subject")),
        "from_name": _decode(from_name),
        "from_addr": from_addr,
        "from_domain": from_addr.split("@")[-1] if "@" in from_addr else "",
        "to": _first_address(msg.get("To")),
        "date": _parse_date(msg.get("Date")),
        "list_unsubscribe": _unsubscribe_link(raw_unsub),
        "list_unsubscribe_post": bool(msg.get("List-Unsubscribe-Post")),
        "size_bytes": size,
        "has_attachments": _has_attachments(msg),
        "snippet": _snippet(msg),
    }


def _iter_eml(path: Path):
    try:
        msg = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    except Exception:
        return None
    return msg


def run(inputs_dir: Path, out_path: Path, log=print) -> int:
    """Parse every message under inputs_dir into a JSONL file. Returns count."""
    records: list[dict] = []

    for eml in sorted(inputs_dir.rglob("*.eml")):
        msg = _iter_eml(eml)
        if msg is None:
            log(f"Skipping unparseable file: {eml.name}")
            continue
        try:
            size = eml.stat().st_size
        except OSError:
            size = 0
        records.append(_record(msg, eml.name, size))

    for mbox_path in sorted(inputs_dir.rglob("*.mbox")):
        try:
            box = mailbox.mbox(mbox_path)
        except Exception as exc:
            log(f"Skipping unreadable mailbox {mbox_path.name}: {exc}")
            continue
        for i, msg in enumerate(box):
            try:
                size = len(msg.as_bytes())
            except Exception:
                size = 0
            records.append(_record(msg, mbox_path.name, size, mbox_index=i))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return len(records)
