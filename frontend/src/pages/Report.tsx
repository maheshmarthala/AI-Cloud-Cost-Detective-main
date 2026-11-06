import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api';
import type { Analysis } from '../types';
import { exportAnalysisToCsv } from '../utils/csvExport';

function Command({command}: {command:string}) {
  const [status,setStatus] = useState('Copy');
  return <div className="command"><pre><code>{command}</code></pre><button onClick={async()=> { try { await navigator.clipboard.writeText(command); setStatus('Copied'); } catch { setStatus('Select text to copy'); } }}>{status}</button></div>;
}

export default function Report() {
  const {id} = useParams();
  const [row,setRow] = useState<Analysis>(), [error,setError] = useState('');

  useEffect(() => {
    let active = true;
    const load = () => api<Analysis>(`/analyses/${id}`).then(value=>{if(active) setRow(value);}).catch(e=>{if(active) setError(e.message);});
    void load(); const timer = window.setInterval(load, 3000);
    return () => { active=false; window.clearInterval(timer); };
  }, [id]);

  if (error) return <p role="alert" className="error">{error}</p>;
  if (!row) return <p>Loading report…</p>;

  return (
    <>
      <Link to="/history">← History</Link>
      <div className="section-title" style={{ marginTop: '14px', alignItems: 'flex-start' }}>
        <div>
          <p className="eyebrow" style={{ marginTop: 0 }}>ANALYSIS REPORT</p>
          <h1 style={{ margin: '6px 0 10px' }}>{row.scope}</h1>
          <p className="muted" style={{ margin: 0 }}>
            {new Date(row.created_at).toLocaleString()} · {row.status}
          </p>
        </div>
        {row.status === 'completed' && (
          <button
            onClick={() => exportAnalysisToCsv(row)}
            className="primary"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', marginTop: '14px' }}
            title="Download analysis report as a CSV spreadsheet"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Download CSV
          </button>
        )}
      </div>

      {row.scan_config && (
        <p className="muted">
          Regions: {row.scan_config.regions.join(', ')} · Services: {row.scan_config.services.join(', ')}
          {Object.keys(row.scan_config.tag_filters).length > 0 && ` · Tags: ${JSON.stringify(row.scan_config.tag_filters)}`}
        </p>
      )}

      {row.status === 'failed' ? (
        <p role="alert" className="error">{row.analysis_result.error}</p>
      ) : row.status !== 'completed' ? (
        <div className="card">
          <p>Investigation in progress. This report will update automatically.</p>
        </div>
      ) : (
        <>
          <div className="feature-grid">
            {[
              ['Resources scanned', row.resources_scanned],
              ['Issues to review', row.issues_found],
              ['Estimated savings', row.estimated_savings]
            ].map(([label, value]) => (
              <div className="card" key={label}>
                <p className="muted">{label}</p>
                <h2>{value}</h2>
              </div>
            ))}
          </div>

          <section className="card">
            <h2>Investigation summary</h2>
            <p>{row.analysis_result.summary}</p>
            {row.analysis_result.limitations?.map(text => (
              <p className="muted" key={text}>{text}</p>
            ))}
          </section>

          <p className="muted">
            AI recommendations may be incomplete. Verify utilization, pricing, ownership, and backups before changing resources. Commands are never run automatically.
          </p>

          {row.analysis_result.issues?.length === 0 && (
            <section className="card">No issues identified from the available evidence.</section>
          )}

          {row.analysis_result.issues?.map((issue, index) => (
            <article className="card" key={index}>
              <div className="section-title">
                <h2>{issue.resource_name}</h2>
                <span className={`badge ${issue.severity}`}>{issue.severity}</span>
              </div>
              <p className="eyebrow">{issue.issue_type}</p>
              <p>{issue.explanation}</p>
              <p className="muted">Potential savings: {issue.estimated_savings}</p>
              <Command command={issue.fix_command} />
            </article>
          ))}
        </>
      )}
    </>
  );
}
