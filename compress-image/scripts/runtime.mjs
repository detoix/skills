import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { access, copyFile, mkdir, mkdtemp, readFile, rename, rm } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const skill = fileURLToPath(new URL('../', import.meta.url));
const manifestFiles = ['package.json', 'package-lock.json'];

async function exists(file) {
  try {
    await access(file);
    return true;
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    return false;
  }
}

export async function loadSharp() {
  const hash = createHash('sha256');
  for (const file of manifestFiles) hash.update(await readFile(join(skill, file)));
  const libc = process.platform === 'linux'
    ? (process.report.getReport().header.glibcVersionRuntime ? '-glibc' : '-musl')
    : '';
  const root = join(skill, '.runtime');
  const version = hash.digest('hex').slice(0, 16);
  const target = join(root, `${process.platform}-${process.arch}-${process.versions.modules}-${version}${libc}`);
  const sharp = join(target, 'node_modules', 'sharp');
  const require = createRequire(import.meta.url);
  if (await exists(sharp)) return require(sharp);

  await mkdir(root, { recursive: true });
  const staging = await mkdtemp(join(root, 'install-'));
  try {
    await Promise.all(manifestFiles.map(file => copyFile(join(skill, file), join(staging, file))));
    const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
    const install = spawnSync(npm, ['ci', '--include=optional', '--ignore-scripts', '--no-audit', '--no-fund'], {
      cwd: staging,
      shell: process.platform === 'win32',
      stdio: ['ignore', 2, 2],
    });
    if (install.error?.code === 'ENOENT') throw new Error('Install npm to set up the local runtime.');
    if (install.error) throw install.error;
    if (install.status !== 0) throw new Error('Dependency setup failed. Check npm access and retry.');
    const check = spawnSync(process.execPath, ['-e', 'require("./node_modules/sharp")'], {
      cwd: staging,
      stdio: ['ignore', 2, 2],
    });
    if (check.error) throw check.error;
    if (check.status !== 0) throw new Error('Sharp did not load on this platform.');
    try {
      await rename(staging, target);
    } catch (error) {
      // Another invocation may have published its completed install first.
      if (!['EEXIST', 'ENOTEMPTY', 'EPERM'].includes(error.code) || !(await exists(sharp))) throw error;
    }
  } finally {
    await rm(staging, { recursive: true, force: true });
  }
  return require(sharp);
}
