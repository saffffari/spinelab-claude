export class PythonBridge {
  async getStatus() {
    return {
      connected: false,
      mode: 'placeholder',
      message: 'Renderer-only preview. Attach your Python process in electron/python-bridge.mjs when you are ready.',
    };
  }

  async invoke(command, payload = {}) {
    throw new Error(
      `No Python backend is attached yet. Wire command "${command}" in electron/python-bridge.mjs before invoking it.`,
    );
  }
}

export const pythonBridge = new PythonBridge();
