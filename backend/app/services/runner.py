"""Job runner: spawns the audit pipeline as a subprocess and tracks progress.

Running each job as its own OS process keeps the API responsive and lets
discard terminate work immediately and deterministically.
"""
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from .. import db
from ..config import BACKEND_DIR, settings
from ..utils import temp_manager
from . import mailbox_download, pipeline

_ACTIVE: dict[str, subprocess.Popen] = {}
_MAILBOX_CANCEL: dict[str, threading.Event] = {}
_LOCK = threading.Lock()

STAGE_LABELS = {
    "connecting": "Connecting to mailbox",
    "downloading": "Downloading recent INBOX messages",
    "snapshot": "Refreshing audit snapshot",
    "extract": "Parsing messages",
    "group": "Grouping senders",
    "summarize": "Building summary",
    "worklist": "Generating cleanup worklist",
    "report": "Rendering HTML report",
    "done": "Done",
}


def start_job(job_id: str) -> None:
    job_dir = temp_manager.job_dir_for(job_id)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "app.services.pipeline", "--job-dir", str(job_dir)],
            cwd=str(BACKEND_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except Exception as exc:
        db.update_job(
            job_id,
            status="failed",
            error_message=f"Failed to start pipeline: {exc}",
            completed_at=db.utcnow(),
        )
        return
    with _LOCK:
        _ACTIVE[job_id] = proc
    threading.Thread(target=_monitor, args=(job_id, proc), daemon=True).start()


def active_job_ids() -> list[str]:
    with _LOCK:
        return list(set(_ACTIVE) | set(_MAILBOX_CANCEL))


def start_mailbox_job(job_id: str, auth: dict) -> None:
    """Start a mailbox ingestion thread; ``auth`` is retained in memory only."""
    cancel = threading.Event()
    with _LOCK:
        _MAILBOX_CANCEL[job_id] = cancel
    threading.Thread(
        target=_mailbox_worker, args=(job_id, auth, cancel), daemon=True
    ).start()


def _publish_snapshot(job_id: str, job_dir: Path, days: int) -> None:
    build = job_dir / "_snapshot_build"
    if build.exists():
        shutil.rmtree(build)
    (build / "inputs").mkdir(parents=True)
    for source in (job_dir / "inputs").rglob("*"):
        if source.is_file() and source.suffix.lower() in {".eml", ".json"}:
            relative = source.relative_to(job_dir / "inputs")
            target = build / "inputs" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    pipeline.run_pipeline(build, days=days, event=lambda _kind, _message: None)
    temp_manager.replace_snapshot_outputs(job_dir, build / "outputs")
    shutil.rmtree(build, ignore_errors=True)
    db.update_job(job_id, snapshot_available=1, snapshot_at=db.utcnow())
    db.append_log(job_id, "Audit snapshot refreshed.")


def _mailbox_worker(job_id: str, auth: dict, cancel: threading.Event) -> None:
    job = db.get_job(job_id)
    if not job:
        return
    job_dir = Path(job["temp_dir"])
    days = int(job.get("days") or 7)
    db.update_job(job_id, status="in_progress", stage="connecting", progress=2)
    db.append_log(job_id, f"Connecting to the INBOX for {job['account_email']}.")
    last_snapshot = 0

    def progress(done: int, total: int) -> None:
        pct = 8 if total == 0 else 8 + int(47 * done / max(total, 1))
        db.update_job(
            job_id,
            stage="downloading",
            progress=pct,
            downloaded_messages=done,
            total_messages=total,
        )

    def on_batch(done: int, total: int) -> None:
        nonlocal last_snapshot
        due = done == 1 or done - last_snapshot >= settings.snapshot_every_messages
        if due and done < total and not cancel.is_set():
            db.update_job(job_id, stage="snapshot")
            try:
                _publish_snapshot(job_id, job_dir, days)
                last_snapshot = done
            except Exception as exc:
                db.append_log(job_id, f"Snapshot refresh skipped: {exc}")
            finally:
                if not cancel.is_set():
                    db.update_job(job_id, stage="downloading")

    try:
        downloaded, total = mailbox_download.download_inbox(
            email=job["account_email"],
            output_dir=job_dir / "inputs" / "mailbox",
            days=days,
            progress=progress,
            log=lambda message: db.append_log(job_id, message),
            should_cancel=cancel.is_set,
            on_batch=on_batch,
            **auth,
        )
        if cancel.is_set():
            return
        if downloaded == 0:
            raise mailbox_download.MailboxDownloadError(
                f"No INBOX messages were found in the last {days} day(s)."
            )
        total_bytes = sum(
            path.stat().st_size for path in (job_dir / "inputs").rglob("*.eml")
        )
        db.update_job(
            job_id,
            file_size=total_bytes,
            downloaded_messages=downloaded,
            total_messages=total,
            stage="extract",
            progress=58,
        )
        db.append_log(job_id, f"Downloaded {downloaded} messages; starting final audit.")

        def audit_event(kind: str, message) -> None:
            if cancel.is_set():
                raise mailbox_download.DownloadCancelled()
            if kind == "STAGE":
                db.update_job(job_id, stage=str(message))
                label = STAGE_LABELS.get(str(message), str(message))
                db.append_log(job_id, f"--- stage: {label} ---")
            elif kind == "PROGRESS":
                db.update_job(job_id, progress=60 + int(int(message) * 0.39))
            elif kind == "LOG":
                db.append_log(job_id, str(message))

        pipeline.run_pipeline(job_dir, days=days, event=audit_event)
        if cancel.is_set():
            return
        zip_path = temp_manager.package_outputs(job_dir)
        db.update_job(
            job_id,
            status="completed",
            progress=100,
            stage="done",
            zip_path=str(zip_path),
            snapshot_available=1,
            snapshot_at=db.utcnow(),
            completed_at=db.utcnow(),
        )
        db.append_log(job_id, "Mailbox audit finished; outputs packaged.")
    except mailbox_download.DownloadCancelled:
        pass
    except Exception as exc:
        current = db.get_job(job_id)
        if current and current["status"] != "discarded":
            db.update_job(
                job_id,
                status="failed",
                stage="failed",
                error_message=str(exc),
                completed_at=db.utcnow(),
            )
            db.append_log(job_id, f"Mailbox job failed: {exc}")
    finally:
        auth.clear()
        with _LOCK:
            _MAILBOX_CANCEL.pop(job_id, None)


def _handle_line(job_id: str, line: str) -> None:
    if line.startswith("[STAGE]"):
        stage = line[7:].strip()
        db.update_job(job_id, stage=stage)
        db.append_log(job_id, f"--- stage: {STAGE_LABELS.get(stage, stage)} ---")
    elif line.startswith("[PROGRESS]"):
        try:
            db.update_job(job_id, progress=int(line[10:].strip()))
        except ValueError:
            pass
    elif line.startswith("[ERROR]"):
        db.append_log(job_id, line[7:].strip())
    else:
        db.append_log(job_id, line)


def _monitor(job_id: str, proc: subprocess.Popen) -> None:
    db.update_job(job_id, status="in_progress", stage="starting", progress=2)
    try:
        for line in proc.stdout or []:
            _handle_line(job_id, line.rstrip("\n"))
    finally:
        code = proc.wait()
        with _LOCK:
            _ACTIVE.pop(job_id, None)
    job = db.get_job(job_id)
    if job is None or job["status"] == "discarded":
        return
    if code == 0:
        try:
            zip_path = temp_manager.package_outputs(Path(job["temp_dir"]))
            db.update_job(
                job_id,
                status="completed",
                progress=100,
                stage="done",
                zip_path=str(zip_path),
                completed_at=db.utcnow(),
            )
            db.append_log(job_id, "Pipeline finished; outputs packaged.")
        except Exception as exc:
            db.update_job(
                job_id,
                status="failed",
                error_message=f"Packaging failed: {exc}",
                completed_at=db.utcnow(),
            )
    else:
        db.update_job(
            job_id,
            status="failed",
            stage="failed",
            error_message=f"Pipeline exited with code {code}. See log for details.",
            completed_at=db.utcnow(),
        )
        db.append_log(job_id, f"[runner] pipeline exited with code {code}")


def discard_job(job_id: str) -> bool:
    """Terminate the running process (if any) and purge the job temp dir."""
    with _LOCK:
        proc = _ACTIVE.get(job_id)
        mailbox_cancel = _MAILBOX_CANCEL.get(job_id)
    if mailbox_cancel is not None:
        mailbox_cancel.set()
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
    job = db.get_job(job_id)
    if job is None:
        return False
    if job.get("temp_dir"):
        temp_manager.purge_job_dir(Path(job["temp_dir"]))
    db.update_job(
        job_id,
        status="discarded",
        stage="discarded",
        error_message="Discarded by user",
        snapshot_available=0,
        completed_at=db.utcnow(),
    )
    db.append_log(job_id, "[runner] job discarded; temp folder purged")
    return True
