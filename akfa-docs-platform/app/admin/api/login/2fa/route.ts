import { NextResponse } from 'next/server';

import { createSessionForAdmin, verifyAdminTotp, verifyLoginChallenge } from '@/lib/auth';
import { findAdminById } from '@/lib/db';
import { error } from '@/lib/api-response';

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const token = String(body?.temp_token || '');
  const code = String(body?.code || '');
  const challenge = verifyLoginChallenge(token);
  if (!challenge) return error('Временный вход истёк. Войдите заново.', 401);
  const admin = findAdminById(challenge.adminId);
  if (!admin || !verifyAdminTotp(admin, code)) return error('Неверный код 2FA', 401);
  const session = await createSessionForAdmin(admin.id);
  return NextResponse.json(session);
}
