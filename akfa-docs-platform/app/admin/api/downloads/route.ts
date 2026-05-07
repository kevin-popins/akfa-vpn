import fs from 'node:fs/promises';

import { assertCsrf, requireAdmin } from '@/lib/auth';
import { error, ok } from '@/lib/api-response';
import { appConfig } from '@/lib/config';
import { assertAllowedDownload, downloadExtension, downloadTargetPath, listDownloads, readDownloadManifest } from '@/lib/downloads';

export async function GET() {
  try {
    await requireAdmin();
    return ok({ downloads: listDownloads(), maxMb: Math.floor(appConfig.maxDownloadBytes / 1024 / 1024), allowedExtensions: appConfig.allowedDownloadExtensions });
  } catch (err) {
    if (err instanceof Error && err.message === 'UNAUTHORIZED') return error('Нужно войти в админку', 401);
    return error('Файлы недоступны', 500);
  }
}

export async function POST(request: Request) {
  try {
    await requireAdmin();
    await assertCsrf(request);
    const data = await request.formData();
    const key = String(data.get('key') || '');
    const file = data.get('file');
    if (!(file instanceof File)) return error('Файл не найден', 422);
    const item = readDownloadManifest().find((entry) => entry.key === key);
    if (!item) return error('Файл не описан в manifest', 404);
    if (file.name.includes('/') || file.name.includes('\\') || file.name.startsWith('.')) return error('Некорректное имя файла', 422);
    assertAllowedDownload(item.filename, file.size);
    assertAllowedDownload(file.name, file.size);
    if (downloadExtension(file.name) !== downloadExtension(item.filename)) return error('Расширение файла не совпадает со стабильным именем', 422);
    await fs.mkdir(appConfig.downloadsDir, { recursive: true });
    await fs.writeFile(downloadTargetPath(item.filename), Buffer.from(await file.arrayBuffer()), { mode: 0o640 });
    return ok({ download: listDownloads().find((entry) => entry.key === key) });
  } catch (err) {
    if (err instanceof Error && err.message === 'UNAUTHORIZED') return error('Нужно войти в админку', 401);
    if (err instanceof Error && err.message === 'CSRF') return error('Неверный CSRF-токен', 403);
    return error(err instanceof Error ? err.message : 'Файл не загружен', 422);
  }
}
