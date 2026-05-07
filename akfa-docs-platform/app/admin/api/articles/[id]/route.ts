import { NextResponse } from 'next/server';

import { assertCsrf, requireAdmin } from '@/lib/auth';
import { deleteArticle, getArticleById, updateArticle } from '@/lib/db';
import { error } from '@/lib/api-response';
import { articleSchema } from '@/lib/validation';

export async function PUT(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    await requireAdmin();
    await assertCsrf(request);
    const { id: rawId } = await params;
    const id = Number(rawId);
    if (!getArticleById(id)) return error('Статья не найдена', 404);
    const payload = articleSchema.parse(await request.json());
    return NextResponse.json(updateArticle(id, payload));
  } catch (err) {
    if (err instanceof Error && err.message === 'UNAUTHORIZED') return error('Нужно войти в админку', 401);
    if (err instanceof Error && err.message === 'CSRF') return error('Неверный CSRF-токен', 403);
    if (err instanceof Error && err.message.includes('UNIQUE')) return error('Статья с таким slug уже существует', 409);
    return error(err instanceof Error ? err.message : 'Статья не сохранена', 422);
  }
}

export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    await requireAdmin();
    await assertCsrf(request);
    const { id: rawId } = await params;
    const id = Number(rawId);
    deleteArticle(id);
    return NextResponse.json({ ok: true });
  } catch (err) {
    if (err instanceof Error && err.message === 'UNAUTHORIZED') return error('Нужно войти в админку', 401);
    if (err instanceof Error && err.message === 'CSRF') return error('Неверный CSRF-токен', 403);
    return error('Статья не удалена', 422);
  }
}
