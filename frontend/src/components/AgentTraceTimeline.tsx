'use client';
import {Check, Clock, ShieldAlert} from 'lucide-react';
import {Trace, time} from '@/lib/api';
import {Empty} from './UI';
export default function AgentTraceTimeline({traces}: {traces: Trace[]}) {return <div className="timeline">{!traces.length && <Empty>Run discharge intake to start the execution timeline.</Empty>}{traces.map((trace,index) => <div className="trace" key={index}><div className={'trace-icon '+(trace.status === 'PASS' ? 'success' : 'warning')}>{trace.status === 'PASS' ? <Check size={14}/> : <ShieldAlert size={14}/>}</div><div><div className="trace-title">{trace.agent}<time>{time(trace.timestamp)}</time></div><p>{trace.action}</p><details><summary>Tool evidence · {trace.status}</summary><pre>{JSON.stringify(trace.details, null, 2)}</pre></details></div></div>)}<div className="timeline-end"><Clock size={13}/> Awaiting next event</div></div>;}
