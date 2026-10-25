import {NextRequest, NextResponse} from 'next/server';
import {adminPage, careApi, Profile, profileCookie} from '@/lib/profiles';

import {equalSecret,readSession,sessionCookie} from '@/lib/session';

export async function middleware(request: NextRequest) {
  const path = request.nextUrl.pathname;
  if (path === '/login' || path === '/api/auth/login' || path === '/api/auth/logout') {
    const headers = new Headers(request.headers);
    headers.set('x-pulse-public-auth','true');
    const response = NextResponse.next({request:{headers}});
    response.headers.set('Cache-Control','private, no-store');
    return response;
  }
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
    const session = await readSession(request.cookies.get(sessionCookie)?.value);
    if (session) access = session;
    else if (await equalSecret(supplied, `${username}:${password}`)) access = 'admin';
    else if (process.env.CARE_USERNAME && process.env.CARE_PASSWORD && await equalSecret(supplied, `${process.env.CARE_USERNAME}:${process.env.CARE_PASSWORD}`)) access = 'care';
    else {
      if (path.startsWith('/api/') || request.headers.has('authorization')) return NextResponse.json({detail:'Please sign in to continue.'}, {status:401});
      else return NextResponse.redirect(new URL('/login',request.url));
    }
  }
  // A profile cookie selects a view; it never grants permission beyond authenticated access.
  // Loopback demo mode intentionally allows both synthetic profiles without credentials.
  const profile: Profile = access === 'admin' && request.cookies.get(profileCookie)?.value === 'admin' ? 'admin' : 'care';
  if (profile === 'care' && adminPage(path)) return NextResponse.redirect(new URL('/overview', request.url));
  if (profile === 'care' && path.startsWith('/api/') && path !== '/api/profile' && !careApi(path)) {
    return NextResponse.json({detail:'Admin & engineering access is required.'}, {status:403});
  }
  const headers = new Headers(request.headers);
  headers.set('x-pulse-public-auth','false');
  headers.set('x-pulse-profile', profile);
  headers.set('x-pulse-access', access);
  headers.set('x-pulse-demo', String(!configured));
  const response = NextResponse.next({request:{headers}});
  response.headers.set('Cache-Control', 'private, no-store');
  response.headers.append('Vary', 'Cookie, Authorization');
  return response;
}

export const config = {matcher:['/((?!_next/static|_next/image|favicon.ico).*)']};
