"""email-doctor API - FastAPI entrypoint."""
import json
import html
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from . import db
from .config import settings
from .schemas.job import JobOut, MailCredentialsIn, OAuthStartIn, PasteJobIn
from .services import mailbox_download, oauth, runner
from .utils import temp_manager


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    settings.jobs_root.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="email-doctor API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

_DATA_EXTENSIONS = {".eml", ".zip", ".mbox"}


def _to_out(job: dict, job_dir: Path | None = None) -> JobOut:
    out = {k: job.get(k) for k in JobOut.model_fields if k in job}
    out["log"] = job.get("log") or ""
    if job_dir is not None:
        out["output_files"] = temp_manager.list_output_files(job_dir)
    return JobOut(**out)


def _get_or_404(job_id: str) -> dict:
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _validate_email(address: str) -> str:
    address = address.strip()
    if address.count("@") != 1 or not mailbox_download.email_domain(address):
        raise HTTPException(status_code=400, detail="Enter a valid email address")
    return address


def _create_mail_job(email: str, days: int, auth: dict) -> dict:
    job_id = uuid.uuid4().hex
    job_dir = temp_manager.create_job_dirs(job_id)
    job = db.create_job(
        job_id,
        f"{email} INBOX ({days} days)",
        0,
        str(job_dir),
        source_kind="mailbox",
        account_email=email,
        days=days,
    )
    runner.start_mailbox_job(job_id, auth)
    return job


@app.get("/api/health")
async def health():
    return {"status": "ok", "app": settings.app_name}


@app.post("/api/jobs", response_model=JobOut, status_code=201)
async def create_job(files: list[UploadFile] = File(...)):
    """Stage one or more uploads (.eml / .zip / .mbox, plus optional
    aliases.json / annotations.json) and start an audit job."""
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    for f in files:
        name = temp_manager.safe_filename(f.filename)
        if Path(name).suffix.lower() not in settings.allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {name}. "
                "Accepted: .eml, .zip, .mbox, .json",
            )
    if not any(
        Path(temp_manager.safe_filename(f.filename)).suffix.lower()
        in _DATA_EXTENSIONS
        for f in files
    ):
        raise HTTPException(
            status_code=400,
            detail="Upload must include at least one .eml, .zip, or .mbox file",
        )

    job_id = uuid.uuid4().hex
    job_dir = temp_manager.create_job_dirs(job_id)
    total = 0
    names = []
    try:
        for f in files:
            target = temp_manager.stage_stream(
                job_dir, f.filename, f.file, settings.max_upload_bytes
            )
            total += target.stat().st_size
            names.append(target.name)
    except ValueError as exc:
        temp_manager.purge_job_dir(job_dir)
        raise HTTPException(status_code=400, detail=str(exc))

    job = db.create_job(
        job_id, ", ".join(names)[:500], total, str(job_dir)
    )
    runner.start_job(job_id)
    return _to_out(job)


@app.post("/api/jobs/paste", response_model=JobOut, status_code=201)
async def create_paste_job(body: PasteJobIn):
    """Create an audit job from raw pasted email source (RFC 822 text)."""
    filename = temp_manager.safe_filename(body.filename, "pasted_email.eml")
    if not filename.lower().endswith(".eml"):
        filename += ".eml"

    job_id = uuid.uuid4().hex
    job_dir = temp_manager.create_job_dirs(job_id)
    path = temp_manager.stage_text(job_dir, filename, body.content)
    job = db.create_job(
        job_id, path.name, path.stat().st_size, str(job_dir)
    )
    runner.start_job(job_id)
    return _to_out(job)


@app.get("/api/mail/providers")
async def mail_providers(email: str = ""):
    """Return provider/server discovery data without accepting credentials."""
    address = email.strip()
    server, port = mailbox_download.resolve_imap(address)
    provider = mailbox_download.provider_for_email(address)
    return {
        "provider": provider,
        "imap_server": server,
        "imap_port": port,
        "use_ssl": port == 993,
        "oauth_configured": (
            oauth.is_configured(provider) if provider in {"google", "microsoft"} else None
        ),
        "oauth_callback_url": (
            oauth.callback_url(provider) if provider in {"google", "microsoft"} else None
        ),
        "known_domains": sorted(mailbox_download.IMAP_SERVERS),
    }


@app.post("/api/mail/jobs", response_model=JobOut, status_code=201)
async def create_mail_job(body: MailCredentialsIn):
    """Start a non-OAuth IMAP job. The supplied secret is never persisted."""
    address = _validate_email(body.email)
    provider = mailbox_download.provider_for_email(address)
    if provider == "microsoft":
        raise HTTPException(
            status_code=400,
            detail="Microsoft accounts must use the permission-based OAuth button.",
        )
    if provider == "google" and not body.use_app_password:
        raise HTTPException(
            status_code=400,
            detail="Google accounts must use OAuth or explicitly choose the app-password fallback.",
        )
    password = body.password
    if provider == "google":
        # Google displays app passwords in four groups. IMAP expects the same
        # 16 characters without presentation whitespace.
        password = "".join(password.split())
        if len(password) != 16 or not password.isalnum():
            raise HTTPException(
                status_code=400,
                detail="A Google app password must contain 16 characters (letters or digits).",
            )
    auth = {
        "password": password,
        "imap_server": body.imap_server,
        "imap_port": body.imap_port,
        "use_ssl": body.use_ssl,
    }
    return _to_out(_create_mail_job(address, body.days, auth))


@app.post("/api/mail/oauth/start")
async def start_mail_oauth(body: OAuthStartIn):
    address = _validate_email(body.email)
    expected = mailbox_download.provider_for_email(address)
    if body.provider not in {"google", "microsoft"}:
        raise HTTPException(status_code=400, detail="Unsupported OAuth provider")
    if expected != body.provider:
        raise HTTPException(
            status_code=400,
            detail=f"This address is configured for {expected}, not {body.provider}.",
        )
    try:
        authorization_url, state = oauth.start_flow(body.provider, address, body.days)
    except oauth.OAuthError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "authorization_url": authorization_url,
        "state": state,
        "message_origin": settings.public_backend_url,
    }


@app.get("/api/mail/oauth/{provider}/callback", response_class=HTMLResponse)
async def mail_oauth_callback(
    provider: str,
    state: str = Query(default=""),
    code: str = Query(default=""),
    error: str = Query(default=""),
):
    """Exchange the provider code, start the job, and notify the opener window."""
    try:
        if error:
            raise oauth.OAuthError(f"Permission was not granted: {error}")
        if not state or not code:
            raise oauth.OAuthError("The OAuth callback was incomplete")
        flow = oauth.take_flow(state, provider)
        token = oauth.exchange_code(provider, code, flow)
        job = _create_mail_job(flow["email"], flow["days"], {"access_token": token})
        message = {"type": "email-doctor-oauth", "jobId": job["id"]}
        title = "Permission granted"
        detail = "The mailbox download has started. You can close this window."
    except oauth.OAuthError as exc:
        message = {"type": "email-doctor-oauth", "error": str(exc)}
        title = "Could not connect mailbox"
        detail = str(exc)
    payload = json.dumps(message).replace("<", "\\u003c")
    origin = json.dumps(settings.frontend_url)
    safe_title = html.escape(title)
    safe_detail = html.escape(detail)
    return HTMLResponse(
        f"""<!doctype html><html><head><meta charset="utf-8"><title>{safe_title}</title></head>
<body style="font-family:system-ui;padding:2rem"><h2>{safe_title}</h2><p>{safe_detail}</p>
<script>if(window.opener){{window.opener.postMessage({payload},{origin});setTimeout(()=>window.close(),500);}}</script>
</body></html>"""
    )


@app.get("/api/jobs", response_model=list[JobOut])
async def list_jobs():
    jobs = db.list_jobs()
    for job in jobs:
        job["log"] = ""  # keep the list payload light
    return [_to_out(j) for j in jobs]


@app.get("/api/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: str):
    job = _get_or_404(job_id)
    return _to_out(job, Path(job["temp_dir"]) if job.get("temp_dir") else None)


@app.get("/api/jobs/{job_id}/files")
async def list_output_files(job_id: str):
    job = _get_or_404(job_id)
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job is not completed")
    return {"files": temp_manager.list_output_files(Path(job["temp_dir"]))}


@app.get("/api/jobs/{job_id}/snapshot-files")
async def list_snapshot_files(job_id: str):
    job = _get_or_404(job_id)
    if not job.get("snapshot_available"):
        raise HTTPException(status_code=404, detail="No audit snapshot is available yet")
    return {
        "files": temp_manager.list_files_under(Path(job["temp_dir"]), "snapshot_outputs")
    }


@app.get("/api/jobs/{job_id}/snapshot-files/{rel_path:path}")
async def get_snapshot_file(job_id: str, rel_path: str):
    job = _get_or_404(job_id)
    target = temp_manager.resolve_snapshot_output(Path(job["temp_dir"]), rel_path)
    if target is None:
        raise HTTPException(status_code=404, detail="Snapshot file not found")
    return FileResponse(target)


@app.get("/api/jobs/{job_id}/files/{rel_path:path}")
async def get_output_file(job_id: str, rel_path: str):
    job = _get_or_404(job_id)
    target = temp_manager.resolve_output(Path(job["temp_dir"]), rel_path)
    if target is None:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target)


@app.post("/api/jobs/{job_id}/discard", response_model=JobOut)
async def discard(job_id: str):
    job = _get_or_404(job_id)
    if job["status"] in ("completed", "failed", "discarded"):
        raise HTTPException(
            status_code=400, detail="Only queued or in-progress jobs can be discarded"
        )
    runner.discard_job(job_id)
    return _to_out(_get_or_404(job_id))


@app.get("/api/jobs/{job_id}/download-zip")
async def download_zip(job_id: str):
    job = _get_or_404(job_id)
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job is not completed")
    zip_path = Path(job["zip_path"] or "")
    if not zip_path.is_file():
        raise HTTPException(status_code=404, detail="ZIP archive not found")
    stem = Path(job["filename"].split(",")[0]).stem or "audit"
    return FileResponse(
        zip_path, filename=f"{stem}_audit.zip", media_type="application/zip"
    )
