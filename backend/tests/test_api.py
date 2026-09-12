import io
import time
import zipfile

from fastapi.testclient import TestClient

from app.main import app
from conftest import SAMPLE_EML


def _wait_for_terminal(client: TestClient, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed", "discarded"):
            return job
        time.sleep(0.4)
    raise AssertionError(f"job {job_id} did not finish: {job}")


def test_full_job_lifecycle():
    with TestClient(app) as client:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for i in range(3):
                zf.writestr(f"emails/msg_{i}.eml", SAMPLE_EML.format(n=i))
        buf.seek(0)

        resp = client.post(
            "/api/jobs",
            files=[("files", ("inbox.zip", buf, "application/zip"))],
        )
        assert resp.status_code == 201, resp.text
        job_id = resp.json()["id"]

        job = _wait_for_terminal(client, job_id)
        assert job["status"] == "completed", job["log"]
        assert job["progress"] == 100
        assert "report/summary.json" in job["output_files"]

        listing = client.get(f"/api/jobs/{job_id}/files").json()
        assert "inbox_audit.html" in listing["files"]

        md = client.get(f"/api/jobs/{job_id}/files/report/summary.md")
        assert md.status_code == 200 and "Inbox Summary" in md.text

        dl = client.get(f"/api/jobs/{job_id}/download-zip")
        assert dl.status_code == 200
        assert dl.headers["content-type"] == "application/zip"

        jobs = client.get("/api/jobs").json()
        assert any(j["id"] == job_id for j in jobs)


def test_paste_job():
    with TestClient(app) as client:
        resp = client.post(
            "/api/jobs/paste",
            json={"content": SAMPLE_EML.format(n=1), "filename": "pasted"},
        )
        assert resp.status_code == 201, resp.text
        job = _wait_for_terminal(client, resp.json()["id"])
        assert job["status"] == "completed", job["log"]


def test_rejects_bad_extension():
    with TestClient(app) as client:
        resp = client.post(
            "/api/jobs",
            files=[("files", ("evil.exe", io.BytesIO(b"MZ"), "application/x-msdownload"))],
        )
        assert resp.status_code == 400


def test_unknown_job_404():
    with TestClient(app) as client:
        assert client.get("/api/jobs/nope").status_code == 404
        assert client.post("/api/jobs/nope/discard").status_code == 404


def test_mail_provider_discovery():
    with TestClient(app) as client:
        google = client.get("/api/mail/providers?email=user@gmail.com").json()
        assert google["provider"] == "google"
        assert google["imap_server"] == "imap.gmail.com"
        assert google["oauth_configured"] is False
        assert google["oauth_callback_url"].endswith("/api/mail/oauth/google/callback")

        proton = client.get("/api/mail/providers?email=user@proton.me").json()
        assert proton["provider"] == "credentials"
        assert proton["imap_port"] == 1143
        assert proton["use_ssl"] is False


def test_mail_password_is_not_persisted(monkeypatch):
    captured = {}

    def fake_start(job_id, auth):
        captured.update(auth)

    monkeypatch.setattr("app.main.runner.start_mailbox_job", fake_start)
    with TestClient(app) as client:
        response = client.post(
            "/api/mail/jobs",
            json={
                "email": "user@yahoo.com",
                "password": "one-time-app-password",
                "days": 3,
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["source_kind"] == "mailbox"
        assert body["days"] == 3
        assert "password" not in body
        persisted = client.get(f"/api/jobs/{body['id']}").text
        assert "one-time-app-password" not in persisted
        assert captured["password"] == "one-time-app-password"


def test_google_password_flow_is_rejected():
    with TestClient(app) as client:
        response = client.post(
            "/api/mail/jobs",
            json={"email": "user@gmail.com", "password": "not-used", "days": 7},
        )
        assert response.status_code == 400
        assert "OAuth" in response.json()["detail"]


def test_google_app_password_fallback_is_explicit(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.main.runner.start_mailbox_job", lambda _id, auth: captured.update(auth)
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/mail/jobs",
            json={
                "email": "user@gmail.com",
                "password": "abcd efgh ijkl mnop",
                "days": 7,
                "use_app_password": True,
            },
        )
        assert response.status_code == 201, response.text
        assert captured["password"] == "abcdefghijklmnop"


def test_google_app_password_requires_sixteen_characters():
    with TestClient(app) as client:
        response = client.post(
            "/api/mail/jobs",
            json={
                "email": "user@gmail.com",
                "password": "regular-password",
                "days": 7,
                "use_app_password": True,
            },
        )
        assert response.status_code == 400
        assert "16 characters" in response.json()["detail"]


def test_mocked_mailbox_job_runs_snapshot_and_final_audit(monkeypatch):
    def fake_download(*, output_dir, progress, on_batch, **_kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        total = 3
        progress(0, total)
        for index in range(1, total + 1):
            (output_dir / f"{index}.eml").write_text(
                SAMPLE_EML.format(n=index), encoding="utf-8"
            )
            progress(index, total)
            on_batch(index, total)
        return total, total

    monkeypatch.setattr("app.services.runner.mailbox_download.download_inbox", fake_download)
    with TestClient(app) as client:
        response = client.post(
            "/api/mail/jobs",
            json={"email": "user@yahoo.com", "password": "temporary", "days": 5},
        )
        assert response.status_code == 201, response.text
        job = _wait_for_terminal(client, response.json()["id"])
        assert job["status"] == "completed", job["log"]
        assert job["downloaded_messages"] == 3
        assert job["total_messages"] == 3
        assert "report/email_briefing.md" in job["output_files"]
        snapshot = client.get(f"/api/jobs/{job['id']}/snapshot-files")
        assert snapshot.status_code == 200
        assert "report/summary.json" in snapshot.json()["files"]
