import {NextRequest, NextResponse} from 'next/server';
import {adminPage, careApi, Profile, profileCookie} from '@/lib/profiles';

// Optional local access gate; mandatory when REQUIRE_JUDGE_AUTH=true on a public host.
async function equalSecret(a: string, b: string) {
  const encode = new TextEncoder();
  const [left, right] = await Promise.all([a,b].map(value => crypto.subtle.digest('SHA-256', encode.encode(value))));
  const x = new Uint8Array(left), y = new Uint8Array(right);
  let difference = 0;
  for (let i=0; i<x.length; i++) difference |= x[i] ^ y[i];
  return difference === 0;
}

export async function middleware(request: NextRequest) {
  const username = process.env.JUDGE_USERNAME;
  const password = process.env.JUDGE_PASSWORD;
  const configured = Boolean(username && password);
  if (!configured && process.env.REQUIRE_JUDGE_AUTH === 'true') return new NextResponse('Judge access is not configured.', {status:503});
  let supplied = '';
  try {
    const header = request.headers.get('authorization') || '';
    if (header.startsWith('Basic ')) supplied = atob(header.slice(6));
  } catch { /* Malformed credentials are rejected below. */ }
  let access: Profile = 'admin';
  if (configured) {
    if (await equalSecret(supplied, `${username}:${password}`)) access = 'admin';
    else if (process.env.CARE_USERNAME && process.env.CARE_PASSWORD && await equalSecret(supplied, `${process.env.CARE_USERNAME}:${process.env.CARE_PASSWORD}`)) access = 'care';
    else return new NextResponse('Enter the private credentials supplied with the demonstration.', {
      status:401, headers:{'WWW-Authenticate':'Basic realm="PulseContinuum access", charset="UTF-8"', 'Cache-Control':'no-store'}
    });
  }
  // A profile cookie selects a view; it never grants permission beyond authenticated access.
  // Loopback demo mode intentionally allows both synthetic profiles without credentials.
  const profile: Profile = access === 'admin' && request.cookies.get(profileCookie)?.value === 'admin' ? 'admin' : 'care';
  const path = request.nextUrl.pathname;
  if (profile === 'care' && adminPage(path)) return NextResponse.redirect(new URL('/overview', request.url));
  if (profile === 'care' && path.startsWith('/api/') && path !== '/api/profile' && !careApi(path)) {
    return NextResponse.json({detail:'Admin & engineering access is required.'}, {status:403});
  }
  const headers = new Headers(request.headers);
  headers.set('x-pulse-profile', profile);
  headers.set('x-pulse-access', access);
  headers.set('x-pulse-demo', String(!configured));
  const response = NextResponse.next({request:{headers}});
  response.headers.set('Cache-Control', 'private, no-store');
  response.headers.append('Vary', 'Cookie, Authorization');
  return response;
}

export const config = {matcher:['/((?!_next/static|_next/image|favicon.ico).*)']};
