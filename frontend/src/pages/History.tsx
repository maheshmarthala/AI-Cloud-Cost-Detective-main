import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import type { Analysis } from '../types';
import { exportAnalysisToCsv } from '../utils/csvExport';

export default function History() {
  const [rows, setRows] = useState<Analysis[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<Analysis[]>('/history')
      .then(setRows)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <p className="eyebrow">INVESTIGATION ARCHIVE</p>
      <h1>Your analysis history</h1>
      <p className="lead">Your latest 100 investigations, saved for reference.</p>
      {error && <p role="alert" className="error">{error}</p>}

      <section className="card">
        {loading ? (
          <p>Loading history…</p>
        ) : rows.length === 0 ? (
          <p className="muted">
            No investigations yet. <Link to="/">Run your first analysis.</Link>
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Account / scan scope</th>
                  <th>Created</th>
                  <th>Status</th>
                  <th>Issues</th>
                  <th>Estimated savings</th>
                  <th>Export</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(row => (
                  <tr key={row.id}>
                    <td>
                      <Link to={`/reports/${row.id}`}>{row.scope}</Link>
                    </td>
                    <td>{new Date(row.created_at).toLocaleString()}</td>
                    <td>
                      <span className={`badge ${row.status === 'completed' ? 'low' : row.status === 'failed' ? 'high' : 'medium'}`}>
                        {row.status}
                      </span>
                    </td>
                    <td>{row.issues_found}</td>
                    <td>{row.estimated_savings}</td>
                    <td>
                      {row.status === 'completed' && (
                        <button
                          onClick={() => exportAnalysisToCsv(row)}
                          style={{ padding: '4px 10px', fontSize: '12px' }}
                          title="Download CSV report"
                        >
                          CSV
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
