import { spawn } from 'node:child_process';
import path from 'node:path';
import process from 'node:process';
import { createRequire } from 'node:module';
import waitOn from 'wait-on';

const require = createRequire(import.meta.url);
const electronBinary = require('electron');
const viteCli = path.join(process.cwd(), 'node_modules', 'vite', 'bin', 'vite.js');
const rendererUrl = 'http://127.0.0.1:5173';

let shuttingDown = false;

const viteProcess = spawn(process.execPath, [viteCli, '--host', '127.0.0.1', '--strictPort'], {
  stdio: 'inherit',
  env: process.env,
});

function shutdown(exitCode = 0) {
  if (shuttingDown) {
    return;
  }

  shuttingDown = true;

  if (!viteProcess.killed) {
    viteProcess.kill();
  }

  process.exit(exitCode);
}

process.on('SIGINT', () => shutdown(0));
process.on('SIGTERM', () => shutdown(0));

viteProcess.on('exit', (code) => {
  if (!shuttingDown) {
    shutdown(code ?? 0);
  }
});

viteProcess.on('error', (error) => {
  console.error('Failed to start Vite for Electron development.');
  console.error(error);
  shutdown(1);
});

try {
  await waitOn({
    resources: [rendererUrl],
    timeout: 60_000,
    validateStatus: (status) => status === 200,
  });
} catch (error) {
  console.error('Electron dev launch failed: Vite did not become ready.');
  console.error(error);
  shutdown(1);
}

const electronProcess = spawn(electronBinary, ['.'], {
  stdio: 'inherit',
  env: {
    ...process.env,
    ELECTRON_RENDERER_URL: rendererUrl,
  },
});

electronProcess.on('error', (error) => {
  console.error('Failed to launch the Electron desktop window.');
  console.error(error);
  shutdown(1);
});

electronProcess.on('exit', (code) => {
  shutdown(code ?? 0);
});
