
# SpineLab Desktop

This project now uses the exported React UI as a launchable Windows-style desktop app shell.

## Run it

Install dependencies once:

```bash
npm install
```

Launch the desktop app in development mode:

```bash
npm run desktop:dev
```

This starts the Vite renderer in the background and opens the Electron desktop window directly.

Launch the built desktop app:

```bash
npm run desktop
```

If you want the browser-only preview instead, run:

```bash
npm run dev
```

## Python backend hook

The Electron bridge is set up so you can attach a Python process later without replacing the UI:

- `electron/main.mjs`: desktop window lifecycle and IPC wiring
- `electron/preload.mjs`: safe renderer bridge exposed as `window.desktop`
- `electron/python-bridge.mjs`: placeholder service where the Python process/API can be connected
  
