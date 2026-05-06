import fs from 'node:fs/promises';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const root = process.cwd();
const dist = path.join(root, 'dist');

await fs.rm(dist, { recursive: true, force: true });
await fs.mkdir(dist, { recursive: true });

const docker = spawnSync(
  'docker',
  [
    'run',
    '--rm',
    '--volume',
    `${root}:/src:ro`,
    '--volume',
    `${dist}:/out`,
    '-w',
    '/work',
    'node:20-bookworm',
    'sh',
    '-lc',
    [
      "tar --exclude='node_modules' --exclude='.next' --exclude='dist' --exclude='data' -cf - -C /src . | tar -xf - -C /work",
      'npm ci --no-audit --no-fund',
      'npm run package:deploy',
      'cp -a dist/. /out/',
    ].join(' && '),
  ],
  { stdio: 'inherit' },
);

if (docker.status !== 0) {
  console.error('Linux deploy build failed. Make sure Docker is running and can pull node:20-bookworm.');
  process.exit(docker.status || 1);
}

console.log(`Linux-compatible deploy archive: ${path.join(dist, 'akfa-docs-platform-deploy.tar.gz')}`);
