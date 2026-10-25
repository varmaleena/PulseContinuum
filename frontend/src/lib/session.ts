import {NextRequest} from 'next/server';

export const sessionCookie = 'pulse-session';
export async function equalSecret(a: string,b: string) {
  const encoder = new TextEncoder();
  const [left,right] = await Promise.all([a,b].map(value => crypto.subtle.digest('SHA-256',encoder.encode(value))));
  const x = new Uint8Array(left), y = new Uint8Array(right);
  let difference = 0;
  for (let i=0;i<x.length;i++) difference |= x[i]^y[i];
  return difference === 0;
}
const encode = (value: string) => btoa(value).replace(/=/g,'').replace(/\+/g,'-').replace(/\//g,'_');
const decode = (value: string) => atob(value.replace(/-/g,'+').replace(/_/g,'/'));
async function key() {
  if (!process.env.JUDGE_PASSWORD) throw new Error('Access is not configured');
  return crypto.subtle.importKey('raw',new TextEncoder().encode('pulsecontinuum-session-v1:'+process.env.JUDGE_PASSWORD),{name:'HMAC',hash:'SHA-256'},false,['sign','verify']);
}
export async function makeSession(access: 'care'|'admin') {
  const payload = encode(JSON.stringify({access,exp:Math.floor(Date.now()/1000)+8*60*60}));
  const signature = new Uint8Array(await crypto.subtle.sign('HMAC',await key(),new TextEncoder().encode(payload)));
  return payload+'.'+encode(String.fromCharCode(...signature));
}
export async function readSession(value?: string): Promise<'care'|'admin'|null> {
  if (!value) return null;
  try {
    const [payload,signature,extra] = value.split('.');
    if (extra || !payload || !signature) return null;
    const bytes = Uint8Array.from(decode(signature),character => character.charCodeAt(0));
    if (!await crypto.subtle.verify('HMAC',await key(),bytes,new TextEncoder().encode(payload))) return null;
    const session = JSON.parse(decode(payload));
    return ['care','admin'].includes(session.access) && typeof session.exp === 'number' && session.exp > Date.now()/1000 ? session.access : null;
  } catch {return null;}
}
export function sameOrigin(request: NextRequest) {
  const protocol = request.headers.get('x-forwarded-proto') === 'https' ? 'https:' : request.nextUrl.protocol;
  return request.headers.get('origin') === `${protocol}//${request.headers.get('host')}`;
}
