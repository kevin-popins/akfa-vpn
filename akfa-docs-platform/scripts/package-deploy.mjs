import fs from 'node:fs/promises';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const root = process.cwd();
const dist = path.join(root, 'dist');
const runtime = path.join(dist, 'akfa-docs-platform');

async function exists(file) {
  try {
    await fs.access(file);
    return true;
  } catch {
    return false;
  }
}

async function copyIfExists(from, to) {
  if (await exists(from)) {
    await fs.cp(from, to, { recursive: true, dereference: true });
  }
}

await fs.rm(dist, { recursive: true, force: true });
await fs.mkdir(runtime, { recursive: true });

await fs.cp(path.join(root, '.next', 'standalone'), runtime, { recursive: true, dereference: true });
await fs.mkdir(path.join(runtime, '.next'), { recursive: true });
await fs.cp(path.join(root, '.next', 'static'), path.join(runtime, '.next', 'static'), { recursive: true, dereference: true });
await copyIfExists(path.join(root, 'public'), path.join(runtime, 'public'));
await copyIfExists(path.join(root, 'seed-downloads'), path.join(runtime, 'seed-downloads'));
await fs.mkdir(path.join(runtime, 'data'), { recursive: true });

for (const file of ['.env.example', 'README_DEPLOY.md']) {
  await fs.copyFile(path.join(root, file), path.join(runtime, file));
}

await fs.mkdir(path.join(runtime, 'deploy'), { recursive: true });
await fs.cp(path.join(root, 'deploy'), path.join(runtime, 'deploy'), { recursive: true, dereference: true });

const archiveName = 'akfa-docs-platform-deploy.tar.gz';
const archivePath = path.join(dist, archiveName);
const tar = spawnSync('tar', ['-czf', archivePath, '-C', dist, 'akfa-docs-platform'], { stdio: 'inherit' });

if (tar.status !== 0) {
  console.log(`Runtime folder is ready: ${runtime}`);
  console.log('tar is not available or failed, archive was not created.');
  process.exit(tar.status || 1);
}

console.log(`Deploy folder: ${runtime}`);
console.log(`Deploy archive: ${archivePath}`);
