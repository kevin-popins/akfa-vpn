import { NextResponse } from 'next/server';

import { adminHasTotp, createLoginChallenge, createSession, publicAdmin, verifyPassword } from '@/lib/auth';
import { error } from '@/lib/api-response';

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const email = String(body?.email || '');
  const password = String(body?.password || '');
  const admin = await verifyPassword(email, password);
  if (!admin) return error('Неверный логин или пароль', 401);
  if (adminHasTotp(admin)) {
    return NextResponse.json({
      requires_2fa: true,
      temp_token: createLoginChallenge(admin.id),
      admin: publicAdmin(admin),
    });
  }
  const session = await createSession(email, password);
  return NextResponse.json(session);
}
