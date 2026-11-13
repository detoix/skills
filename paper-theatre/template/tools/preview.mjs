import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const FILM = path.resolve(import.meta.dirname, '../film');
const MIME = {
  '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json',
  '.png': 'image/png', '.wav': 'audio/wav',
};

function inside(root, file) {
  const relative = path.relative(root, file);
  return relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative);
}

export function serveFilm() {
  const root = fs.realpathSync(FILM);
  const server = http.createServer((req, res) => {
    let file;
    try {
      const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
      const requested = path.resolve(root, `.${pathname === '/' ? '/index.html' : pathname}`);
      if (!inside(root, requested)) return res.writeHead(404).end();
      file = fs.realpathSync(requested);
      if (!inside(root, file) || !fs.statSync(file).isFile()) return res.writeHead(404).end();
    } catch {
      return res.writeHead(404).end();
    }
    const stream = fs.createReadStream(file);
    stream.once('error', () => {
      if (res.headersSent) res.destroy();
      else res.writeHead(404).end();
    });
    stream.once('open', () => {
      res.writeHead(200, {
        'content-type': MIME[path.extname(file)] || 'application/octet-stream',
        'cache-control': 'no-store',
      });
      stream.pipe(res);
    });
  });
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

function executable(file) {
  try {
    fs.accessSync(file, fs.constants.X_OK);
    return fs.statSync(file).isFile();
  } catch {
    return false;
  }
}

export function findChrome() {
  if (process.env.CHROME) return process.env.CHROME;

  const windows = process.platform === 'win32';
  const names = windows
    ? ['chrome.exe', 'chromium.exe', 'msedge.exe', 'chrome-headless-shell.exe']
    : ['chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable', 'chrome', 'chrome-headless-shell'];
  const onPath = (process.env.PATH || '').split(path.delimiter).filter(Boolean)
    .flatMap((dir) => names.map((name) => path.resolve(dir, name)));
  const installed = process.platform === 'darwin'
    ? ['/Applications', path.join(os.homedir(), 'Applications')].flatMap((dir) =>
        ['Google Chrome', 'Chromium'].map((name) => path.join(dir, `${name}.app`, 'Contents/MacOS', name)))
    : windows
      ? [process.env.PROGRAMFILES, process.env['PROGRAMFILES(X86)'], process.env.LOCALAPPDATA]
          .filter(Boolean).map((dir) => path.join(dir, 'Google/Chrome/Application/chrome.exe'))
      : [];
  const browser = [...onPath, ...installed].find(executable);
  if (browser) return browser;

  const platformCache = windows ? (process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData/Local'))
    : process.platform === 'darwin' ? path.join(os.homedir(), 'Library/Caches')
    : (process.env.XDG_CACHE_HOME || path.join(os.homedir(), '.cache'));
  const cache = process.env.PLAYWRIGHT_BROWSERS_PATH === '0'
    ? path.resolve('node_modules/playwright-core/.local-browsers')
    : (process.env.PLAYWRIGHT_BROWSERS_PATH || path.join(platformCache, 'ms-playwright'));
  const entries = fs.existsSync(cache) ? fs.readdirSync(cache, { withFileTypes: true }) : [];
  const revisions = entries
    .filter((entry) => entry.isDirectory() && /^chromium(?:_headless_shell)?-\d+$/.test(entry.name))
    .map((entry) => entry.name)
    .sort((a, b) => Number(b.split('-').at(-1)) - Number(a.split('-').at(-1))
      || Number(b.includes('_headless_shell')) - Number(a.includes('_headless_shell')));
  for (const revision of revisions) {
    const dir = path.join(cache, revision);
    for (const build of fs.readdirSync(dir, { withFileTypes: true })) {
      if (!build.isDirectory()) continue;
      const binary = ['chrome-headless-shell', 'chrome-headless-shell.exe', 'headless_shell',
        'headless_shell.exe', 'chrome', 'chrome.exe',
        'Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
        'Chromium.app/Contents/MacOS/Chromium']
        .map((name) => path.join(dir, build.name, name)).find(executable);
      if (binary) return binary;
    }
  }
  throw new Error('Chromium or Chrome was not found. Set CHROME to its executable path.');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const server = await serveFilm();
  console.log(`http://127.0.0.1:${server.address().port}/`);
}
