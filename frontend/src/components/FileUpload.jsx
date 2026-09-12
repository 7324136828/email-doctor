import React, { useEffect, useRef, useState } from 'react';
import { createJob, createPasteJob } from '../services/api';

const ACCEPTED = ['.eml', '.zip', '.mbox', '.json'];
const DATA_EXT = ['.eml', '.zip', '.mbox'];

function ext(name) {
  const i = name.lastIndexOf('.');
  return i >= 0 ? name.slice(i).toLowerCase() : '';
}

export default function FileUpload({ onJobCreated }) {
  const [files, setFiles] = useState([]);
  const [pasteText, setPasteText] = useState('');
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const inputRef = useRef(null);

  const addFiles = (fileList) => {
    const incoming = Array.from(fileList || []);
    const rejected = incoming.filter((f) => !ACCEPTED.includes(ext(f.name)));
    if (rejected.length) {
      setError(
        `Skipped unsupported file(s): ${rejected.map((f) => f.name).join(', ')}`
      );
    } else {
      setError('');
    }
    const ok = incoming.filter((f) => ACCEPTED.includes(ext(f.name)));
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
      return [...prev, ...ok.filter((f) => !seen.has(`${f.name}:${f.size}`))];
    });
  };

  // Ctrl+V paste: stage files dropped onto the clipboard.
  useEffect(() => {
    const handlePaste = (e) => {
      const items = e.clipboardData?.items;
      if (!items) return;
      const pasted = [];
      for (const item of items) {
        if (item.kind === 'file') {
          const f = item.getAsFile();
          if (f) pasted.push(f);
        }
      }
      if (pasted.length) {
        e.preventDefault();
        addFiles(pasted);
      }
    };
    window.addEventListener('paste', handlePaste);
    return () => window.removeEventListener('paste', handlePaste);
  }, []);

  const removeFile = (target) =>
    setFiles((prev) => prev.filter((f) => f !== target));

  const hasDataFile = files.some((f) => DATA_EXT.includes(ext(f.name)));

  const submit = async () => {
    setError('');
    setSubmitting(true);
    try {
      let job;
      if (files.length) {
        if (!hasDataFile) {
          throw new Error(
            'Add at least one .eml, .zip or .mbox file (aliases.json / annotations.json are optional extras).'
          );
        }
        job = await createJob(files);
      } else if (pasteText.trim()) {
        job = await createPasteJob(pasteText, 'pasted_email.eml');
      } else {
        throw new Error('Provide files or paste raw email source first.');
      }
      onJobCreated(job.id);
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="card upload-card">
      <h2>Audit an inbox export</h2>
      <p className="muted">
        Drop a <code>.zip</code> of <code>.eml</code> files, individual{' '}
        <code>.eml</code> files, or an <code>.mbox</code> archive — or paste raw
        email source below. Optional <code>aliases.json</code> /{' '}
        <code>annotations.json</code> files are picked up automatically.
      </p>

      <div
        className={dragging ? 'dropzone dragging' : 'dropzone'}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          addFiles(e.dataTransfer.files);
        }}
      >
        <p>
          <strong>Click to choose files</strong>, drag &amp; drop, or press{' '}
          <kbd>Ctrl</kbd>+<kbd>V</kbd> to paste
        </p>
        <p className="muted small">Accepted: .eml, .zip, .mbox, .json</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          hidden
          accept=".eml,.zip,.mbox,.json"
          onChange={(e) => {
            addFiles(e.target.files);
            e.target.value = '';
          }}
        />
      </div>

      {files.length > 0 && (
        <ul className="file-list">
          {files.map((f) => (
            <li key={`${f.name}:${f.size}`}>
              <span className="file-name">{f.name}</span>
              <span className="muted small">
                {(f.size / 1024).toFixed(1)} KB
              </span>
              <button className="link-btn" onClick={() => removeFile(f)}>
                remove
              </button>
            </li>
          ))}
        </ul>
      )}

      <details className="paste-box">
        <summary>Or paste raw email source (.eml)</summary>
        <textarea
          rows={8}
          placeholder={'From: ...\nTo: ...\nSubject: ...\n\n(message body)'}
          value={pasteText}
          onChange={(e) => setPasteText(e.target.value)}
        />
      </details>

      {error && <div className="banner error">{error}</div>}

      <button
        className="btn primary"
        disabled={submitting || (!files.length && !pasteText.trim())}
        onClick={submit}
      >
        {submitting ? 'Starting…' : 'Start audit'}
      </button>
    </div>
  );
}
