import json
import zipfile

from app.services.pipeline import run_pipeline
from app.utils import temp_manager

from conftest import HUMAN_EML, SAMPLE_EML


def _seed_inputs(job_dir, count=12):
    inputs = job_dir / "inputs"
    for i in range(count):
        (inputs / f"news_{i}.eml").write_text(
            SAMPLE_EML.format(n=i), encoding="utf-8"
        )
    (inputs / "human.eml").write_text(HUMAN_EML, encoding="utf-8")


def test_run_pipeline_produces_all_outputs(job_dir):
    _seed_inputs(job_dir)
    run_pipeline(job_dir)

    outputs = job_dir / "outputs"
    for rel in (
        "messages.jsonl",
        "messages_grouped.jsonl",
        "_domain_aliases.json",
        "report/senders.csv",
        "report/summary.json",
        "report/summary.md",
        "report/email_briefing.md",
        "report/recent_emails.csv",
        "report/unsubscribe.csv",
        "inbox_cleanup_worklist.csv",
        "worklist.json",
        "inbox_audit.html",
    ):
        assert (outputs / rel).is_file(), rel

    summary = json.loads((outputs / "report/summary.json").read_text())
    assert summary["total_messages"] == 13
    assert summary["unique_senders"] == 2  # mail.example.com -> example.com

    worklist = json.loads((outputs / "worklist.json").read_text())
    by_group = {i["sender_group"]: i for i in worklist["items"]}
    assert by_group["example.com"]["recommended_action"] == "unsubscribe_and_purge"
    assert by_group["friends.org"]["recommended_action"] == "keep"

    html = (outputs / "inbox_audit.html").read_text()
    assert "example.com" in html and "unsubscribe_and_purge" in html
    briefing = (outputs / "report/email_briefing.md").read_text()
    assert "Weekly digest" in briefing and "Lunch on Friday" in briefing


def test_package_outputs_zip(job_dir):
    _seed_inputs(job_dir, count=2)
    run_pipeline(job_dir)
    zip_path = temp_manager.package_outputs(job_dir)
    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert "inbox_audit.html" in names
    assert "report/summary.json" in names


def test_mbox_input(job_dir):
    import mailbox

    mbox_path = job_dir / "inputs" / "list.mbox"
    box = mailbox.mbox(mbox_path)
    for i in range(3):
        box.add(mailbox.mboxMessage(SAMPLE_EML.format(n=i)))
    box.flush()
    box.close()

    run_pipeline(job_dir)
    summary = json.loads(
        (job_dir / "outputs/report/summary.json").read_text()
    )
    assert summary["total_messages"] == 3


def test_empty_inputs_fail(job_dir):
    import pytest

    from app.services.pipeline import PipelineError

    with pytest.raises(PipelineError):
        run_pipeline(job_dir)
