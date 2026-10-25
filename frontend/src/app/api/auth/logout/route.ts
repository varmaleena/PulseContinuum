import {NextRequest,NextResponse} from 'next/server';
import {sameOrigin,sessionCookie} from '@/lib/session';
export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({detail:'Same-origin sign-out required.'},{status:403});
  const response = NextResponse.json({redirect:'/login'});
  response.cookies.set(sessionCookie,'',{path:'/',maxAge:0,httpOnly:true,sameSite:'lax'});
  response.cookies.set('pulse-profile','',{path:'/',maxAge:0,httpOnly:true,sameSite:'lax'});
  response.headers.set('Cache-Control','no-store');
  return response;
}
