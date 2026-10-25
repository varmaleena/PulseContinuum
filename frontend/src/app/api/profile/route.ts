import {NextRequest, NextResponse} from 'next/server';
import {profileCookie} from '@/lib/profiles';

export const dynamic = 'force-dynamic';
export async function POST(request: NextRequest) {
  // Next's internal URL can use localhost even when the browser uses 127.0.0.1.
  // Use the actual request host; proxies must preserve Host and set forwarded protocol.
  const protocol = request.headers.get('x-forwarded-proto') === 'https' ? 'https:' : request.nextUrl.protocol;
  const expectedOrigin = `${protocol}//${request.headers.get('host')}`;
  if (request.headers.get('origin') !== expectedOrigin) return NextResponse.json({detail:'Same-origin profile changes only.'}, {status:403});
  const body = await request.json().catch(() => null);
  if (!body || !['care','admin'].includes(body.profile)) return NextResponse.json({detail:'Choose a valid profile.'}, {status:400});
  if (body.profile === 'admin' && request.headers.get('x-pulse-access') !== 'admin') return NextResponse.json({detail:'Your credentials allow the care profile only.'}, {status:403});
  const response = NextResponse.json({profile:body.profile});
  response.cookies.set(profileCookie, body.profile, {httpOnly:true, sameSite:'lax', secure:protocol === 'https:', path:'/', maxAge:60*60*8});
  response.headers.set('Cache-Control','no-store');
  return response;
}
