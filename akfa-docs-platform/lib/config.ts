import path from 'node:path';

export const appConfig = {
  siteUrl: process.env.SITE_URL || 'https://help.kevinrobertson.ru',
  dataDir: process.env.DATA_DIR || path.join(process.cwd(), 'data'),
  uploadDir: path.join(process.env.DATA_DIR || path.join(process.cwd(), 'data'), 'uploads'),
  dbPath: path.join(process.env.DATA_DIR || path.join(process.cwd(), 'data'), 'akfa-docs.sqlite'),
  sessionSecret: process.env.SESSION_SECRET || 'dev-only-change-this-secret',
  adminEmail: process.env.ADMIN_EMAIL || 'admin@example.com',
  adminPassword: process.env.ADMIN_PASSWORD || 'ChangeMe123!',
  maxUploadBytes: Number(process.env.MAX_UPLOAD_MB || 5) * 1024 * 1024,
};

export function downloadUrl(fileName: string) {
  return `${appConfig.siteUrl.replace(/\/$/, '')}/downloads/${fileName}`;
}
