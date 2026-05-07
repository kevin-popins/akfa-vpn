import fs from 'node:fs';
import path from 'node:path';

import { appConfig } from './config';

export type DownloadManifestItem = {
  key: string;
  title: string;
  platform: string;
  version?: string;
  filename: string;
  source: string;
  publicPath: string;
};

export type DownloadInfo = DownloadManifestItem & {
  exists: boolean;
  size: number | null;
  updatedAt: string | null;
};

const manifestPath = path.join(process.cwd(), 'seed-downloads', 'downloads.manifest.json');

function safeBasename(value: string) {
  const base = path.basename(value);
  if (base !== value || base.startsWith('.') || !/^[A-Za-z0-9._-]+$/.test(base)) {
    throw new Error('Invalid download filename');
  }
  return base;
}

export function readDownloadManifest(): DownloadManifestItem[] {
  if (!fs.existsSync(manifestPath)) return [];
  const parsed = JSON.parse(fs.readFileSync(manifestPath, 'utf8')) as { downloads?: DownloadManifestItem[] };
  return (parsed.downloads || []).map((item) => {
    const filename = safeBasename(item.filename);
    return {
      ...item,
      filename,
      source: safeBasename(item.source),
      publicPath: item.publicPath || `/downloads/${filename}`,
    };
  });
}

export function downloadTargetPath(filename: string) {
  const safe = safeBasename(filename);
  const target = path.join(appConfig.downloadsDir, safe);
  const root = path.resolve(appConfig.downloadsDir);
  if (!path.resolve(target).startsWith(`${root}${path.sep}`)) throw new Error('Invalid download path');
  return target;
}

export function downloadExtension(filename: string) {
  return path.extname(filename).replace('.', '').toLowerCase();
}

export function assertAllowedDownload(filename: string, size: number) {
  const ext = downloadExtension(filename);
  if (!appConfig.allowedDownloadExtensions.includes(ext)) {
    throw new Error(`Allowed extensions: ${appConfig.allowedDownloadExtensions.join(', ')}`);
  }
  if (size > appConfig.maxDownloadBytes) {
    throw new Error(`Max download size is ${Math.floor(appConfig.maxDownloadBytes / 1024 / 1024)} MB`);
  }
}

export function listDownloads(): DownloadInfo[] {
  return readDownloadManifest().map((item) => {
    const target = downloadTargetPath(item.filename);
    if (!fs.existsSync(target)) return { ...item, exists: false, size: null, updatedAt: null };
    const stat = fs.statSync(target);
    return {
      ...item,
      exists: stat.isFile(),
      size: stat.isFile() ? stat.size : null,
      updatedAt: stat.isFile() ? stat.mtime.toISOString() : null,
    };
  });
}
