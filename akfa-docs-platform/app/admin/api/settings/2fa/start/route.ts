import QRCode from 'qrcode';
import { NextResponse } from 'next/server';

import { assertCsrf, currentAdmin } from '@/lib/auth';
import { updateAdminTotpPending } from '@/lib/db';
import { error } from '@/lib/api-response';
import { generateTotpSecret, totpUri } from '@/lib/totp';

export async function POST(request: Request) {
  try {
    await assertCsrf(request);
    const admin = await currentAdmin();
    if (!admin) return error('Нужно войти в админку', 401);
    const secret = generateTotpSecret();
    updateAdminTotpPending(admin.id, secret);
    const otpauth_url = totpUri(secret, admin.email);
    const qr_data_url = await QRCode.toDataURL(otpauth_url, { margin: 1, width: 240 });
    return NextResponse.json({ secret, otpauth_url, qr_data_url });
  } catch (err) {
    if (err instanceof Error && err.message === 'CSRF') return error('Неверный CSRF-токен', 403);
    return error(err instanceof Error ? err.message : 'Не удалось начать настройку 2FA', 422);
  }
}
