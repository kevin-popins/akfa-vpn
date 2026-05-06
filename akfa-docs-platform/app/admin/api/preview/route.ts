import { assertCsrf, requireAdmin } from '@/lib/auth';
import { error, ok } from '@/lib/api-response';
import { renderMarkdown } from '@/lib/markdown';

export async function POST(request: Request) {
  try {
    await requireAdmin();
    await assertCsrf(request);
    const body = await request.json();
    return ok({ html: renderMarkdown(String(body?.content || '')) });
  } catch (err) {
    if (err instanceof Error && err.message === 'UNAUTHORIZED') return error('Нужно войти в админку', 401);
    if (err instanceof Error && err.message === 'CSRF') return error('Неверный CSRF-токен', 403);
    return error('Предпросмотр недоступен', 422);
  }
}
