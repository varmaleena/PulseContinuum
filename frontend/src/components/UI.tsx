import {ReactNode} from 'react';
export function Heading({eyebrow, title, description, action}: {eyebrow: string; title: string; description: string; action?: ReactNode}) {return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>;}
export function Badge({children, tone = 'neutral'}: {children: ReactNode; tone?: string}) {return <span className={`badge ${tone}`}>{children}</span>;}
export function Empty({children}: {children: ReactNode}) {return <div className="empty">{children}</div>;}
export function Channel({name}: {name: string}) {const label: Record<string,string> = {WHATSAPP: 'WhatsApp', RCS: 'RCS', SMS: 'SMS failover', SES: 'Amazon SES', LOCAL_REVIEW: 'Clinical review'}; return <Badge tone={name.toLowerCase()}><span className="dot"/>{label[name] || name}</Badge>;}
