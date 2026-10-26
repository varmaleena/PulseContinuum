import {NextRequest} from 'next/server';
import {careApi} from '@/lib/profiles';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
export const maxDuration = 60;

async function proxy(request: NextRequest, {params}: {params: Promise<{path: string[]}>}) {
  const isCare = request.headers.get('x-pulse-profile') !== 'admin';
  if (isCare && !careApi(request.nextUrl.pathname)) return Response.json({detail:'Admin & engineering access is required.'}, {status:403});
  const resolved = await params;
  const upstream = new URL(`/api/${resolved.path.map(encodeURIComponent).join('/')}`, process.env.BACKEND_URL || 'http://127.0.0.1:8000');
  upstream.search = request.nextUrl.search;
  const headers = new Headers();
  const contentType = request.headers.get('content-type');
  if (contentType) headers.set('content-type', contentType);
  if (process.env.BACKEND_API_TOKEN) headers.set('authorization', `Bearer ${process.env.BACKEND_API_TOKEN}`);
  try {
    const body = request.method === 'POST' ? await request.arrayBuffer() : undefined;
    if (process.env.BACKEND_EVENT_TRANSPORT === 'poll' && body && body.byteLength > 3 * 1024 * 1024) {
      return Response.json({detail:'Hosted demo uploads must total less than 3 MB.'}, {status:413});
    }
    const response = await fetch(upstream, {method: request.method, headers, cache: 'no-store',
      body,
      signal: request.signal});
    const outgoing = new Headers();
    for (const key of ['content-type', 'content-disposition', 'cache-control']) {
      const value = response.headers.get(key);
      if (value) outgoing.set(key, value);
    }
    outgoing.set('cache-control', 'private, no-store');
    if (isCare && response.headers.get('content-type')?.includes('application/json')) {
      const sanitize = (value: unknown): unknown => {
        if (Array.isArray(value)) return value.map(sanitize);
        if (!value || typeof value !== 'object') return value;
        const record = value as Record<string, unknown>;
        return Object.fromEntries(Object.entries(record).filter(([key]) => !['account_id','pending_message_id','canonical_payload','message_id','request_id','hmac_sha256'].includes(key))
          .map(([key,item]) => [key, key === 'traces' ? [] : sanitize(item)]));
      };
      return Response.json(sanitize(await response.json()), {status:response.status, headers:outgoing});
    }
    return new Response(response.body, {status: response.status, headers: outgoing});
  } catch {
    return Response.json({detail: 'The clinical backend is unavailable.'}, {status: 502});
  }
}

export const GET = proxy;
export const POST = proxy;
