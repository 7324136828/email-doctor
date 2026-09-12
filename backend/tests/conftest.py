import os
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Redirect job state to a throwaway location before app modules read settings.
_TMP = Path(tempfile.mkdtemp(prefix="email_doctor_test_"))
os.environ["JOBS_ROOT"] = str(_TMP / "jobs")
os.environ["JOBS_DB"] = str(_TMP / "jobs.db")

SAMPLE_EML = """From: Newsletter Bot <news@mail.example.com>
To: user@test.local
Subject: Weekly digest {n}
Date: Mon, 05 Aug 2024 10:0{n}:00 +0000
Message-ID: <msg{n}@mail.example.com>
List-Unsubscribe: <https://mail.example.com/unsub?token={n}>
MIME-Version: 1.0
Content-Type: text/plain; charset="utf-8"

Hello, here is your weekly digest number {n}.
"""

HUMAN_EML = """From: Alice Smith <alice@friends.org>
To: user@test.local
Subject: Lunch on Friday?
Date: Tue, 06 Aug 2024 09:15:00 +0000
Message-ID: <lunch@friends.org>
MIME-Version: 1.0
Content-Type: text/plain; charset="utf-8"

Are you still up for lunch on Friday?
"""


def make_job_dir(base: Path) -> Path:
    job_dir = base / "job1"
    for sub in ("inputs", "work", "outputs", "archive"):
        (job_dir / sub).mkdir(parents=True, exist_ok=True)
    return job_dir


@pytest.fixture()
def job_dir(tmp_path):
    return make_job_dir(tmp_path)
