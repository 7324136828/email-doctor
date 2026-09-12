import React, { useEffect, useRef, useState } from 'react';

export default function LogViewer({ log }) {
  const [open, setOpen] = useState(true);
  const preRef = useRef(null);

  useEffect(() => {
    if (open && preRef.current) {
      preRef.current.scrollTop = preRef.current.scrollHeight;
    }
  }, [log, open]);

  return (
    <div className="log-viewer">
      <button className="link-btn" onClick={() => setOpen((o) => !o)}>
        {open ? 'Hide log' : 'Show log'}
      </button>
      {open && (
        <pre ref={preRef} className="log">
          {log || '(waiting for output…)'}
        </pre>
      )}
    </div>
  );
}
