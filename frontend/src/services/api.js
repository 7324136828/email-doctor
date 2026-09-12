const BASE = '/api';

async function req(path, options) {
  const resp = await fetch(`${BASE}${path}`, options);
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail || detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(`${resp.status}: ${detail}`);
  }
  return resp.json();
}

export function listJobs() {
  return req('/jobs');
}

export function getJob(id) {
  return req(`/jobs/${id}`);
}

export function createJob(files) {
  const form = new FormData();
  for (const f of files) form.append('files', f, f.name);
  return req('/jobs', { method: 'POST', body: form });
}

export function createPasteJob(content, filename) {
  return req('/jobs/paste', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, filename }),
  });
}

export function discoverMailProvider(email) {
  return req(`/mail/providers?email=${encodeURIComponent(email)}`);
}

export function createMailJob(payload) {
  return req('/mail/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function startMailOAuth(provider, email, days) {
  return req('/mail/oauth/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider, email, days }),
  });
}

export function discardJob(id) {
  return req(`/jobs/${id}/discard`, { method: 'POST' });
}

export function listOutputFiles(id) {
  return req(`/jobs/${id}/files`);
}

export function downloadZipUrl(id) {
  return `${BASE}/jobs/${id}/download-zip`;
}

export function outputFileUrl(id, relPath) {
  const encoded = relPath.split('/').map(encodeURIComponent).join('/');
  return `${BASE}/jobs/${id}/files/${encoded}`;
}

export function snapshotFileUrl(id, relPath) {
  const encoded = relPath.split('/').map(encodeURIComponent).join('/');
  return `${BASE}/jobs/${id}/snapshot-files/${encoded}`;
}

export function listSnapshotFiles(id) {
  return req(`/jobs/${id}/snapshot-files`);
}

export async function fetchOutputText(id, relPath) {
  const resp = await fetch(outputFileUrl(id, relPath));
  if (!resp.ok) throw new Error(`${resp.status}: ${resp.statusText}`);
  return resp.text();
}

export async function fetchSnapshotText(id, relPath) {
  const resp = await fetch(snapshotFileUrl(id, relPath));
  if (!resp.ok) throw new Error(`${resp.status}: ${resp.statusText}`);
  return resp.text();
}
