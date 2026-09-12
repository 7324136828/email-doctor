import React, { useEffect, useState } from 'react';
import DOMPurify from 'dompurify';
import { marked } from 'marked';
import {
  downloadZipUrl,
  fetchOutputText,
  fetchSnapshotText,
  listOutputFiles,
  listSnapshotFiles,
  outputFileUrl,
  snapshotFileUrl,
} from '../services/api';

const PREVIEW_ROWS = 25;

function parseCSV(text) {
  const rows = [];
  let row = [];
  let field = '';
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += c;
      }
    } else if (c === '"') {
      inQuotes = true;
    } else if (c === ',') {
      row.push(field);
      field = '';
    } else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      row.push(field);
      field = '';
      if (row.some((v) => v !== '')) rows.push(row);
      row = [];
    } else {
      field += c;
    }
  }
  row.push(field);
  if (row.some((v) => v !== '')) rows.push(row);
  return rows;
}

function CsvTable({ title, text }) {
  const rows = parseCSV(text);
  if (!rows.length) return null;
  const [header, ...body] = rows;
  return (
    <section className="result-section">
      <h3>{title}</h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {header.map((h, i) => (
                <th key={i}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.slice(0, PREVIEW_ROWS).map((r, i) => (
              <tr key={i}>
                {r.map((c, j) => (
                  <td key={j}>{c}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {body.length > PREVIEW_ROWS && (
        <p className="muted small">
          Showing {PREVIEW_ROWS} of {body.length} rows — download the ZIP for the
          full file.
        </p>
      )}
    </section>
  );
}

export default function ResultsPanel({ jobId, snapshot = false }) {
  const [files, setFiles] = useState([]);
  const [summary, setSummary] = useState(null);
  const [summaryHtml, setSummaryHtml] = useState('');
  const [briefingHtml, setBriefingHtml] = useState('');
  const [sendersCsv, setSendersCsv] = useState('');
  const [worklistCsv, setWorklistCsv] = useState('');
  const [unsubCsv, setUnsubCsv] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const { files: list } = await (snapshot
          ? listSnapshotFiles(jobId)
          : listOutputFiles(jobId));
        if (cancelled) return;
        setFiles(list);
        const grabber = snapshot ? fetchSnapshotText : fetchOutputText;
        const grab = (rel) =>
          list.includes(rel) ? grabber(jobId, rel) : Promise.resolve('');
        const [summaryJson, summaryMd, briefingMd, senders, worklist, unsub] =
          await Promise.all([
            grab('report/summary.json'),
            grab('report/summary.md'),
            grab('report/email_briefing.md'),
            grab('report/senders.csv'),
            grab('inbox_cleanup_worklist.csv'),
            grab('report/unsubscribe.csv'),
          ]);
        if (cancelled) return;
        if (summaryJson) setSummary(JSON.parse(summaryJson));
        if (summaryMd)
          setSummaryHtml(DOMPurify.sanitize(marked.parse(summaryMd)));
        if (briefingMd)
          setBriefingHtml(DOMPurify.sanitize(marked.parse(briefingMd)));
        setSendersCsv(senders);
        setWorklistCsv(worklist);
        setUnsubCsv(unsub);
      } catch (e) {
        if (!cancelled) setError(e.message);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [jobId, snapshot]);

  if (error) return <div className="banner error">{error}</div>;

  return (
    <div className="results">
      <h3>{snapshot ? 'Audit snapshot' : 'Results'}</h3>
      {snapshot && (
        <div className="banner info">
          This is a partial audit of messages downloaded so far. It refreshes during ingestion.
        </div>
      )}

      {summary && (
        <div className="stat-cards">
          <div className="stat">
            <div className="stat-num">{summary.total_messages}</div>
            <div className="stat-lbl">Messages</div>
          </div>
          <div className="stat">
            <div className="stat-num">{summary.unique_senders}</div>
            <div className="stat-lbl">Sender groups</div>
          </div>
          <div className="stat">
            <div className="stat-num">{summary.senders_with_unsubscribe}</div>
            <div className="stat-lbl">Unsubscribe-ready</div>
          </div>
          <div className="stat">
            <div className="stat-num">
              {(summary.total_size_bytes / 1024).toFixed(0)} KB
            </div>
            <div className="stat-lbl">Total size</div>
          </div>
        </div>
      )}

      <div className="btn-row">
        {files.includes('inbox_audit.html') && (
          <a
            className="btn"
            href={(snapshot ? snapshotFileUrl : outputFileUrl)(jobId, 'inbox_audit.html')}
            target="_blank"
            rel="noreferrer"
          >
            Open full HTML report
          </a>
        )}
        {!snapshot && (
          <a className="btn primary" href={downloadZipUrl(jobId)} download>
            Download ZIP
          </a>
        )}
      </div>

      {briefingHtml && (
        <section
          className="result-section markdown briefing"
          dangerouslySetInnerHTML={{ __html: briefingHtml }}
        />
      )}

      {summaryHtml && (
        <section
          className="result-section markdown"
          dangerouslySetInnerHTML={{ __html: summaryHtml }}
        />
      )}

      {sendersCsv && <CsvTable title="Top senders" text={sendersCsv} />}
      {worklistCsv && (
        <CsvTable title="Cleanup worklist" text={worklistCsv} />
      )}
      {unsubCsv && (
        <CsvTable title="Unsubscribe candidates" text={unsubCsv} />
      )}
    </div>
  );
}
