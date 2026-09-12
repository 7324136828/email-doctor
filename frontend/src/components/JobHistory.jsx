import React, { useEffect, useState } from 'react';
import { discardJob, downloadZipUrl, listJobs } from '../services/api';

function elapsed(job) {
  const start = new Date(job.created_at);
  const end = job.completed_at ? new Date(job.completed_at) : new Date();
  const secs = Math.max(0, Math.round((end - start) / 1000));
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

function fmtSize(bytes) {
  if (bytes > 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024).toFixed(1)} KB`;
}

export default function JobHistory({ onContinue }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = async () => {
    try {
      setJobs(await listJobs());
      setError('');
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const timer = setInterval(load, 4000);
    return () => clearInterval(timer);
  }, []);

  const handleDiscard = async (jobId) => {
    if (
      !window.confirm(
        'Discard this in-progress job? Its temporary files will be purged.'
      )
    )
      return;
    try {
      await discardJob(jobId);
      load();
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="card">
      <h2>Audit history</h2>
      {error && <div className="banner error">{error}</div>}
      {loading ? (
        <p className="muted">Loading history…</p>
      ) : jobs.length === 0 ? (
        <p className="muted">No audits yet. Start one from the New Audit tab.</p>
      ) : (
        <div className="table-wrap">
          <table className="jobs-table">
            <thead>
              <tr>
                <th>Job</th>
                <th>Filename</th>
                <th>Size</th>
                <th>Created</th>
                <th>Elapsed</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id} className={`status-${job.status}`}>
                  <td className="mono">{job.id.slice(0, 8)}</td>
                  <td>{job.filename}</td>
                  <td>{fmtSize(job.file_size)}</td>
                  <td>{new Date(job.created_at).toLocaleString()}</td>
                  <td>{elapsed(job)}</td>
                  <td>
                    <span className={`badge badge-${job.status}`}>
                      {job.status}
                    </span>
                  </td>
                  <td>
                    <div className="btn-group">
                      {job.status === 'in_progress' ||
                      job.status === 'queued' ? (
                        <>
                          <button
                            className="btn small"
                            onClick={() => onContinue(job.id)}
                          >
                            Continue
                          </button>
                          <button
                            className="btn small danger"
                            onClick={() => handleDiscard(job.id)}
                          >
                            Discard
                          </button>
                        </>
                      ) : null}
                      {job.status === 'completed' && (
                        <>
                          <button
                            className="btn small"
                            onClick={() => onContinue(job.id)}
                          >
                            View
                          </button>
                          <a
                            className="btn small primary"
                            href={downloadZipUrl(job.id)}
                            download
                          >
                            Download ZIP
                          </a>
                        </>
                      )}
                      {(job.status === 'failed' ||
                        job.status === 'discarded') && (
                        <button
                          className="btn small"
                          onClick={() => onContinue(job.id)}
                        >
                          Details
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
