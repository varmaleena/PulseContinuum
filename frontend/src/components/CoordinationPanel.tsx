'use client';
import {useState} from 'react';
import {Clock3,GitBranch,RotateCcw,ShieldCheck} from 'lucide-react';
import {api,Patient} from '@/lib/api';
import {usePulse} from './Provider';
import {Badge} from './UI';

export interface Coordination {
  run_id: string; mode: string; logical_now: number; clock_offset_seconds: number;
  concern_open: boolean; scheduler_last_checked_at: string | null;
  tasks: Record<string,{id: string; owner: string; status: string; due_at: number; reason: string; delivery: string; correlation_id: string; attempts: number}>;
  outbox: {id: string; task_id: string; audience: string; text: string; status: string}[];
  decisions: {at: number; action: string; reason: string; task_id: string}[];
  last_caregiver_reply?: {text: string}; last_event_result?: {event_id: string; status: string};
}
type Command = {episode_id: string; run_id: string; event_id: string; kind: string; task_id?: string; correlation_id?: string; text?: string; advance_seconds?: number};
export function CoordinationPanel({patient}:{patient: Patient}) {
  const {run,busy,pollEvents} = usePulse();
  const [previous,setPrevious] = useState<Command>();
  const c = patient.coordination;
  if (!c) return <section className="card coordination-panel"><h2><GitBranch size={19}/> Accountable handoff coordination</h2><p>Request clinician review to start owned tasks, deadline monitoring and correlated contact tracking.</p></section>;
  const command = (kind: string, extra: Partial<Command> = {}) => {
    const body = {episode_id:patient.episode_id,run_id:c.run_id,event_id:crypto.randomUUID(),kind,...extra};
    setPrevious(body);
    void run(()=>api<Patient>('/workflow/coordination-event',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}));
  };
  const contact = Object.values(c.tasks).find(t=>['patient_contact','caregiver_contact'].includes(t.id) && t.status==='OPEN');
  const caregiver = c.tasks.caregiver_contact;
  const correlate = (t: NonNullable<typeof contact>) => ({task_id:t.id,correlation_id:t.correlation_id});
  const stamp = (s: number) => new Date(s*1000).toLocaleTimeString();
  return <section className="card coordination-panel" aria-label="Accountable coordination">
    <div className="section-head"><div><h2><GitBranch size={19}/> The handoff keeps moving</h2><p>One episode, explicit owners, visible unresolved work.</p></div><Badge tone={c.concern_open?'danger':'violet'}>{c.concern_open?'Concern remains open':'Bounded policy controller'}</Badge></div>
    <div className="coordination-boundary"><ShieldCheck size={16}/><p>Synthetic operational timers demonstrate coordination, not medical response deadlines. Contact intents and injected receipts are previews; no email or phone message is sent. Urgent real symptoms must never wait for this demo timer.</p></div>
    <div className="coordination-clock"><span><Clock3 size={16}/> Demo clock <strong>{stamp(c.logical_now)}</strong> · advanced {c.clock_offset_seconds/60} min</span><small>{pollEvents?'Hosted AWS checks every 5 minutes, even with the browser closed.':'Local demo: advance the clock to evaluate deadlines; the hosted version also has an AWS worker.'}{c.scheduler_last_checked_at && ` Last worker check: ${new Date(c.scheduler_last_checked_at).toLocaleTimeString()}`}</small></div>
    <div className="coordination-actions"><button className="button" disabled={busy} onClick={()=>command('ADVANCE_CLOCK',{advance_seconds:180})}>Advance 3 demo minutes</button><button className="button" disabled={busy} onClick={()=>command('ADVANCE_CLOCK',{advance_seconds:360})}>Advance 6 demo minutes</button>
      {contact && <button className="button" disabled={busy} onClick={()=>command('DELIVERY_FAILED',correlate(contact))}>Inject {contact.id==='patient_contact'?'patient':'caregiver'} delivery failure</button>}
      {caregiver && <button className="button" disabled={busy} onClick={()=>command('CONCERN_REPORTED',{...correlate(caregiver),text:'SYNTHETIC caregiver reply: the concern is still present. Please keep the treating-team assessment request open.'})}>Inject caregiver concern</button>}
      {previous?.run_id===c.run_id && <button className="text-link" disabled={busy} onClick={()=>void run(()=>api('/workflow/coordination-event',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(previous)}))}><RotateCcw size={14}/> Replay same event</button>}
    </div>
    <p className="coordination-hint">Judge walkthrough: inject patient delivery failure → inject caregiver concern → replay the same event → advance 6 minutes. Watch the contact path, duplicate protection and review owner change.</p>
    {c.last_event_result && <p role="status" className="coordination-result">Last event: <strong>{c.last_event_result.status.replaceAll('_',' ')}</strong></p>}
    <div className="coordination-tasks">{Object.values(c.tasks).map(t=><article key={t.id}><div><strong>{t.id.replaceAll('_',' ')}</strong><Badge tone={['ESCALATED','MANUAL_INTERVENTION'].includes(t.status)?'danger':t.status==='COMPLETED'?'whatsapp':'neutral'}>{t.status.replaceAll('_',' ')}</Badge></div><p>{t.owner}</p><small>{t.reason}</small><footer>Due {stamp(t.due_at)} · retries {t.attempts}/2{t.delivery!=='NOT_APPLICABLE' && ` · ${t.delivery.replaceAll('_',' ')}`}</footer></article>)}</div>
    {c.last_caregiver_reply && <blockquote className="coordination-reply">{c.last_caregiver_reply.text}<small>Correlated to this episode. Human interpretation required; no automatic clinical clearance.</small></blockquote>}
    <details className="coordination-log"><summary>Why the controller acted · {c.decisions.length} decisions</summary><ol>{c.decisions.slice().reverse().map((d,i)=><li key={i}><strong>{d.action.replaceAll('_',' ')}</strong><time>{stamp(d.at)}</time><p>{d.reason}</p></li>)}</ol></details>
  </section>;
}
