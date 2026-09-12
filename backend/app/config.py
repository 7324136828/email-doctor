"""Environment configuration for the email-doctor backend.

All settings resolve from environment variables; sensible defaults are used for
local development. See .env.example at the repository root.
"""
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent

load_dotenv(ROOT_DIR / ".env")


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings:
    app_name: str = "email-doctor"
    host: str = os.environ.get("BACKEND_HOST", "0.0.0.0")
    port: int = int(os.environ.get("BACKEND_PORT", "8000"))
    cors_origins: list[str] = _split(
        os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    )
    # Root under the system temp directory where every job gets an isolated folder.
    jobs_root: Path = Path(
        os.environ.get(
            "JOBS_ROOT", str(Path(tempfile.gettempdir()) / "email_doctor_jobs")
        )
    )
    db_path: Path = Path(os.environ.get("JOBS_DB", str(BACKEND_DIR / "jobs.db")))
    max_upload_bytes: int = int(
        os.environ.get("MAX_UPLOAD_BYTES", str(200 * 1024 * 1024))
    )
    log_char_cap: int = int(os.environ.get("JOB_LOG_CHAR_CAP", "200000"))
    allowed_extensions: frozenset[str] = frozenset({".eml", ".zip", ".mbox", ".json"})
    public_backend_url: str = os.environ.get(
        "PUBLIC_BACKEND_URL", "http://localhost:8000"
    ).rstrip("/")
    frontend_url: str = os.environ.get("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    google_oauth_client_id: str = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
    google_oauth_client_secret: str = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
    microsoft_oauth_client_id: str = os.environ.get("MICROSOFT_OAUTH_CLIENT_ID", "")
    microsoft_oauth_client_secret: str = os.environ.get(
        "MICROSOFT_OAUTH_CLIENT_SECRET", ""
    )
    snapshot_every_messages: int = max(
        1, int(os.environ.get("MAIL_SNAPSHOT_EVERY_MESSAGES", "25"))
    )


settings = Settings()
