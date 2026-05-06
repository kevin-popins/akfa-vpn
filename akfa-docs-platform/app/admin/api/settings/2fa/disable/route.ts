import { NextResponse } from 'next/server';

import { assertCsrf, currentAdmin, publicAdmin, verifyPasswordForAdmin } from '@/lib/auth';
import { disableAdminTotp } from '@/lib/db';
import { error } from '@/lib/api-response';

export async function POST(request: Request) {
  try {
    await assertCsrf(request);
    const admin = await currentAdmin();
    if (!admin) return error('Нужно войти в админку', 401);
    const body = await request.json().catch(() => null);
    const password = String(body?.password || '');
    if (!(await verifyPasswordForAdmin(admin.id, password))) return error('Неверный пароль', 401);
    const updated = disableAdminTotp(admin.id);
    return NextResponse.json(publicAdmin(updated || admin));
  } catch (err) {
    if (err instanceof Error && err.message === 'CSRF') return error('Неверный CSRF-токен', 403);
    return error(err instanceof Error ? err.message : 'Не удалось отключить 2FA', 422);
  }
}
