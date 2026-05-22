import { app, BrowserWindow, ipcMain, dialog, shell } from "electron";
import path from "path";
import { PythonBridge } from "./python-bridge";

let mainWindow: BrowserWindow | null = null;
let pythonBridge: PythonBridge | null = null;

const isDev = !app.isPackaged;

function createWindow(apiBaseUrl: string) {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    backgroundColor: "#050A10",
    title: "Ghost Creator AI — Neural Interface",
    icon: path.join(__dirname, "..", "icon.ico"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  mainWindow.webContents.on("did-finish-load", () => {
    mainWindow?.webContents.send("api-ready", { baseUrl: apiBaseUrl });
  });

  if (isDev) {
    mainWindow.loadURL("http://localhost:5173");
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

async function bootstrap() {
  pythonBridge = new PythonBridge();
  const apiBaseUrl = await pythonBridge.start();
  createWindow(apiBaseUrl);
}

app.whenReady().then(bootstrap);

app.on("window-all-closed", () => {
  pythonBridge?.stop();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  pythonBridge?.stop();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0 && pythonBridge) {
    createWindow(pythonBridge.baseUrl);
  }
});

ipcMain.handle("dialog:openFile", async (_evt, opts: Electron.OpenDialogOptions) => {
  const win = BrowserWindow.getFocusedWindow() ?? mainWindow;
  if (!win) return null;
  const result = await dialog.showOpenDialog(win, opts);
  return result.canceled ? null : result.filePaths;
});

ipcMain.handle("dialog:openDirectory", async (_evt, opts: Electron.OpenDialogOptions) => {
  const win = BrowserWindow.getFocusedWindow() ?? mainWindow;
  if (!win) return null;
  const result = await dialog.showOpenDialog(win, { ...opts, properties: ["openDirectory"] });
  return result.canceled ? null : result.filePaths[0] ?? null;
});

ipcMain.handle("shell:openPath", async (_evt, filePath: string) => {
  return shell.openPath(filePath);
});

ipcMain.handle("shell:showItemInFolder", async (_evt, filePath: string) => {
  shell.showItemInFolder(filePath);
});

ipcMain.handle("shell:openExternal", async (_evt, url: string) => {
  await shell.openExternal(url);
});
