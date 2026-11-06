import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api';
export function AuthForm({ signup = false }: { signup?: boolean }) {
  const [email, setEmail] = useState(''), [password, setPassword] = useState('');
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { const result = await api<{access_token:string}>(`/auth/${signup ? 'signup' : 'login'}`, { method:'POST', body:JSON.stringify({email, password}) }); localStorage.setItem('token', result.access_token); navigate('/'); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <main className="auth"><div className="brand">◈ Cost Detective</div><div className="card"><p className="eyebrow">YOUR CLOUD, UNDERSTOOD</p><h1>{signup ? 'Create your account' : 'Welcome back'}</h1><p className="muted">Investigate AWS costs. Find your next saving.</p><form onSubmit={submit}>
    <label>Email<input type="email" autoComplete="email" required maxLength={254} value={email} onChange={e=>setEmail(e.target.value)}/></label>
    <label>Password<input type="password" autoComplete={signup ? 'new-password' : 'current-password'} required minLength={12} maxLength={72} value={password} onChange={e=>setPassword(e.target.value)}/></label><small className="muted">Use 12–72 characters (at most 72 UTF-8 bytes).</small>
    {error && <p role="alert" className="error">{error}</p>}<button disabled={busy} className="primary">{busy ? 'Please wait…' : signup ? 'Create account' : 'Sign in'}</button>
    </form><p className="muted">{signup ? 'Already have an account? ' : 'New here? '}<Link to={signup ? '/login' : '/signup'}>{signup ? 'Sign in' : 'Create account'}</Link></p></div></main>;
}
export default function Login() { return <AuthForm/>; }
