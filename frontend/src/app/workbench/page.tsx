'use client';

import {useEffect, useState} from 'react';

import {ArrowRight, Check, FileText, ImagePlus, Mic, RotateCcw, ShieldCheck, Upload, Zap} from 'lucide-react';

import {api, Patient, workflow} from '@/lib/api';

import {usePulse} from '@/components/Provider';

import {Badge, Empty, Heading} from '@/components/UI';

import PhoneFrameWhatsApp from '@/components/PhoneFrameWhatsApp';
import PatientContext from '@/components/PatientContext';

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

    {id: 3, title: 'Care continuity', detail: 'Reach the caregiver', done: !!patient.order},

  ];

  return <>

    <Heading eyebrow="PATIENT CARE WORKBENCH" title="Care, without interruption." description="Follow one recovery episode from discharge to a coordinated care response." action={<button className="button ghost" disabled={busy || health?.mode === 'live'} title={health?.mode === 'live' ? 'Reset is available in offline demo mode only' : 'Reset this synthetic episode'} onClick={() => void run(async () => {await workflow('reset', selected); setStep(1); setTab('WHATSAPP');})}><RotateCcw size={15}/> Reset demo</button>}/>

    {health?.mode === 'live' && <div className="aws-connection-note"><ShieldCheck size={17}/><span><strong>{profile === 'admin' ? 'AWS storage & Bedrock connected.' : 'Synthetic care demonstration.'}</strong> Patient records are fictional. Phone conversations are previews; disconnected channels show “Not sent”.</span></div>}

    <nav className="workflow-steps" aria-label="Care workflow steps">{steps.map(s => <button key={s.id} aria-current={step === s.id ? 'step' : undefined} className={`workflow-step ${step === s.id ? 'current' : ''} ${s.done ? 'done' : ''}`} onClick={() => setStep(s.id)}><span className="workflow-step-number">{s.done ? <Check size={16}/> : `0${s.id}`}</span><span><strong>{s.title}</strong><small>{s.detail}</small></span><ArrowRight size={16}/></button>)}</nav>

    <div className="workbench-grid">

      <div className="controls">

        <div className="episode-summary"><div className="patient-cell"><span className="avatar">{patient.name.split(' ').map(s => s[0]).join('')}</span><div><strong>{patient.name}</strong><small>{patient.age} years · Recovery day {patient.day}</small></div></div><p>{patient.condition}</p><div><code>{patient.episode_id}</code><Badge tone={patient.risk_score >= 70 ? 'danger' : 'whatsapp'}>Risk {patient.risk_score}/100</Badge></div></div>

        <PatientContext patient={patient}/>
        {step === 1 && <section className="card trigger"><div className="step-title"><span className="step-number ses"><FileText size={19}/></span><div><h3>Start with the care plan</h3><small>Discharge intake · Amazon SES</small></div></div><p>Bring the physician’s medication schedule into the episode and send a patient check-in.</p><label className="upload-zone"><Upload size={24}/><strong>{pdf?.name || 'Choose a discharge summary'}</strong><small>Upload a PDF, or use our sample below</small><input aria-label="Discharge PDF" type="file" accept="application/pdf" onChange={e => setPdf(e.target.files?.[0])}/></label><button className="button primary full" disabled={busy} onClick={() => void submit('ingest-discharge')}>{busy ? 'Connecting care plan…' : pdf ? 'Use this discharge plan' : 'Start with sample patient'}<ArrowRight size={15}/></button>{patient.ingested && <div className="extracted"><span><ShieldCheck size={15}/> Physician plan connected</span>{patient.medications.map(m => <div key={m.name}><strong>{m.name} {m.strength}</strong><small>{m.schedule}</small></div>)}</div>}</section>}

        {step === 2 && <section className="card trigger"><div className="step-title"><span className="step-number whatsapp"><ImagePlus size={19}/></span><div><h3>Listen to the patient</h3><small>Symptoms & evidence · WhatsApp</small></div></div><p>Review a medication label or wound photo alongside the patient’s report.</p><div className="upload-pair"><label className="mini-upload"><ImagePlus size={20}/><span>{image?.name || 'Add a photo'}</span><input type="file" accept="image/jpeg,image/png,image/webp" aria-label="Medication or wound photo" onChange={e => setImage(e.target.files?.[0])}/></label><label className="mini-upload"><Mic size={20}/><span>{audio?.name || 'Add voice note'}</span><input type="file" accept="audio/*" aria-label="Patient voice note" onChange={e => setAudio(e.target.files?.[0])}/></label></div><label className="field-label" htmlFor="transcript">What the patient is saying</label><textarea id="transcript" value={transcript} onChange={e => setTranscript(e.target.value)} rows={5}/><small className="helper">English, Hindi, or Telugu transcript. Voice notes are stored and playable; transcription is manual.</small><button className="button primary full" disabled={busy || !patient.ingested || !transcript.trim()} onClick={() => void submit('whatsapp-multimodal')}>{busy ? 'Reviewing patient evidence…' : 'Review & prepare care options'}<ArrowRight size={15}/></button>{!patient.ingested && <p className="helper">Connect the discharge plan in step 1 first.</p>}</section>}

        {step === 3 && <section className="card trigger chaos"><div className="step-title"><span className="step-number sms"><Zap size={19}/></span><div><h3>Keep care connected</h3><small>Caregiver fallback · SMS</small></div></div><p>When mobile data drops, the same care context reaches both the patient and their caregiver by SMS.</p><div className="continuity-path"><span>WhatsApp / RCS</span><ArrowRight size={15}/><span>Caregiver SMS</span></div><button className="blackout-toggle" role="switch" aria-checked={patient.blackout} disabled={busy || !patient.analysis || patient.blackout || !!patient.order} onClick={() => void run(() => workflow('simulate-deadzone-failover', selected))}><span>{patient.blackout ? 'SMS fallback is active' : 'Simulate loss of mobile data'}</span><span className={`switch ${patient.blackout ? 'on' : ''}`}><i/></span></button><small className="helper">Automatic fallback also runs after 15 seconds without a delivery receipt.</small>{patient.order && <div className="extracted"><span><ShieldCheck size={15}/> Care request reserved</span><p>The clinical audit is ready. The treating clinician approves the next action.</p><a className="text-link" href="/pharmacy-rcs">View care request & audit <ArrowRight size={14}/></a></div>}</section>}

        <div className="workbench-reassurance"><ShieldCheck size={17}/><p>Clinical oversight at every step.<br/><span>Unverified medications always go to review.</span></p></div>

      </div>

      <section className="demo-stage"><div className="stage-top"><div><h2>The care conversation</h2></div><span className="live-caption"><span className="dot"/> Live mirror</span></div><div className="device-grid"><div className="device-column"><div className="device-label">Patient <span>{patient.name.split(' ')[0]}</span></div><div className="tabs"><button className={tab === 'WHATSAPP' ? 'selected whatsapp' : ''} onClick={() => setTab('WHATSAPP')}>WhatsApp</button><button className={tab === 'RCS' ? 'selected rcs' : ''} onClick={() => setTab('RCS')}>Care options {patient.rcs_cards.length > 0 && <span className="dot"/>}</button></div>{tab === 'WHATSAPP' ? <PhoneFrameWhatsApp patient={patient}/> : <PhoneFrameRCSAndSMS patient={patient} mode="RCS"/>}</div><div className="device-column"><div className="device-label">Caregiver <span>Emergency contact</span></div><div className="caregiver-status"><span className={`dot ${patient.blackout ? 'amber' : ''}`}/>{health?.mode === 'live' && !health.channels?.SMS ? 'SMS sender not connected' : patient.blackout ? 'SMS continuity active' : 'SMS ready when needed'}</div><PhoneFrameRCSAndSMS patient={patient} mode="SMS"/></div></div>{patient.analysis && <div className="analysis-strip"><ShieldCheck size={20}/><div><strong>{patient.analysis.guardrail_verification.dosage_verified ? 'Medication evidence matched' : 'Clinical review required'}</strong><p>{patient.analysis.summary}</p></div><Badge tone="violet">Safety gate</Badge></div>}<div className="stage-bottom"><span className="dot"/>{patient.stage}<span>Demo · synthetic patient</span></div></section>

    </div>

  </>;

}

