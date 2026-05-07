import { NextResponse } from 'next/server';

import { currentAdmin, publicAdmin } from '@/lib/auth';
import { error } from '@/lib/api-response';

export async function GET() {
  const admin = await currentAdmin();
  if (!admin) return error('Нужно войти в админку', 401);
  return NextResponse.json(publicAdmin(admin));
}
