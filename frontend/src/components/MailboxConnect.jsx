import React, { useEffect, useRef, useState } from 'react';
import {
  createMailJob,
  discoverMailProvider,
  startMailOAuth,
} from '../services/api';

const PROVIDER_NAMES = {
  google: 'Google',
  microsoft: 'Microsoft',
  credentials: 'IMAP',
};

export default function MailboxConnect({ onJobCreated }) {
  const [email, setEmail] = useState('');
  const [days, setDays] = useState(7);
  const [password, setPassword] = useState('');
  const [discovery, setDiscovery] = useState(null);
  const [server, setServer] = useState('');
  const [port, setPort] = useState(993);
  const [useSsl, setUseSsl] = useState(true);
  const [advanced, setAdvanced] = useState(false);
  const [useAppPassword, setUseAppPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const expectedOrigin = useRef('');

  const discover = async () => {
    if (!email.includes('@')) return null;
    const info = await discoverMailProvider(email.trim());
    setDiscovery(info);
    setServer(info.imap_server);
    setPort(info.imap_port);
    setUseSsl(info.use_ssl);
    setUseAppPassword(info.provider === 'google' && !info.oauth_configured);
    return info;
  };

  useEffect(() => {
    const receive = (event) => {
      if (expectedOrigin.current && event.origin !== expectedOrigin.current) return;
      if (event.data?.type !== 'email-doctor-oauth') return;
      setBusy(false);
      if (event.data.error) setError(event.data.error);
      if (event.data.jobId) onJobCreated(event.data.jobId);
    };
    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, [onJobCreated]);

  const connect = async () => {
    setError('');
    if (!email.includes('@')) {
      setError('Enter a valid email address.');
      return;
    }
    const popup = window.open('', 'email-doctor-oauth', 'width=600,height=720');
    setBusy(true);
    try {
      const info = discovery || (await discover());
      if (
        (info.provider === 'google' || info.provider === 'microsoft') &&
        !useAppPassword
      ) {
        if (!info.oauth_configured) {
          throw new Error(
            `${PROVIDER_NAMES[info.provider]} OAuth setup is required. Add the OAuth application settings to .env and restart the app.`
          );
        }
        const started = await startMailOAuth(info.provider, email.trim(), Number(days));
        expectedOrigin.current = started.message_origin;
        if (!popup) throw new Error('Allow pop-ups to grant mailbox permission.');
        popup.location = started.authorization_url;
      } else {
        popup?.close();
        if (!password) throw new Error('Enter the mailbox password or provider app password.');
        const job = await createMailJob({
          email: email.trim(),
          password,
          days: Number(days),
          imap_server: server || info.imap_server,
          imap_port: Number(port || info.imap_port),
          use_ssl: useSsl,
          use_app_password: useAppPassword,
        });
        setPassword('');
        onJobCreated(job.id);
      }
    } catch (e) {
      popup?.close();
      setError(e.message);
      setBusy(false);
    }
  };

  const oauthProvider =
    discovery && ['google', 'microsoft'].includes(discovery.provider);
  const oauth = oauthProvider && !useAppPassword;
  const oauthBlocked = oauth && !discovery.oauth_configured;

  return (
    <div className="card mailbox-card">
      <h2>Connect an inbox</h2>
      <p className="muted">
        Download recent messages from <strong>INBOX</strong>, audit them as they arrive,
        and create a day-by-day briefing. Messages remain unread on the server.
      </p>

      <div className="form-grid">
        <label className="field field-wide">
          <span>Email address</span>
          <input
            type="email"
            autoComplete="username"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              setDiscovery(null);
            }}
            onBlur={() => discover().catch((e) => setError(e.message))}
          />
        </label>
        <label className="field">
          <span>Summarize the last</span>
          <div className="inline-input">
            <input
              type="number"
              min="1"
              max="3650"
              value={days}
              onChange={(e) => setDays(e.target.value)}
            />
            <span>days</span>
          </div>
        </label>

        {discovery && (
          <div className="provider-note field-wide">
            <strong>{PROVIDER_NAMES[discovery.provider]} connection</strong>
            <span>{discovery.imap_server}:{discovery.imap_port}</span>
          </div>
        )}

        {discovery?.provider === 'google' && (
          <fieldset className="auth-method field-wide">
            <legend>Authentication method</legend>
            <label className={!discovery.oauth_configured ? 'disabled-option' : ''}>
              <input
                type="radio"
                name="google-auth-method"
                checked={!useAppPassword}
                disabled={!discovery.oauth_configured}
                onChange={() => setUseAppPassword(false)}
              />
              <span>
                <strong>Google OAuth</strong>
                <small>Grant access on Google’s official sign-in page.</small>
              </span>
            </label>
            <label>
              <input
                type="radio"
                name="google-auth-method"
                checked={useAppPassword}
                onChange={() => setUseAppPassword(true)}
              />
              <span>
                <strong>Google app password</strong>
                <small>Use a 16-character password created after enabling 2-Step Verification.</small>
              </span>
            </label>
            {!discovery.oauth_configured && (
              <small className="oauth-unavailable">
                OAuth is unavailable until <code>GOOGLE_OAUTH_CLIENT_ID</code> and{' '}
                <code>GOOGLE_OAUTH_CLIENT_SECRET</code> are configured.
              </small>
            )}
          </fieldset>
        )}

        {oauthBlocked && discovery.provider === 'microsoft' && (
          <div className="banner info field-wide oauth-setup">
            <strong>{PROVIDER_NAMES[discovery.provider]} OAuth setup required</strong>
            <span>
              Add <code>
                {discovery.provider === 'google'
                  ? 'GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET'
                  : 'MICROSOFT_OAUTH_CLIENT_ID'}
              </code>{' '}
              to <code>.env</code>, register this callback URL, and restart the app:
            </span>
            <code>{discovery.oauth_callback_url}</code>
          </div>
        )}

        {discovery && !oauth && (
          <label className="field field-wide">
            <span>
              {discovery.provider === 'google' ? 'Google app password' : 'Password / app password'}
            </span>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <small>
              {discovery.provider === 'google'
                ? 'Paste the 16-character app password. Spaces are accepted and removed automatically.'
                : 'Used for this connection only; it is never written to disk.'}
            </small>
          </label>
        )}
      </div>

      {discovery && !oauth && (
        <details open={advanced} onToggle={(e) => setAdvanced(e.currentTarget.open)}>
          <summary>Advanced IMAP settings</summary>
          <div className="form-grid advanced-fields">
            <label className="field field-wide">
              <span>Server</span>
              <input value={server} onChange={(e) => setServer(e.target.value)} />
            </label>
            <label className="field">
              <span>Port</span>
              <input type="number" value={port} onChange={(e) => setPort(e.target.value)} />
            </label>
            <label className="check-field">
              <input type="checkbox" checked={useSsl} onChange={(e) => setUseSsl(e.target.checked)} />
              SSL/TLS from connection start
            </label>
          </div>
        </details>
      )}

      {error && <div className="banner error">{error}</div>}
      <button
        className="btn primary"
        disabled={busy || !email || !days || oauthBlocked}
        onClick={connect}
      >
        {busy
          ? 'Waiting…'
          : oauthBlocked
            ? 'OAuth setup required'
          : oauth
            ? `Continue with ${PROVIDER_NAMES[discovery.provider]}`
            : 'Connect and audit'}
      </button>
      {!discovery && email.includes('@') && (
        <p className="muted small">Leave the email field to detect its provider, or click Connect.</p>
      )}
    </div>
  );
}
