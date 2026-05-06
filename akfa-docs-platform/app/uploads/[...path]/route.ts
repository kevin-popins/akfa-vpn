import fs from 'node:fs/promises';
import path from 'node:path';
import { NextResponse } from 'next/server';

import { appConfig } from '@/lib/config';

const types: Record<string, string> = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
};

export async function GET(_request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  const { path: parts } = await params;
  const name = parts.join('/');
  if (name.includes('..') || name.includes('\\')) return new NextResponse('Not found', { status: 404 });
  const filePath = path.join(appConfig.uploadDir, name);
  const ext = path.extname(filePath).toLowerCase();
  const type = types[ext];
  if (!type) return new NextResponse('Not found', { status: 404 });
  try {
    const file = await fs.readFile(filePath);
    return new NextResponse(file, {
      headers: {
        'Content-Type': type,
        'Cache-Control': 'public, max-age=31536000, immutable',
      },
    });
  } catch {
    return new NextResponse('Not found', { status: 404 });
  }
}
