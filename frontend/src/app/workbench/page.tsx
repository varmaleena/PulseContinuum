'use client';

import {useEffect, useState} from 'react';

import {ArrowRight, Check, FileText, ImagePlus, Mic, RotateCcw, ShieldCheck, Upload} from 'lucide-react';

import {api, evidenceSummary, Patient, workflow} from '@/lib/api';

import {usePulse} from '@/components/Provider';

import {Badge, Empty, Heading} from '@/components/UI';

import PhoneFrameWhatsApp from '@/components/PhoneFrameWhatsApp';
import PatientContext from '@/components/PatientContext';
import ScenarioLauncher from '@/components/ScenarioLauncher';

import PhoneFrameRCSAndSMS from '@/components/PhoneFrameRCSAndSMS';



export default function Workbench() {

  const {profile, patient, selected, run, busy, health} = usePulse();

  const [step, setStep] = useState(1);

  const [tab, setTab] = useState<'WHATSAPP' | 'RCS'>('WHATSAPP');

  const [pdf, setPdf] = useState<File>();

  const [image, setImage] = useState<File>();

  const [audio, setAudio] = useState<File>();

  const [transcript, setTranscript] = useState('I took the blue tablet this morning. Now I have a 101.2F fever and dizziness. Which strip do I take next?');

  useEffect(() => { if (patient?.profile?.patient_report) setTranscript(patient.profile.patient_report); }, [selected, patient?.profile?.patient_report]);
  useEffect(() => { setStep(1); setTab('WHATSAPP'); setPdf(undefined); setImage(undefined); setAudio(undefined); }, [selected]);
  const orderId = patient?.order?.order_id;
  const replayLoadedAt = patient?.demo_replay?.loaded_at;
  useEffect(() => {if (orderId) setStep(4);}, [orderId]);
  useEffect(() => {if (replayLoadedAt) setStep(3);}, [replayLoadedAt]);
  const recordedReport = patient?.demo_replay ? [...patient.messages].reverse().find(message=>message.direction==='inbound' && message.channel==='WHATSAPP' && message.media_type!=='audio')?.text : undefined;
  useEffect(() => {if (recordedReport) setTranscript(recordedReport);}, [recordedReport,replayLoadedAt]);
  const submit = (action: string) => run(async () => {

    const form = new FormData();

    form.set('episode_id', selected);

    if (action === 'ingest-discharge' && pdf) form.set('file', pdf);

    if (action === 'whatsapp-multimodal') {

      form.set('transcript', transcript);

      if (image) form.set('image', image);

      if (audio) form.set('audio', audio);

    }

    await api<Patient>(`/workflow/${action}`, {method: 'POST', body: form});

    setStep(action === 'ingest-discharge' ? 2 : 3);

  });

  if (!patient) return <Empty>Connecting to the clinical backend…</Empty>;

  const steps = [

    {id: 1, title: 'Discharge plan', detail: 'Connect the care context', done: patient.ingested},

    {id: 2, title: 'Patient check-in', detail: 'Review symptoms & evidence', done: !!patient.analysis},

    {id: 3, title: 'Request review', detail: 'Open a clinical handoff', done: !!patient.order},
    {id: 4, title: 'Review & follow-up', detail: 'Record the next steps', done: !!patient.follow_up_record},

  ];

  return <>

    <Heading eyebrow="PATIENT CARE WORKBENCH" title="Care, without interruption." description="Follow one recovery episode from discharge to a coordinated care response." action={<button className="button ghost" disabled={busy || (health?.mode === 'live' && !health?.synthetic_reset)} title={health?.mode === 'live' && !health?.synthetic_reset ? 'Reset is available in offline demo mode only' : 'Reset this synthetic episode'} onClick={() => void run(async () => {await workflow('reset', selected); setStep(1); setTab('WHATSAPP');})}><RotateCcw size={15}/> Reset demo</button>}/>

    {health?.mode === 'live' && <div className="aws-connection-note"><ShieldCheck size={17}/><span><strong>{profile === 'admin' ? 'AWS storage & Bedrock connected.' : 'Synthetic care demonstration.'}</strong> Patient records are fictional. Phone conversations are previews; disconnected channels show “Not sent”.</span></div>}

    <ScenarioLauncher/>
    {patient.demo_replay && <div className="recorded-evidence-note"><strong>Recorded AWS analysis · {new Date(patient.demo_replay.recorded_at).toLocaleDateString()}</strong><p>{patient.demo_replay.description} The review, acknowledgment and follow-up actions you enter below are new synthetic records.</p></div>}
    <nav className="workflow-steps" aria-label="Care workflow steps">{steps.map(s => <button key={s.id} aria-current={step === s.id ? 'step' : undefined} className={`workflow-step ${step === s.id ? 'current' : ''} ${s.done ? 'done' : ''}`} onClick={() => setStep(s.id)}><span className="workflow-step-number">{s.done ? <Check size={16}/> : `0${s.id}`}</span><span><strong>{s.title}</strong><small>{s.detail}</small></span><ArrowRight size={16}/></button>)}</nav>

    <div className="workbench-grid">

      <div className="controls">

        <div className="episode-summary"><div className="patient-cell"><span className="avatar">{patient.name.split(' ').map(s => s[0]).join('')}</span><div><strong>{patient.name}</strong><small>{patient.age} years · Recovery day {patient.day}</small></div></div><p>{patient.condition}</p><div><code>{patient.episode_id}</code><Badge tone={patient.risk_score >= 70 ? 'danger' : 'whatsapp'}>{!patient.analysis ? 'Awaiting check-in' : patient.analysis.clinical_red_flags.length || patient.risk_score>=70 ? 'Assessment needed' : 'Evidence review'}</Badge></div></div>

        <PatientContext patient={patient}/>
        {step === 1 && <section className="card trigger"><div className="step-title"><span className="step-number ses"><FileText size={19}/></span><div><h3>Start with the care plan</h3><small>Written discharge plan · PDF intake</small></div></div><p>Connect the written medication schedule and follow-up context. The app does not create or replace a prescription.</p><label className="upload-zone"><Upload size={24}/><strong>{pdf?.name || 'Choose a discharge summary'}</strong><small>Upload a PDF, or use our sample below</small><input aria-label="Discharge PDF" type="file" accept="application/pdf" onChange={e => setPdf(e.target.files?.[0])}/></label><button className="button primary full" disabled={busy || !!patient.analysis} onClick={() => void submit('ingest-discharge')}>{busy ? 'Connecting care plan…' : pdf ? 'Use this discharge plan' : 'Start with sample patient'}<ArrowRight size={15}/></button>{patient.ingested && <div className="extracted"><span><ShieldCheck size={15}/> Physician plan connected</span>{patient.medications.map(m => <div key={m.name}><strong>{m.name} {m.strength}</strong><small>{m.schedule}</small></div>)}</div>}</section>}

        {step === 2 && <section className="card trigger"><div className="step-title"><span className="step-number whatsapp"><ImagePlus size={19}/></span><div><h3>Listen to the patient</h3><small>Patient report · conversation preview</small></div></div><p>Review a medication label or wound photo alongside the patient’s report.</p><div className="upload-pair"><label className="mini-upload"><ImagePlus size={20}/><span>{image?.name || 'Add a photo'}</span><input type="file" accept="image/jpeg,image/png,image/webp" aria-label="Medication or wound photo" onChange={e => setImage(e.target.files?.[0])}/></label><label className="mini-upload"><Mic size={20}/><span>{audio?.name || 'Add voice note'}</span><input type="file" accept="audio/*" aria-label="Patient voice note" onChange={e => setAudio(e.target.files?.[0])}/></label></div><label className="field-label" htmlFor="transcript">What the patient is saying</label><textarea id="transcript" value={transcript} onChange={e => setTranscript(e.target.value)} rows={5}/>{patient.demo_replay && <p className="helper">Recorded evidence is already loaded. Continue with Request review to avoid another model call; the button below runs a fresh live analysis.</p>}<small className="helper">English, Hindi, or Telugu transcript. Voice notes are stored and playable; transcription is manual.</small><button className="button primary full" disabled={busy || !patient.ingested || !transcript.trim()} onClick={() => void submit('whatsapp-multimodal')}>{busy ? 'Reviewing patient evidence…' : patient.demo_replay ? 'Run a fresh AWS analysis' : 'Analyze & identify the next review step'}<ArrowRight size={15}/></button>{!patient.ingested && <p className="helper">Connect the discharge plan in step 1 first.</p>}</section>}

        {step === 3 && <section className="card trigger"><div className="step-title"><span className="step-number sms"><ShieldCheck size={19}/></span><div><h3>Request the right review</h3><small>A clinician decides what happens next</small></div></div><p>{patient.analysis?.next_action || 'Analyze the patient report first.'}</p><div className="care-next-action"><strong>No medication change has been made.</strong><p>A review request asks the clinical team to assess the report. It is not an order for tablets or a completed consultation.</p></div><button className="button primary full" disabled={busy || !patient.analysis || !!patient.order} onClick={()=>void run(async()=>{await workflow('rcs-action',selected,{option_id:'triage'});setStep(4);})}>Request clinician review<ArrowRight size={15}/></button><details className="optional-fallback"><summary>Optional demo branch: loss of mobile data</summary><p>Preview how the patient and caregiver could retain context through SMS. This is a communication fallback, not treatment.</p><button className="blackout-toggle" role="switch" aria-checked={patient.blackout} disabled={busy || !patient.analysis || patient.blackout || !!patient.order} onClick={() => void run(() => workflow('simulate-deadzone-failover', selected))}><span>{patient.blackout ? 'Fallback branch recorded' : 'Simulate loss of mobile data'}</span><span className={`switch ${patient.blackout ? 'on' : ''}`}><i/></span></button><small className="helper">{health?.mode==='demo' || health?.channels?.WHATSAPP ? 'A 15-second watchdog also runs while an enabled alert awaits its delivery receipt.' : 'Hosted phone senders are disconnected. No automatic live delivery watchdog is armed.'}</small></details></section>}
        {step === 4 && <section className="card trigger"><div className="step-title"><span className="step-number whatsapp"><Check size={19}/></span><div><h3>Close the handoff</h3><small>Review → acknowledgment → follow-up</small></div></div><p>{patient.order ? 'The request is recorded. Now show what the clinician decides, what the patient understands and what the follow-up records.' : 'Create a review request in step 3 before recording the clinical handoff.'}</p><div className="care-completion-list"><span>{patient.clinical_review?'✓':'○'} Synthetic clinician decision</span><span>{patient.patient_acknowledgement?'✓':'○'} Patient/caregiver teach-back</span><span>{patient.follow_up_record?'✓':'○'} Follow-up contact record</span></div><a className="button primary full" href="/pharmacy-rcs">Open review & follow-up<ArrowRight size={15}/></a><small className="helper">The email/PDF is a handoff record. Generating it does not mean the patient has been treated or recovered.</small></section>}

        <div className="workbench-reassurance"><ShieldCheck size={17}/><p>Clinical oversight at every step.<br/><span>Unverified medications always go to review.</span></p></div>

      </div>

      <section className="demo-stage"><div className="stage-top"><div><h2>The care conversation</h2></div><span className="live-caption"><span className="dot"/> Conversation preview</span></div><div className="device-grid"><div className="device-column"><div className="device-label">Patient <span>{patient.name.split(' ')[0]}</span></div><div className="tabs"><button className={tab === 'WHATSAPP' ? 'selected whatsapp' : ''} onClick={() => setTab('WHATSAPP')}>WhatsApp</button><button className={tab === 'RCS' ? 'selected rcs' : ''} onClick={() => setTab('RCS')}>Care options {patient.rcs_cards.length > 0 && <span className="dot"/>}</button></div>{tab === 'WHATSAPP' ? <PhoneFrameWhatsApp patient={patient}/> : <PhoneFrameRCSAndSMS patient={patient} mode="RCS"/>}</div><div className="device-column"><div className="device-label">Caregiver <span>Emergency contact</span></div><div className="caregiver-status"><span className={`dot ${patient.blackout ? 'amber' : ''}`}/>{health?.mode === 'live' && !health.channels?.SMS ? 'SMS sender not connected' : patient.blackout ? 'SMS continuity active' : 'SMS ready when needed'}</div><PhoneFrameRCSAndSMS patient={patient} mode="SMS"/></div></div>{patient.analysis && <div className="analysis-strip"><ShieldCheck size={20}/><div><strong>{patient.analysis.clinical_red_flags.length || patient.risk_score>=70 ? 'Symptoms require clinician assessment' : patient.analysis.guardrail_verification.dosage_verified ? 'Label matched; clinical suitability is not established' : 'Medication identity requires reconciliation'}</strong><p>{evidenceSummary(patient.analysis.summary)}</p><small>No medication change is authorized by the app.</small></div><Badge tone="violet">Safety gate</Badge></div>}<div className="stage-bottom"><span className="dot"/>{patient.stage}<span>Demo · synthetic patient</span></div></section>

    </div>

  </>;

}
