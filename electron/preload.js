/**
 * JARVIS Desktop — Preload Script
 * ================================
 * Exposes a safe, minimal IPC bridge to the renderer via contextBridge.
 * The renderer can call window.electronAPI.* methods.
 * No Node.js APIs are exposed directly.
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // ── Queries ────────────────────────────────────────────────────────────────
  getBackendStatus: () => ipcRenderer.invoke('get-backend-status'),
  getBackendUrl:    () => ipcRenderer.invoke('get-backend-url'),

  // ── Actions ────────────────────────────────────────────────────────────────
  restartBackend: () => ipcRenderer.invoke('restart-backend'),
  quitApp:        () => ipcRenderer.invoke('quit-app'),

  // ── Window controls (custom titlebar) ─────────────────────────────────────
  minimizeWindow: () => ipcRenderer.send('window-minimize'),
  maximizeWindow: () => ipcRenderer.send('window-maximize'),
  closeWindow:    () => ipcRenderer.send('window-close'),

  // ── Event listeners ────────────────────────────────────────────────────────
  onBackendStatus: (callback) => {
    ipcRenderer.on('backend-status', (_event, status) => callback(status));
  },

  // ── Utility ────────────────────────────────────────────────────────────────
  isDesktop: () => true,
  platform:  () => process.platform,
});
