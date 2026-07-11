/**
 * JARVIS Desktop — Electron Main Process
 * =======================================
 * - Creates a frameless BrowserWindow (1280×800) with custom titlebar
 * - Spawns the FastAPI backend (uvicorn main:app) as a child process
 * - System tray icon with Show/Hide, Restart Backend, Quit
 * - IPC handlers for renderer ↔ main communication
 * - Graceful shutdown: kills backend on app quit
 */

const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage, shell } = require('electron');
const path  = require('path');
const { spawn, execSync } = require('child_process');
const http  = require('http');
const fs    = require('fs');

// ── Config ────────────────────────────────────────────────────────────────────
const BACKEND_PORT  = 8000;
const BACKEND_HOST  = '127.0.0.1';
const BACKEND_URL   = `http://${BACKEND_HOST}:${BACKEND_PORT}`;
const PYTHON_SCRIPT = path.join(__dirname, '..', 'main.py');
const RENDERER_HTML = path.join(__dirname, 'renderer', 'index.html');
const ICON_PATH     = path.join(__dirname, 'assets', 'icon.png');

let mainWindow  = null;
let tray        = null;
let backendProc = null;
let backendReady = false;

// ── Backend management ────────────────────────────────────────────────────────

function findPython() {
  const candidates = ['python3', 'python', 'py'];
  for (const cmd of candidates) {
    try { execSync(`${cmd} --version`, { stdio: 'ignore' }); return cmd; }
    catch (_) {}
  }
  return 'python';
}

function startBackend() {
  if (backendProc) return;
  const python = findPython();
  const env = { ...process.env, JARVIS_LLM_PROVIDER: 'mock' };

  console.log(`[JARVIS] Starting backend: ${python} ${PYTHON_SCRIPT}`);
  backendProc = spawn(python, [PYTHON_SCRIPT, '--port', String(BACKEND_PORT)], {
    cwd: path.dirname(PYTHON_SCRIPT),
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  backendProc.stdout.on('data', d => {
    const msg = d.toString().trim();
    console.log(`[backend] ${msg}`);
    if (msg.includes('Application startup complete') || msg.includes('Uvicorn running')) {
      backendReady = true;
      notifyRenderer('backend-status', 'online');
    }
  });

  backendProc.stderr.on('data', d => console.error(`[backend-err] ${d.toString().trim()}`));

  backendProc.on('exit', (code) => {
    console.log(`[JARVIS] Backend exited (code ${code})`);
    backendProc = null;
    backendReady = false;
    notifyRenderer('backend-status', 'offline');
  });

  // Poll until ready (max 30s)
  pollBackend(0);
}

function pollBackend(attempt) {
  if (attempt > 30) { console.warn('[JARVIS] Backend did not start in 30s'); return; }
  http.get(`${BACKEND_URL}/health`, (res) => {
    if (res.statusCode === 200) {
      backendReady = true;
      notifyRenderer('backend-status', 'online');
    }
  }).on('error', () => setTimeout(() => pollBackend(attempt + 1), 1000));
}

function stopBackend() {
  if (!backendProc) return;
  console.log('[JARVIS] Stopping backend...');
  backendProc.kill('SIGTERM');
  setTimeout(() => { if (backendProc) backendProc.kill('SIGKILL'); }, 3000);
  backendProc = null;
}

function restartBackend() {
  stopBackend();
  setTimeout(startBackend, 1500);
}

// ── Window ────────────────────────────────────────────────────────────────────

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    frame: false,
    titleBarStyle: 'hidden',
    backgroundColor: '#07070f',
    icon: fs.existsSync(ICON_PATH) ? ICON_PATH : undefined,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: false,
    },
  });

  mainWindow.loadFile(RENDERER_HTML);

  if (process.env.JARVIS_DEV) mainWindow.webContents.openDevTools();

  mainWindow.on('closed', () => { mainWindow = null; });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
}

// ── Tray ──────────────────────────────────────────────────────────────────────

function createTray() {
  const icon = fs.existsSync(ICON_PATH)
    ? nativeImage.createFromPath(ICON_PATH).resize({ width: 16, height: 16 })
    : nativeImage.createEmpty();

  tray = new Tray(icon);
  tray.setToolTip('JARVIS AI Assistant');
  updateTrayMenu();

  tray.on('click', () => {
    if (mainWindow) {
      mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show();
    }
  });
}

function updateTrayMenu() {
  if (!tray) return;
  const menu = Menu.buildFromTemplate([
    { label: 'JARVIS AI Assistant', enabled: false },
    { type: 'separator' },
    {
      label: mainWindow?.isVisible() ? 'Hide Window' : 'Show Window',
      click: () => {
        if (!mainWindow) { createWindow(); return; }
        mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show();
        updateTrayMenu();
      },
    },
    {
      label: `Backend: ${backendReady ? '🟢 Online' : '🔴 Offline'}`,
      enabled: false,
    },
    {
      label: 'Restart Backend',
      click: () => { restartBackend(); updateTrayMenu(); },
    },
    { type: 'separator' },
    { label: 'Open Dashboard', click: () => { if (mainWindow) mainWindow.show(); } },
    { label: 'Open API Docs', click: () => shell.openExternal(`${BACKEND_URL}/docs`) },
    { type: 'separator' },
    { label: 'Quit JARVIS', click: () => app.quit() },
  ]);
  tray.setContextMenu(menu);
}

// ── IPC handlers ──────────────────────────────────────────────────────────────

function notifyRenderer(channel, data) {
  if (mainWindow?.webContents) {
    mainWindow.webContents.send(channel, data);
  }
}

ipcMain.handle('get-backend-status', () => backendReady ? 'online' : 'offline');
ipcMain.handle('get-backend-url',    () => BACKEND_URL);
ipcMain.handle('restart-backend',    () => { restartBackend(); return true; });
ipcMain.handle('quit-app',           () => app.quit());

ipcMain.on('window-minimize', () => mainWindow?.minimize());
ipcMain.on('window-maximize', () => {
  if (!mainWindow) return;
  mainWindow.isMaximized() ? mainWindow.unmaximize() : mainWindow.maximize();
});
ipcMain.on('window-close', () => mainWindow?.close());

// ── App lifecycle ─────────────────────────────────────────────────────────────

app.whenReady().then(() => {
  createWindow();
  createTray();
  startBackend();

  setInterval(updateTrayMenu, 5000);

  app.on('activate', () => { if (!mainWindow) createWindow(); });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => stopBackend());

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) { mainWindow.show(); mainWindow.focus(); }
  });
}
