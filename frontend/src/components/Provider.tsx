'use client';
import {createContext, useCallback, useContext, useEffect, useState} from 'react';
import {api, Health, Patient, TelemetryEvent} from '@/lib/api';
import {Profile} from '@/lib/profiles';

interface Context {pollEvents: boolean; profile: Profile; canSwitch: boolean; demoProfiles: boolean; patients: Patient[]; patient: Patient | undefined; selected: string; select: (id: string) => void; refresh: () => Promise<void>; events: TelemetryEvent[]; health?: Health; connected: boolean; error: string; clearError: () => void; busy: boolean; run: (task: () => Promise<unknown>) => Promise<void>}
const PulseContext = createContext<Context | null>(null);
export function Provider({children,profile,canSwitch,demoProfiles,pollEvents}: {children: React.ReactNode; profile: Profile; canSwitch: boolean; demoProfiles: boolean; pollEvents: boolean}) {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selected, setSelected] = useState('EP-2026-409');
  useEffect(() => {try {const episode = sessionStorage.getItem('pulse-episode'); if (episode) setSelected(episode);} catch { /* Browser storage may be disabled. */ }}, []);
  const select = useCallback((episode: string) => {setSelected(episode); try {sessionStorage.setItem('pulse-episode', episode);} catch { /* Keep the in-memory selection. */ }}, []);
  const [events, setEvents] = useState<TelemetryEvent[]>([]);
  const [health, setHealth] = useState<Health>();
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {const result = await api<Patient[]>('/patients'); setPatients(result);}, []);
  useEffect(() => {
    let active = true;
    const load = async () => {try {const [p,h,e] = await Promise.all([api<Patient[]>('/patients'), api<Health>('/health'), profile === 'admin' ? api<TelemetryEvent[]>('/telemetry') : Promise.resolve([])]); if (active) {setPatients(p); setHealth(h); setEvents(e); setConnected(true);}} catch(e) {if (active) {setConnected(false); setError((e as Error).message);}}};
    void load();
    if (profile === 'care' || pollEvents) {
      const poll = setInterval(() => {void load();}, 5000);
      return () => {active = false; clearInterval(poll);};
    }
    const stream = new EventSource('/api/events');
    stream.onopen = () => { if (active) setConnected(true); };
    stream.onmessage = event => {
      const item = JSON.parse(event.data) as TelemetryEvent;
      if (item.category === 'HEARTBEAT') return;
      if (item.category === 'STATE_UPDATE') {void refresh().catch(e => setError(e.message)); return;}
      setEvents(current => current.some(e => e.id === item.id) ? current : [...current, item].slice(-1000));
    };
    stream.onerror = () => { if (active) setConnected(false); };
    return () => {active = false; stream?.close();};
  }, [refresh, profile, pollEvents]);
  const run = async (task: () => Promise<unknown>) => {setBusy(true); setError(''); try {await task(); await refresh();} catch(e) {setError((e as Error).message);} finally {setBusy(false);}};
  return <PulseContext.Provider value={{pollEvents, profile, canSwitch, demoProfiles, patients, patient: patients.find(p => p.episode_id === selected), selected, select, refresh, events, health, connected, error, clearError: () => setError(''), busy, run}}>{children}</PulseContext.Provider>;
}
export function usePulse() {const context = useContext(PulseContext); if (!context) throw new Error('Provider required'); return context;}
