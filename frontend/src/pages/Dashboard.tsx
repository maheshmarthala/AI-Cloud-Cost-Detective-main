import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import type { Analysis, ProgressEvent, ScanOptions } from '../types';
import ProgressTracker from '../components/ProgressTracker';
export default function Dashboard() {
  const [options, setOptions] = useState<ScanOptions>();
  const [regions, setRegions] = useState<string[]>([]), [services, setServices] = useState<string[]>(['ec2', 'ebs', 'rds', 's3']);
  const [tagKey, setTagKey] = useState(''), [tagValue, setTagValue] = useState('');
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [events, setEvents] = useState<ProgressEvent[]>([]), [analysisId, setAnalysisId] = useState('');
  const socket = useRef<WebSocket | null>(null);
  const navigate = useNavigate();
  async function loadOptions() {
    setLoading(true); setError('');
    try { const result = await api<ScanOptions>('/scan-options'); setOptions(result); setRegions([result.default_region]); }
    catch(e) { setOptions(undefined); setRegions([]); setError((e as Error).message); } finally { setLoading(false); }
  }
  useEffect(() => { void loadOptions(); }, []);
  useEffect(() => {
    if (!analysisId) return;
    let disposed = false, checking = false;
    const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/progress/${analysisId}`);
    socket.current = ws;
    ws.onopen = () => ws.send(JSON.stringify({token:localStorage.getItem('token')}));
    function finish(status: string, message?: string) {
      if (disposed) return;
      if (status === 'completed') { setBusy(false); navigate(`/reports/${analysisId}`); }
      if (status === 'failed') { setBusy(false); setError(message || 'Analysis failed.'); setAnalysisId(''); }
    }
    ws.onmessage = event => { const next = JSON.parse(event.data) as ProgressEvent; setEvents(previous => [...previous, next]); finish(next.status, next.message); };
    // REST polling handles socket failures, server restarts, and terminal-event races.
    const timer = window.setInterval(async () => {
      if (checking) return; checking = true;
      try { const row = await api<Analysis>(`/analyses/${analysisId}`); finish(row.status, row.analysis_result.error); }
      catch(e) { if (!disposed) setError((e as Error).message); } finally { checking = false; }
    }, 2000);
    return () => { disposed = true; window.clearInterval(timer); ws.close(); socket.current = null; };
  }, [analysisId, navigate]);
  async function run() {
    if (!options) return;
    setBusy(true); setError(''); setEvents([]);
    try { const result = await api<{analysis_id:string}>('/analyze', {method:'POST', body:JSON.stringify({account_id:options.account_id, regions, services, tag_filters:tagKey ? {[tagKey]:tagValue} : {}})}); setAnalysisId(result.analysis_id); }
    catch(e) { setError((e as Error).message); setBusy(false); }
  }
  return <><p className="eyebrow">AWS COST INTELLIGENCE</p><h1>Find where your cloud spend goes.</h1><p className="lead">Scan your AWS account by region and service. No Resource Group is needed.</p>
    <section className="card"><div className="section-title"><div><h2>New investigation</h2><p className="muted">Read-only scanning. Fix commands are suggestions for your review.</p></div><span className="badge low">AWS</span></div>
      {error && <p role="alert" className="error">{error}</p>}
      <label>Connected AWS account<input readOnly value={options?.account_id ?? ''} placeholder={loading ? 'Checking backend AWS identity…' : 'No account connected'}/></label>
      <p className="muted">Uses the backend IAM role or AWS CLI profile. To switch accounts, change backend authentication and refresh. Never enter access keys here.</p>
      {options?.warnings.map(note=><p className="muted" key={note}>{note}</p>)}
      <label>Regions (select up to 5)<select multiple disabled={loading || busy} value={regions} onChange={e=>setRegions(Array.from(e.target.selectedOptions, option=>option.value))}>
        {options?.regions.map(region=><option key={region}>{region}</option>)}
      </select></label>
      <small className="muted">Use Ctrl or Command to select multiple regions.</small>
      <fieldset disabled={loading || busy}><legend>Services</legend><div className="service-options">{(options?.services ?? ['ec2', 'ebs', 'rds', 's3', 'elbv2']).map(service=><label key={service}>
        <input type="checkbox" checked={services.includes(service)} onChange={e=>setServices(previous=>e.target.checked ? [...previous, service] : previous.filter(value=>value!==service))}/>{service.toUpperCase()}
      </label>)}</div></fieldset>
      <div className="feature-grid"><label>Tag key (optional)<input maxLength={128} disabled={busy} value={tagKey} onChange={e=>setTagKey(e.target.value)} placeholder="Environment"/></label>
      <label>Tag value<input maxLength={256} disabled={busy || !tagKey} value={tagValue} onChange={e=>setTagValue(e.target.value)} placeholder="Production"/></label></div>
      <p className="muted">Configuration review only. Actual costs and rightsizing require billing, pricing, and utilization data, which are not connected.</p>
      <div className="actions"><button className="primary" onClick={run} disabled={busy || loading || !options || regions.length===0 || regions.length>5 || services.length===0}>{busy ? 'Investigating…' : 'Run analysis →'}</button><button onClick={loadOptions} disabled={busy || loading}>Refresh account</button></div>
    </section>{(busy || events.length > 0) && <ProgressTracker events={events}/>}
    <div className="feature-grid">{[['01','Discover','Inventory resources and their configuration.'],['02','Investigate','Review evidence and possible cost issues.'],['03','Act','Verify recommendations before making changes.']].map(([step,title,text])=><article className="card" key={step}><p className="eyebrow">{step}</p><h2>{title}</h2><p className="muted">{text}</p></article>)}</div></>;
}
