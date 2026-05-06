import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';

import { assertCsrf, requireAdmin } from '@/lib/auth';
import { error, ok } from '@/lib/api-response';
import { appConfig } from '@/lib/config';

const allowed = new Map([
  ['image/png', '.png'],
  ['image/jpeg', '.jpg'],
  ['image/webp', '.webp'],
  ['image/gif', '.gif'],
]);

export async function POST(request: Request) {
  try {
    await requireAdmin();
    await assertCsrf(request);
    const data = await request.formData();
    const file = data.get('file');
    if (!(file instanceof File)) return error('Файл не найден', 422);
    const ext = allowed.get(file.type);
    if (!ext) return error('Можно загружать только изображения PNG, JPG, WEBP или GIF', 422);
    if (file.size > appConfig.maxUploadBytes) return error('Файл слишком большой', 422);
    await fs.mkdir(appConfig.uploadDir, { recursive: true });
    const name = `${Date.now()}-${crypto.randomBytes(8).toString('hex')}${ext}`;
    const target = path.join(appConfig.uploadDir, name);
    await fs.writeFile(target, Buffer.from(await file.arrayBuffer()));
    return ok({ url: `/uploads/${name}` });
  } catch (err) {
    if (err instanceof Error && err.message === 'UNAUTHORIZED') return error('Нужно войти в админку', 401);
    if (err instanceof Error && err.message === 'CSRF') return error('Неверный CSRF-токен', 403);
    return error('Изображение не загружено', 422);
  }
}
