import {ClipboardList, FileText} from 'lucide-react';
import {Patient} from '@/lib/api';
import {Badge} from './UI';

export default function PatientContext({patient}: {patient: Patient}) {
  const profile = patient.profile;
  if (!profile) return null;
  return <details className="card patient-context">
    <summary><ClipboardList size={16}/><span>Clinical context</span><Badge>Synthetic</Badge></summary>
    <div className="patient-context-body">
      <div className="context-facility">{profile.facility}<small>{profile.care_unit} · {profile.sex}</small></div>
      <dl><div><dt>Discharged</dt><dd>{profile.discharged_at}</dd></div><div><dt>Caregiver</dt><dd>{profile.caregiver_relation}</dd></div><div><dt>Language</dt><dd>{profile.preferred_language}</dd></div><div><dt>Care team</dt><dd>{profile.clinician}</dd></div></dl>
      <h4>History & allergies</h4><ul>{[...profile.history, ...profile.allergies].map(item => <li key={item}>{item}</li>)}</ul>
      <h4>At discharge</h4><div className="context-vitals">{Object.entries(profile.discharge_vitals).map(([key,value]) => <div key={key}><small>{key}</small><strong>{value}</strong></div>)}</div>
      <h4>Care-team handoff</h4><p>{profile.handoff_note}</p><h4>Follow-up</h4><p>{profile.follow_up}</p>
      <a className="text-link" href={`/api/fixtures/${patient.episode_id}/discharge.pdf`} target="_blank" rel="noreferrer"><FileText size={14}/> View synthetic discharge summary</a>
    </div>
  </details>;
}
