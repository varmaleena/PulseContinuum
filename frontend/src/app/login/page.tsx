'use client';
import {useState,FormEvent} from 'react';
import {Activity,ArrowRight,ShieldCheck,Stethoscope} from 'lucide-react';
export default function Login() {
  const [username,setUsername] = useState(''), [password,setPassword] = useState('');
  const [error,setError] = useState(''),[busy,setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();setBusy(true);setError('');
    try {
      const response = await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Sign-in failed.');
      window.location.assign(result.redirect);
    } catch (e) {setError((e as Error).message);setBusy(false);}
  }
  return <main className="access-page"><section className="access-story"><span className="brandmark"><Activity size={26}/></span><p className="access-eyebrow">PULSECONTINUUM AI</p><h1>Care, without<br/>interruption.</h1><p>One recovery episode. Every handoff. Context intact.</p><div className="access-role"><Stethoscope size={21}/><div><strong>Care team</strong><p>Patient workbench, recovery overview and clinical audit.</p></div></div><div className="access-role"><ShieldCheck size={21}/><div><strong>Admin & engineering</strong><p>Orchestration and AWS evidence, available to authorized administrators.</p></div></div><small>Synthetic demonstration · Clinician oversight required</small></section><section className="access-form"><span className="access-eyebrow">YOUR WORKSPACE</span><h2>Welcome back</h2><p>Sign in with the private demo credentials shared with you.</p><form onSubmit={event => void submit(event)}><label htmlFor="username">Username</label><input id="username" autoComplete="username" value={username} onChange={event=>setUsername(event.target.value)} required maxLength={100}/><label htmlFor="password">Password</label><input id="password" type="password" autoComplete="current-password" value={password} onChange={event=>setPassword(event.target.value)} required maxLength={256}/>{error && <p role="alert" className="access-error">{error}</p>}<button className="button primary" disabled={busy}>{busy ? 'Signing in…' : 'Open workspace'}<ArrowRight size={16}/></button></form><p className="access-help">Administrator credentials unlock both profiles. Care credentials open the care workspace only.</p></section></main>;
}
