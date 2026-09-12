# email-doctor

Full-stack inbox audit tool. Connect a live mailbox or upload an email export
(`.eml` files, a `.zip` of them, or an `.mbox` archive) and get a cleanup report: top senders,
unsubscribe candidates, a per-sender action worklist, and a standalone HTML
audit — packaged as a downloadable ZIP.

## Connect a mailbox

Open **New Audit → Connect inbox**, enter an address, and choose how many days
to include. The app searches only `INBOX`, downloads with `BODY.PEEK[]` so it
does not mark messages read, publishes partial audit snapshots during long
downloads, and then runs the complete audit. Passwords, app passwords, and
OAuth access tokens stay in process memory and are never stored in SQLite or a
job directory.

- Gmail, Googlemail, ScarletMail: Google OAuth permission screen, with an
  explicit Google app-password fallback when OAuth is not configured.
- Outlook, Hotmail, Live, MSN, UCR: Microsoft OAuth permission screen.
- AOL, Yahoo, QQ/Foxmail and other IMAP services: provider app password.
- Proton Mail domains: local Proton Mail Bridge at `127.0.0.1:1143`.
- Unknown domains default to `imap.<domain>:993`; Advanced settings can
  override the host, port, and implicit TLS choice.

For OAuth, register the redirect URIs shown in `.env.example` with Google and
Microsoft, then set the corresponding client credentials in `.env`. Provider
admin or test-user approval may also be required.

The requested N-day overview is written to `report/email_briefing.md`, with a
complete message inventory in `report/recent_emails.csv`.

## Stack

- **Backend** — Python + FastAPI. Each job runs the audit pipeline as a
  subprocess inside an isolated workspace under the system temp folder
  (`<temp>/email_doctor_jobs/<uuid>/`). Job history persists in SQLite.
- **Frontend** — React (Vite SPA) with a file-picker / drag-and-drop / `Ctrl+V`
  upload screen, live progress + log viewer, results preview, and a persistent
  job history dashboard.

## Quick start

**Windows**

```bat
setup.bat
run.bat
```

**macOS / Linux**

```sh
chmod +x setup.sh run.sh
./setup.sh
./run.sh
```

`setup.*` dispatches `setup.py`, which creates `.venv`, installs
`backend/requirements.txt`, runs `npm install` in `frontend/`, and seeds
`.env` from `.env.example`.

`run.*` launches both services:

- Backend API + interactive docs: http://localhost:8000/docs
- Frontend: http://localhost:5173

## Inputs

| Type | Notes |
|---|---|
| `.eml` | One or many raw RFC 822 message files |
| `.zip` | Archive containing `.eml` / `.mbox` files (extracted in place) |
| `.mbox` | Standard mbox mailbox export |
| `aliases.json` | Optional sender rollups: `{"example.com": ["mail.example.com"]}` or `{"mail.example.com": "example.com"}` |
| `annotations.json` | Optional per-sender action overrides: `{"example.com": "keep"}` or `{"example.com": {"action": "keep", "note": "…"}}` |

Raw email source can also be pasted directly into the UI.

## Outputs (per job, zipped)

```
messages.jsonl / messages_grouped.jsonl / _domain_aliases.json
report/senders.csv  report/unsubscribe.csv  report/summary.json  report/summary.md
report/email_briefing.md  report/recent_emails.csv
inbox_cleanup_worklist.csv  worklist.json  inbox_audit.html
```

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/jobs` | Multipart upload (`files`), starts an audit job |
| `POST` | `/api/jobs/paste` | JSON `{content, filename?}` raw-source job |
| `GET` | `/api/mail/providers?email=…` | Discover auth mode and IMAP server |
| `POST` | `/api/mail/jobs` | Start app-password/custom IMAP audit |
| `POST` | `/api/mail/oauth/start` | Start Google/Microsoft permission flow |
| `GET` | `/api/jobs` | List all jobs |
| `GET` | `/api/jobs/{id}` | Status, progress %, stage, log |
| `GET` | `/api/jobs/{id}/files` | List output files |
| `GET` | `/api/jobs/{id}/files/{path}` | Download a single output file |
| `GET` | `/api/jobs/{id}/snapshot-files` | List partial audit files |
| `GET` | `/api/jobs/{id}/download-zip` | Download the consolidated ZIP |
| `POST` | `/api/jobs/{id}/discard` | Terminate + purge temp workspace |

## Tests

```sh
.venv\Scripts\python -m pytest backend/tests   # Windows
.venv/bin/python -m pytest backend/tests       # POSIX
```

## Layout

```
backend/    FastAPI app + audit pipeline (app/services/stages/*)
frontend/   React SPA (Vite)
skill/      productionization standard + preserved legacy `original-project/`
setup.py    cross-platform environment provisioning
setup.bat / setup.sh   setup launchers
run.bat / run.sh       launch frontend + backend together
secrets.md  credential-hygiene audit trail (locations only, no values)
```
