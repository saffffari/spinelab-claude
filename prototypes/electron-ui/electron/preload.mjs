import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('desktop', {
  isDesktop: true,
  window: {
    minimize: () => ipcRenderer.invoke('window:minimize'),
    toggleMaximize: () => ipcRenderer.invoke('window:toggle-maximize'),
    close: () => ipcRenderer.invoke('window:close'),
    getState: () => ipcRenderer.invoke('window:get-state'),
    onStateChange: (callback) => {
      const listener = (_event, state) => callback(state);
      ipcRenderer.on('window:state-changed', listener);

      return () => {
        ipcRenderer.removeListener('window:state-changed', listener);
      };
    },
  },
  backend: {
    getStatus: () => ipcRenderer.invoke('backend:get-status'),
    invoke: (command, payload) => ipcRenderer.invoke('backend:invoke', { command, payload }),
  },
});
