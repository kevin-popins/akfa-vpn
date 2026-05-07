import { NextResponse } from 'next/server';

import { assertCsrf, destroySession } from '@/lib/auth';

export async function POST(request: Request) {
  await assertCsrf(request);
  await destroySession();
  return NextResponse.json({ ok: true });
}
