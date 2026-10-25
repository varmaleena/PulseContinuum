import {NextRequest,NextResponse} from 'next/server';
import {equalSecret,makeSession,sameOrigin,sessionCookie} from '@/lib/session';
export const dynamic = 'force-dynamic';
export async function POST(request: NextRequest) {
  if (!sameOrigin(request)) return NextResponse.json({detail:'Same-origin sign-in required.'},{status:403});
  if (!process.env.JUDGE_USERNAME || !process.env.JUDGE_PASSWORD) return NextResponse.json({detail:'Sign-in is not configured.'},{status:503});
  const data = await request.json().catch(() => null);
  if (!data || typeof data.username !== 'string' || typeof data.password !== 'string' || data.username.length>100 || data.password.length>256) return NextResponse.json({detail:'Enter your username and password.'},{status:400});
  const supplied = data.username+':'+data.password;
  let access: 'care'|'admin';
  if (await equalSecret(supplied,process.env.JUDGE_USERNAME+':'+process.env.JUDGE_PASSWORD)) access = 'admin';
  else if (process.env.CARE_USERNAME && process.env.CARE_PASSWORD && await equalSecret(supplied,process.env.CARE_USERNAME+':'+process.env.CARE_PASSWORD)) access = 'care';
  else return NextResponse.json({detail:'The username or password is incorrect.'},{status:401});
  const response = NextResponse.json({redirect:'/overview'});
  response.cookies.set(sessionCookie,await makeSession(access),{httpOnly:true,sameSite:'lax',secure:request.headers.get('x-forwarded-proto')==='https' || request.nextUrl.protocol==='https:',path:'/',maxAge:8*60*60});
  response.cookies.set('pulse-profile','care',{httpOnly:true,sameSite:'lax',secure:request.headers.get('x-forwarded-proto')==='https' || request.nextUrl.protocol==='https:',path:'/',maxAge:8*60*60});
  response.headers.set('Cache-Control','no-store');
  return response;
}
