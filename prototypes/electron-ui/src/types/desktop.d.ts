export {};

type DesktopWindowState = {
  isDesktop: boolean;
  isMaximized: boolean;
  platform: string;
};

type BackendStatus = {
  connected: boolean;
  mode: string;
  message: string;
};

type DesktopApi = {
  isDesktop: boolean;
  window: {
    minimize: () => Promise<void>;
    toggleMaximize: () => Promise<void>;
    close: () => Promise<void>;
    getState: () => Promise<DesktopWindowState>;
    onStateChange: (callback: (state: DesktopWindowState) => void) => () => void;
  };
  backend: {
    getStatus: () => Promise<BackendStatus>;
    invoke: (command: string, payload?: unknown) => Promise<unknown>;
  };
};

declare global {
  interface Window {
    desktop?: DesktopApi;
  }
}
