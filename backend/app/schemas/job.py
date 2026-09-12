"""Pydantic request / response schemas."""
from pydantic import BaseModel, Field


class JobOut(BaseModel):
    id: str
    filename: str
    file_size: int
    status: str
    progress: int
    stage: str | None = None
    log: str = ""
    error_message: str | None = None
    created_at: str
    completed_at: str | None = None
    output_files: list[str] = Field(default_factory=list)
    source_kind: str = "upload"
    account_email: str | None = None
    days: int | None = None
    downloaded_messages: int = 0
    total_messages: int | None = None
    snapshot_available: bool = False
    snapshot_at: str | None = None


class PasteJobIn(BaseModel):
    content: str = Field(min_length=1)
    filename: str | None = None


class MailCredentialsIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=4096)
    days: int = Field(default=7, ge=1, le=3650)
    imap_server: str | None = Field(default=None, max_length=253)
    imap_port: int | None = Field(default=None, ge=1, le=65535)
    use_ssl: bool | None = None
    use_app_password: bool = False


class OAuthStartIn(BaseModel):
    provider: str
    email: str = Field(min_length=3, max_length=320)
    days: int = Field(default=7, ge=1, le=3650)
