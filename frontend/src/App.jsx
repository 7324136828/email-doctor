import React, { useState } from 'react';
import FileUpload from './components/FileUpload';
import JobStatus from './components/JobStatus';
import JobHistory from './components/JobHistory';
import MailboxConnect from './components/MailboxConnect';

export default function App() {
  const [screen, setScreen] = useState('audit'); // 'audit' | 'history'
  const [activeJobId, setActiveJobId] = useState(null);
  const [source, setSource] = useState('mailbox');

  const continueJob = (id) => {
    setActiveJobId(id);
    setScreen('audit');
  };

  return (
    <div className="app">
      <nav className="navbar">
        <span className="brand">email-doctor</span>
        <div className="nav-links">
          <button
            className={screen === 'audit' ? 'nav-btn active' : 'nav-btn'}
            onClick={() => setScreen('audit')}
          >
            New Audit
          </button>
          <button
            className={screen === 'history' ? 'nav-btn active' : 'nav-btn'}
            onClick={() => setScreen('history')}
          >
            History
          </button>
        </div>
      </nav>

      <main className="content">
        {screen === 'audit' &&
          (activeJobId ? (
            <JobStatus jobId={activeJobId} onReset={() => setActiveJobId(null)} />
          ) : (
            <>
              <div className="source-switch" role="tablist" aria-label="Audit source">
                <button
                  className={source === 'mailbox' ? 'active' : ''}
                  onClick={() => setSource('mailbox')}
                >
                  Connect inbox
                </button>
                <button
                  className={source === 'files' ? 'active' : ''}
                  onClick={() => setSource('files')}
                >
                  Upload export
                </button>
              </div>
              {source === 'mailbox' ? (
                <MailboxConnect onJobCreated={setActiveJobId} />
              ) : (
                <FileUpload onJobCreated={setActiveJobId} />
              )}
            </>
          ))}
        {screen === 'history' && <JobHistory onContinue={continueJob} />}
      </main>
    </div>
  );
}
