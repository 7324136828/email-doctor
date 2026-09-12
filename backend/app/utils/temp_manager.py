"""Isolated job workspace management under the system temp directory.

Every job runs inside ``<system-temp>/email_doctor_jobs/<job_uuid>/`` so no
upload, scratch file, or output ever touches the repository.
"""
import shutil
import zipfile
from pathlib import Path

from ..config import settings

SUBDIRS = ("inputs", "work", "outputs", "archive")
ZIP_NAME = "audit_output.zip"


def job_dir_for(job_id: str) -> Path:
    return settings.jobs_root / job_id


def create_job_dirs(job_id: str) -> Path:
    job_dir = job_dir_for(job_id)
    for sub in SUBDIRS:
        (job_dir / sub).mkdir(parents=True, exist_ok=True)
    return job_dir


def safe_filename(name: str | None, fallback: str = "upload") -> str:
    """Reduce an arbitrary client-supplied name to a plain basename."""
    cleaned = Path(name or "").name.strip()
    return cleaned or fallback


def stage_stream(job_dir: Path, filename: str, stream, max_bytes: int) -> Path:
    """Write an upload stream into inputs/, enforcing a cumulative size cap."""
    inputs = job_dir / "inputs"
    target = _dedupe(inputs, safe_filename(filename))
    written = 0
    with open(target, "wb") as fh:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                fh.close()
                target.unlink(missing_ok=True)
                raise ValueError("Upload exceeds maximum allowed size")
            fh.write(chunk)
    return target


def stage_text(job_dir: Path, filename: str, content: str) -> Path:
    target = _dedupe(job_dir / "inputs", safe_filename(filename, "pasted.eml"))
    target.write_text(content, encoding="utf-8", errors="replace")
    return target


def _dedupe(directory: Path, name: str) -> Path:
    candidate = directory / name
    stem, suffix = candidate.stem, candidate.suffix
    i = 1
    while candidate.exists():
        candidate = directory / f"{stem}_{i}{suffix}"
        i += 1
    return candidate


def prepare_inputs(job_dir: Path) -> None:
    """Extract any uploaded .zip archives in place so the pipeline only ever
    sees a flat folder of .eml / .mbox / .json inputs."""
    inputs = job_dir / "inputs"
    for archive in sorted(inputs.glob("*.zip")):
        dest = _dedupe(inputs, archive.stem + "_extracted")
        dest.mkdir(parents=True, exist_ok=True)
        _safe_extract(archive, dest)


def _safe_extract(archive: Path, dest: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            name = member.filename
            # Skip directories, absolute paths and traversal attempts.
            if member.is_dir() or name.startswith(("/", "\\")) or ".." in Path(name).parts:
                continue
            zf.extract(member, dest)


def package_outputs(job_dir: Path) -> Path:
    outputs = job_dir / "outputs"
    archive_dir = job_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    zip_path = archive_dir / ZIP_NAME
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in sorted(outputs.rglob("*")):
            if file.is_file():
                zf.write(file, arcname=str(file.relative_to(outputs)))
    return zip_path


def list_output_files(job_dir: Path) -> list[str]:
    return list_files_under(job_dir, "outputs")


def list_files_under(job_dir: Path, folder: str) -> list[str]:
    outputs = job_dir / folder
    if not outputs.is_dir():
        return []
    return sorted(
        str(p.relative_to(outputs)).replace("\\", "/")
        for p in outputs.rglob("*")
        if p.is_file()
    )


def resolve_output(job_dir: Path, rel_path: str) -> Path | None:
    """Resolve a user-supplied relative path inside outputs/ safely."""
    outputs = (job_dir / "outputs").resolve()
    candidate = (outputs / rel_path).resolve()
    try:
        candidate.relative_to(outputs)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def resolve_snapshot_output(job_dir: Path, rel_path: str) -> Path | None:
    outputs = (job_dir / "snapshot_outputs").resolve()
    candidate = (outputs / rel_path).resolve()
    try:
        candidate.relative_to(outputs)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def replace_snapshot_outputs(job_dir: Path, source: Path) -> None:
    """Publish a complete snapshot only after its pipeline run succeeds."""
    resolved_job = job_dir.resolve()
    root = settings.jobs_root.resolve()
    if resolved_job == root or root not in resolved_job.parents:
        raise ValueError("Snapshot target is outside the managed jobs root")
    target = resolved_job / "snapshot_outputs"
    if target.exists():
        shutil.rmtree(target)
    shutil.move(str(source), str(target))


def purge_job_dir(job_dir: Path) -> None:
    # Only ever delete inside the managed jobs root.
    resolved = job_dir.resolve()
    root = settings.jobs_root.resolve()
    if resolved == root or root not in resolved.parents:
        return
    shutil.rmtree(resolved, ignore_errors=True)
