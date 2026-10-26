'use client';
import {useEffect,useState} from 'react';
import {useRouter} from 'next/navigation';
import {ArrowRight,FlaskConical} from 'lucide-react';
import {api,workflow} from '@/lib/api';
import {usePulse} from './Provider';
interface Scenario {episode_id: string; title: string; focus: string; available: boolean}
export default function ScenarioLauncher() {
  const {select,run,busy} = usePulse();
  const [scenarios,setScenarios] = useState<Scenario[]>([]);
  const router = useRouter();
  useEffect(()=>{void api<Scenario[]>('/scenarios').then(setScenarios).catch(()=>setScenarios([]));},[]);
  if (!scenarios.some(scenario=>scenario.available)) return null;
  return <section className="scenario-launcher" aria-label="Recorded AWS test scenarios"><div className="scenario-heading"><FlaskConical size={18}/><div><strong>Start with a tested patient story</strong><p>Recorded AWS inference, new interactive handoff. No login or fresh model call is needed for these examples. Engineering verification is not clinical validation.</p></div></div><div className="scenario-grid">{scenarios.map((scenario,index)=><article key={scenario.episode_id}><small>SCENARIO 0{index+1}</small><h3>{scenario.title}</h3><p>{scenario.focus}</p><button disabled={busy || !scenario.available} onClick={()=>void run(async()=>{await workflow('replay-scenario',scenario.episode_id);select(scenario.episode_id);router.push('/workbench');})}>{scenario.available?'Explore recorded case':'Verification pending'}<ArrowRight size={14}/></button></article>)}</div></section>;
}
