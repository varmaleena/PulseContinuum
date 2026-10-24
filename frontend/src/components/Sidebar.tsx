'use client';
import Link from 'next/link';
import {usePathname} from 'next/navigation';
import {useState} from 'react';
import {Activity, LayoutDashboard, Smartphone, Network, Pill, Radio, HeartPulse, ArrowUpRight, ShieldCheck, Stethoscope} from 'lucide-react';
import {usePulse} from './Provider';
import {Profile} from '@/lib/profiles';
const careItems = [{path:'/overview', title:'Clinical overview', icon:LayoutDashboard}, {path:'/workbench', title:'Patient workbench', icon:Smartphone}, {path:'/pharmacy-rcs', title:'Care requests & audit', icon:Pill}];
const adminItems = [{path:'/agentcore', title:'Agent orchestration', icon:Network}, {path:'/telemetry', title:'AWS telemetry', icon:Radio}];
export default function Sidebar() {
  const path = usePathname();
  const {profile,canSwitch,demoProfiles} = usePulse();
  const [switching,setSwitching] = useState(false);
  const [error,setError] = useState('');
  const admin = profile === 'admin';
  const items = admin ? adminItems : careItems;
  async function switchProfile(next: Profile) {
    if (next === profile || switching) return;
    setSwitching(true); setError('');
    try {
      const response = await fetch('/api/profile', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({profile:next})});
      if (!response.ok) throw new Error((await response.json()).detail || 'Profile change failed.');
      window.location.assign(next === 'admin' ? '/agentcore' : '/overview');
    } catch (e) {setError((e as Error).message); setSwitching(false);}
  }
  return <aside className={'sidebar '+(admin ? 'admin-sidebar' : '')}>
    <Link href={admin ? '/agentcore' : '/overview'} className="brand"><span className="brandmark"><Activity size={24}/></span><span>Pulse<span className="brand-light">Continuum</span><small>CLINICAL INTELLIGENCE</small></span></Link>
    <div className="profile-picker" aria-label="Workspace profile">
      <span className="profile-picker-label">{demoProfiles ? 'DEMO PROFILES' : 'WORKSPACE PROFILE'}</span>
      <button className={!admin ? 'profile-choice selected' : 'profile-choice'} aria-pressed={!admin} disabled={switching} onClick={() => void switchProfile('care')}><Stethoscope size={16}/><span>Care team<small>Recovery & clinical review</small></span></button>
      {canSwitch && <button className={admin ? 'profile-choice selected' : 'profile-choice'} aria-pressed={admin} disabled={switching} onClick={() => void switchProfile('admin')}><ShieldCheck size={16}/><span>Admin & engineering<small>Systems & integrations</small></span></button>}
      {error && <p role="alert" className="profile-error">{error}</p>}
    </div>
    <div className="workspace"><span className="hospital">{admin ? <ShieldCheck size={18}/> : <HeartPulse size={18}/>}</span><div>{admin ? 'Technical operations' : 'Continuum Demo Network'}<small>{admin ? 'Restricted system visibility' : 'Post-discharge operations'}</small></div><span className="workspace-dot"/></div>
    <div className="nav-label">{admin ? 'ADMIN & ENGINEERING' : 'CARE OPERATIONS'}</div>
    <nav>{items.map((item,index) => <Link key={item.path} href={item.path} className={path === item.path ? 'nav-item active' : 'nav-item'}><item.icon size={18}/><span>{item.title}</span><small>{String(index+1).padStart(2,'0')}</small></Link>)}</nav>
    <div className="sidebar-bottom"><div className="protocol"><span className="dot"/>{admin ? 'Inspect system behavior' : 'Continuity of care'}<p>{admin ? 'Execution traces, delivery events and AWS request evidence.' : 'One patient. Every channel. Clinician oversight at every step.'}</p><Link href={admin ? '/telemetry' : '/workbench'}>{admin ? 'Inspect AWS requests' : 'Open care workbench'}<ArrowUpRight size={13}/></Link></div><div className="user"><span className="avatar">{admin ? 'AD' : 'CT'}</span><div>{admin ? 'Technical administrator' : 'Clinical operations'}<small>Synthetic demonstration</small></div></div></div>
  </aside>;
}
