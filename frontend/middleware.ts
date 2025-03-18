import { createMiddlewareClient } from '@supabase/auth-helpers-nextjs';
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export async function middleware(req: NextRequest) {
  const res = NextResponse.next();
  
  // Crea un client Supabase per i cookies
  const supabase = createMiddlewareClient({ req, res });
  
  // Sincronizziamo i cookies ma non prendiamo decisioni di routing qui
  await supabase.auth.getSession();
  
  return res;
}

// Solo le route che vogliamo proteggere o sincronizzare i cookies
export const config = {
  matcher: [
    '/((?!api|_next/static|_next/image|favicon.ico|images).*)',
  ],
} 