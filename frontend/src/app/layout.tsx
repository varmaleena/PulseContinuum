import type {Metadata} from 'next';
import './clinical.css';
import Sidebar from '@/components/Sidebar';
import TopStatusBar from '@/components/TopStatusBar';
import {Provider} from '@/components/Provider';
import {headers} from 'next/headers';
export const dynamic = 'force-dynamic';
export const metadata: Metadata = {title: 'PulseContinuum AI | Clinical continuity', description: 'Autonomous post-discharge care orchestration across every channel.'};
export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {const context = headers(); return <html lang="en"><body><Provider profile={context.get('x-pulse-profile') === 'admin' ? 'admin' : 'care'} canSwitch={context.get('x-pulse-access') === 'admin'} demoProfiles={context.get('x-pulse-demo') === 'true'}><Sidebar/><div className="app-shell"><TopStatusBar/><main>{children}</main><footer>PulseContinuum AI <span>Clinical decision support · Synthetic demonstration · Clinician oversight required</span><span>POWERED BY AWS</span></footer></div></Provider></body></html>;}
