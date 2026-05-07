import { NextResponse } from 'next/server';

import { assertCsrf, requireAdmin } from '@/lib/auth';
import { createArticle, listAllArticles } from '@/lib/db';
import { error } from '@/lib/api-response';
import { articleSchema } from '@/lib/validation';

export async function GET() {
  try {
    await requireAdmin();
    return NextResponse.json(listAllArticles());
  } catch {
    return error('Нужно войти в админку', 401);
  }
}

export async function POST(request: Request) {
  try {
    await requireAdmin();
    await assertCsrf(request);
    const payload = articleSchema.parse(await request.json());
    const article = createArticle(payload);
    return NextResponse.json(article, { status: 201 });
  } catch (err) {
    if (err instanceof Error && err.message === 'UNAUTHORIZED') return error('Нужно войти в админку', 401);
    if (err instanceof Error && err.message === 'CSRF') return error('Неверный CSRF-токен', 403);
    if (err instanceof Error && err.message.includes('UNIQUE')) return error('Статья с таким slug уже существует', 409);
    return error(err instanceof Error ? err.message : 'Статья не создана', 422);
  }
}
