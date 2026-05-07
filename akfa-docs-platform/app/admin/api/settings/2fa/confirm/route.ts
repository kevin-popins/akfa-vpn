import { NextResponse } from 'next/server';

import { assertCsrf, currentAdmin, publicAdmin } from '@/lib/auth';
import { confirmAdminTotp } from '@/lib/db';
import { error } from '@/lib/api-response';
import { verifyTotp } from '@/lib/totp';

export async function POST(request: Request) {
  try {
    await assertCsrf(request);
    const admin = await currentAdmin();
    if (!admin) return error('Нужно войти в админку', 401);
    const body = await request.json().catch(() => null);
    const code = String(body?.code || '');
    if (!admin.pending_totp_secret) return error('Сначала начните настройку 2FA', 400);
    if (!verifyTotp(admin.pending_totp_secret, code)) return error('Неверный код 2FA', 422);
    const updated = confirmAdminTotp(admin.id, admin.pending_totp_secret);
    return NextResponse.json(publicAdmin(updated || admin));
  } catch (err) {
    if (err instanceof Error && err.message === 'CSRF') return error('Неверный CSRF-токен', 403);
    return error(err instanceof Error ? err.message : 'Не удалось подтвердить 2FA', 422);
  }
}
