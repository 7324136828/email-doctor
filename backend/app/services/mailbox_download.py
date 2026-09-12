"""Download a recent INBOX window over IMAP without persisting credentials."""

from __future__ import annotations

import imaplib
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable


IMAP_SERVERS: dict[str, tuple[str, int]] = {
    "gmail.com": ("imap.gmail.com", 993),
    "googlemail.com": ("imap.gmail.com", 993),
    "aol.com": ("imap.aol.com", 993),
    "yahoo.com": ("imap.mail.yahoo.com", 993),
    "outlook.com": ("outlook.office365.com", 993),
    "hotmail.com": ("outlook.office365.com", 993),
    "live.com": ("outlook.office365.com", 993),
    "live.cn": ("outlook.office365.com", 993),
    "msn.com": ("outlook.office365.com", 993),
    "foxmail.com": ("imap.qq.com", 993),
    "qq.com": ("imap.qq.com", 993),
    "protonmail.com": ("127.0.0.1", 1143),
    "pm.me": ("127.0.0.1", 1143),
    "proton.me": ("127.0.0.1", 1143),
}

GOOGLE_DOMAINS = {"gmail.com", "googlemail.com"}
MICROSOFT_DOMAINS = {
    "outlook.com",
    "hotmail.com",
    "live.com",
    "live.cn",
    "msn.com"
}


class MailboxDownloadError(RuntimeError):
    pass


class DownloadCancelled(RuntimeError):
    pass


def email_domain(address: str) -> str:
    return address.rsplit("@", 1)[-1].strip().lower() if "@" in address else ""


def provider_for_email(address: str) -> str:
    domain = email_domain(address)
    if domain in GOOGLE_DOMAINS:
        return "google"
    if domain in MICROSOFT_DOMAINS:
        return "microsoft"
    return "credentials"


def resolve_imap(address: str) -> tuple[str, int]:
    domain = email_domain(address)
    return IMAP_SERVERS.get(domain, (f"imap.{domain}", 993))


def since_date_str(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")


def _raw_message(fetch_data) -> bytes | None:
    for part in fetch_data or []:
        if isinstance(part, tuple) and len(part) > 1 and isinstance(part[1], bytes):
            return part[1]
    return None


def _connect(server: str, port: int, use_ssl: bool):
    try:
        if use_ssl:
            return imaplib.IMAP4_SSL(server, port, timeout=30)
        return imaplib.IMAP4(server, port, timeout=30)
    except (OSError, imaplib.IMAP4.error) as exc:
        raise MailboxDownloadError(
            f"Could not connect to IMAP server {server}:{port}: {exc}"
        ) from exc


def download_inbox(
    *,
    email: str,
    output_dir: Path,
    days: int,
    password: str | None = None,
    access_token: str | None = None,
    imap_server: str | None = None,
    imap_port: int | None = None,
    use_ssl: bool | None = None,
    progress: Callable[[int, int], None] = lambda _done, _total: None,
    log: Callable[[str], None] = print,
    should_cancel: Callable[[], bool] = lambda: False,
    on_batch: Callable[[int, int], None] = lambda _done, _total: None,
) -> tuple[int, int]:
    """Download INBOX messages received in the last ``days`` days.

    Authentication material is accepted as an in-memory argument and is never
    written to the job workspace. BODY.PEEK[] keeps messages unread.
    """
    default_server, default_port = resolve_imap(email)
    server = (imap_server or default_server).strip()
    port = int(imap_port or default_port)
    ssl_enabled = (port == 993) if use_ssl is None else use_ssl
    output_dir.mkdir(parents=True, exist_ok=True)

    conn = _connect(server, port, ssl_enabled)
    try:
        try:
            if access_token:
                auth = f"user={email}\x01auth=Bearer {access_token}\x01\x01"
                conn.authenticate("XOAUTH2", lambda _challenge: auth.encode("utf-8"))
            elif password:
                conn.login(email, password)
            else:
                raise MailboxDownloadError("No mailbox authentication was supplied")
        except imaplib.IMAP4.error as exc:
            raise MailboxDownloadError(
                "Mailbox sign-in failed. Check provider permissions or use an app password."
            ) from exc

        status, _ = conn.select("INBOX", readonly=True)
        if status != "OK":
            raise MailboxDownloadError("The server would not open the INBOX folder")

        since = since_date_str(days)
        status, data = conn.uid("search", None, "SINCE", since)
        if status != "OK":
            raise MailboxDownloadError("The server could not search the requested date range")
        uids = (data[0] if data else b"").split()
        total = len(uids)
        log(f"Found {total} INBOX messages since {since}")
        progress(0, total)

        downloaded = 0
        for uid_bytes in uids:
            if should_cancel():
                raise DownloadCancelled("Mailbox download was cancelled")
            uid = re.sub(r"[^0-9A-Za-z_-]", "_", uid_bytes.decode("ascii", "replace"))
            target = output_dir / f"{uid}.eml"
            if not target.exists():
                status, fetched = conn.uid("fetch", uid_bytes, "(BODY.PEEK[])")
                raw = _raw_message(fetched)
                if status != "OK" or raw is None:
                    log(f"Skipped UID {uid}: the server returned no message data")
                    continue
                partial = target.with_suffix(".eml.part")
                partial.write_bytes(raw)
                partial.replace(target)
                time.sleep(0.03)
            downloaded += 1
            progress(downloaded, total)
            on_batch(downloaded, total)
        return downloaded, total
    finally:
        try:
            conn.logout()
        except Exception:
            pass
