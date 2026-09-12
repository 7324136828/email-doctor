# Genesis

based on the skills, can you create based on the original-project so that it will have everything in the root? Make sure you follow the guidance of productionization. Also make sure we can have a UI in React.js such that the user can paste/select the input files/data to be processed, create a temp folder under the system's temp folder, pipe the data through the script, and allow the user to retrieve the resulting output file? Create a backend with the Python code based on original-project. Make sure you have setup.bat/setup.sh files that will dispatch setup.py to set up the virtual environment, and run.bat/run.sh files to dispatch both the frontend and backend. You can have multiple screens to support them etc.

I'll look for Python scripts under a skills directory in this workspace.

There's a `skill` directory (singular). Let me check its contents.

Found the scripts. Let me read the skill docs and the Python files to understand their features.

The README files are blocked by an ignore file. Let me check which ignore rules apply and whether the Python scripts are accessible.

The Python scripts may also be blocked. Let me check for nested ignore files and test whether the .py files are readable.

The `skill/.gitignore` file excludes `original-project`, so I'm blocked from reading those scripts directly — likely intentional since the folder contains `credential.json`, `credential.bk`, and email data. Let me check the rest of the productionization doc and the git tracking state, which will tell me what I can legitimately infer.

Important caveat first: `skill/.gitignore` contains `original-project`, so all the scripts under `skill/original-project/` are intentionally excluded from my file access (likely because the folder contains `credential.json`, `credential.bk`, and real email data). I can't read the script bodies, but the file inventory, output artifacts, and the `productionization` skill doc give a clear picture of what they do.

## What the scripts are — an inbox audit / cleanup pipeline ("email-doctor")

| Script / artifact | Inferred feature |
|---|---|
| `email_downloader.py` + `credential.json` + `email_downloader.log` | Connects to a mailbox (IMAP, e.g. Gmail app-password) and downloads messages, presumably as `.eml` files, with logging |
| `eml_extract.py` → `messages.jsonl` | Parses `.eml` files into structured records (sender, subject, date, `List-Unsubscribe` headers, etc.) |
| `export_eml.py` | Exports selected/filtered messages back out as `.eml` files |
| `inbox_summary.py` → `senders.csv`, `summary.json`, `summary.md`, `unsubscribe.csv` | Aggregates the inbox: top senders, per-sender counts, unsubscribe-link candidates, human-readable summary |
| `gen_report.py` → `inbox_audit.html` | Renders a standalone HTML audit report |
| `worklist.py` → `inbox_cleanup_worklist.csv`, `worklist.json` | Produces an actionable cleanup worklist (unsubscribe / delete / archive decisions grouped by sender) |
| `rebrand.py`, `aliases.json`, `_domain_aliases.json`, `messages_grouped.jsonl` | Sender normalization — groups aliases/domains so "no-reply@mail.x.com" and "news@x.com" roll up to one entity |
| `annotations.json` | User-supplied labels/decisions that feed back into the worklist |
| `summarize_emails.py` | Content-level summarization of emails (possibly LLM-assisted) |
| `text_to_speech.py`, `text_to_speech_sapi.py` | Speaks the summary aloud (SAPI = Windows Speech API) — an accessibility/convenience feature |
| `run.bat` / `run_all.bat` / `run_audit.bat` | End-to-end pipeline orchestration |

The four `feature N` folders look like progressive iterations: feature 2 = downloader only, feature 3 = extract + summary reports, feature 4 = full audit with worklist + HTML report, feature 1 = everything including TTS.

The `productionization` skill (`SKILL.md`) is a blueprint for turning these scripts into a full-stack app: React frontend + FastAPI backend, isolated temp-dir job execution, ZIP output download, job history dashboard, cross-platform setup/run scripts, and credential hygiene. Note the template is written generically around "PDF conversion" — here the payload is email data instead.

## Stories with INVEST criteria

Each story is written to satisfy INVEST (Independent, Negotiable, Valuable, Estimable, Small, Testable). Estimates in story points.

### Epic 1 — Backend pipeline

**S1. Submit an audit job**
As a user, I want to upload a ZIP/folder of `.eml` files (or mailbox export) via `POST /api/jobs` so the backend can run the audit pipeline on it.
- AC: endpoint accepts upload, returns `job_id` + `in_progress`; invalid types rejected with 400.
- INVEST: independent entry point; testable via HTTP client; ~3 pts.

**S2. Isolated job workspace**
As the system, I want every job to run in a unique directory under the system temp folder so concurrent jobs never collide and the repo stays clean.
- AC: `tempfile.gettempdir()/prod_jobs/<uuid>/{inputs,work,outputs,archive}` created; nothing written to repo.
- INVEST: small, self-contained; verifiable by filesystem assertion; ~2 pts.

**S3. Pipeline adapter for original scripts**
As a developer, I want a service layer that invokes the `original-project` scripts with explicit `--input`/`--output-dir` args so legacy logic is reused without modification.
- AC: subprocess invocation captures stdout/stderr; non-zero exit marks job failed with error message.
- INVEST: negotiable (import vs. subprocess); testable with fixture `.eml` files; ~5 pts.

**S4. Job state machine + persistence**
As a user, I want job status (`queued → in_progress → completed/failed/discarded`) persisted in SQLite so history survives restarts.
- AC: schema fields per SKILL.md; status transitions recorded with timestamps.
- INVEST: independent of UI; testable via unit tests on state transitions; ~3 pts.

**S5. Job status & log endpoint**
As a user, I want `GET /api/jobs/{id}` to return status, progress %, and captured logs so the UI can poll for updates.
- AC: returns progress 0–100 and tail of stdout/stderr; 404 for unknown id.
- INVEST: small; testable end-to-end against a running job; ~2 pts.

**S6. ZIP packaging + download**
As a user, I want `GET /api/jobs/{id}/download-zip` to return a ZIP of all outputs (report, CSVs, summary) so I can take results with one click.
- AC: ZIP contains every file under `outputs/`; 400 if job not completed.
- INVEST: independent; testable by unzipping response; ~2 pts.

**S7. Discard running job**
As a user, I want `POST /api/jobs/{id}/discard` to terminate the process and purge the temp folder so I can abort a mistaken run.
- AC: process killed, temp dir deleted, status = `discarded`.
- INVEST: testable by asserting dir removal + state; ~3 pts.

### Epic 2 — Frontend

**S8. Upload landing page**
As a user, I want a landing page where I can pick, drag-and-drop, or Ctrl+V-paste my email export so starting an audit takes seconds.
- AC: all three input modes stage the file and trigger `POST /api/jobs`.
- INVEST: independent of history screen; testable in browser; ~5 pts.

**S9. Live progress monitor**
As a user, I want a multi-stage progress indicator and collapsible log viewer so I can see what the pipeline is doing.
- AC: polls `GET /api/jobs/{id}`; shows stage labels + streamed logs; terminal states clearly displayed.
- INVEST: depends only on S5 contract; ~3 pts.

**S10. History dashboard**
As a user, I want a history screen listing all jobs with auto-refresh and per-status actions (Continue / Discard / Download ZIP) so I can manage past and current audits.
- AC: table auto-polls every ~4s; in-progress rows show Continue+Discard; completed rows show Download.
- INVEST: negotiable table columns; testable against seeded job DB; ~5 pts.

**S11. Results viewer**
As a user, I want to preview `summary.md`, `senders.csv`, and the cleanup worklist in the browser before downloading so I can sanity-check results.
- AC: renders markdown + tabular CSVs for completed jobs.
- INVEST: independent of download story; ~3 pts.

### Epic 3 — Platform & hygiene

**S12. Cross-platform setup**
As a new developer, I want `setup.bat`/`setup.sh` → `setup.py` to create the venv, install backend + frontend deps, and seed `.env` so setup is one command.
- AC: fresh clone → working stack on Windows and POSIX.
- INVEST: testable on clean checkout; ~3 pts.

**S13. Unified run scripts**
As a user, I want `run.bat`/`run.sh` to launch frontend + backend together with graceful shutdown so I don't manage two processes.
- AC: both services up; Ctrl+C kills both cleanly.
- INVEST: small, testable; ~2 pts.

**S14. Secrets audit & remediation**
As a maintainer, I want a repo-wide secret scan that masks findings and records locations in `secrets.md` so no credential (e.g. the existing `credential.json`) is ever committed.
- AC: scan runs; `secrets.md` lists path/line/category only — never values; `.env` + credential files gitignored.
- INVEST: independent; testable by re-running scanner; ~3 pts.

### Ordering note

S2 → S3 → S4 form the critical path (workspace → adapter → persistence); S1 and S5–S7 are thin API layers on top. Frontend stories need only the API contracts, not finished implementations, so they can proceed in parallel with mocks.

Two things worth confirming with you: (1) whether the app should keep requiring mailbox credentials (downloader feature) or only accept exported `.eml`/ZIP input — that changes S1's scope significantly; (2) if you want me to analyze the actual script logic rather than infer from filenames, you'd need to move the code out from under the `original-project` ignore rule — though I'd recommend keeping `credential*.json`, `email.txt`, and the `audit_out/`/`report/` data folders ignored regardless.