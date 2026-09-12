import React, { useEffect, useState } from 'react';
import { discardJob, downloadZipUrl, getJob } from '../services/api';
import LogViewer from './LogViewer';
import ResultsPanel from './ResultsPanel';

const STAGE_LABELS = {
  connecting: 'Connecting to mailbox',
  downloading: 'Downloading recent INBOX messages',
  snapshot: 'Refreshing audit snapshot',
  starting: 'Starting',
  extract: 'Parsing messages',
  group: 'Grouping senders',
  summarize: 'Building summary',
  worklist: 'Generating cleanup worklist',
  report: 'Rendering HTML report',
  done: 'Done',
};

const TERMINAL = ['completed', 'failed', 'discarded'];

export default function JobStatus({ jobId, onReset }) {
  const [job, setJob] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    let timer;
    const poll = async () => {
      try {
        const j = await getJob(jobId);
        if (cancelled) return;
        setJob(j);
        if (!TERMINAL.includes(j.status)) {
          timer = setTimeout(poll, 1500);
        }
      } catch (e) {
        if (!cancelled) setError(e.message);
      }
    };
    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [jobId]);

  const handleDiscard = async () => {
    if (!window.confirm('Discard this job and purge its temporary files?'))
      return;
    try {
      await discardJob(jobId);
      const j = await getJob(jobId).catch(() => null);
      if (j) setJob(j);
    } catch (e) {
      setError(e.message);
    }
  };

  if (!job) return <p className="muted">{error || 'Loading job…'}</p>;

  const running = !TERMINAL.includes(job.status);
  const stageLabel = STAGE_LABELS[job.stage] || job.stage || job.status;

  return (
    <div className="card">
      <div className="job-header">
        <h2>Audit {job.id.slice(0, 8)}</h2>
        <span className={`badge badge-${job.status}`}>{job.status}</span>
      </div>
      <p className="muted small">{job.filename}</p>

      {job.source_kind === 'mailbox' && job.total_messages !== null && (
        <p className="mail-count">
          <strong>{job.downloaded_messages}</strong> of <strong>{job.total_messages}</strong>{' '}
          recent messages downloaded
        </p>
      )}

      <div className="progress-row">
        <div className="progress">
          <div
            className={`progress-fill ${job.status}`}
            style={{ width: `${job.progress}%` }}
          />
        </div>
        <span className="muted small">
          {job.progress}% — {stageLabel}
        </span>
      </div>

      {job.error_message && (
        <div className="banner error">{job.error_message}</div>
      )}
      {error && <div className="banner error">{error}</div>}

      <LogViewer log={job.log} />

      <div className="btn-row">
        {running && (
          <button className="btn danger" onClick={handleDiscard}>
            Discard job
          </button>
        )}
        {job.status === 'completed' && (
          <a className="btn primary" href={downloadZipUrl(job.id)} download>
            Download ZIP
          </a>
        )}
        {TERMINAL.includes(job.status) && (
          <button className="btn" onClick={onReset}>
            New audit
          </button>
        )}
      </div>

      {job.status === 'completed' && <ResultsPanel jobId={job.id} />}
      {job.status !== 'completed' && job.snapshot_available && (
        <ResultsPanel
          key={job.snapshot_at || 'snapshot'}
          jobId={job.id}
          snapshot
        />
      )}
    </div>
  );
}
