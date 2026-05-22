import { contextBridge, ipcRenderer } from "electron";

export interface ElectronAPI {
  onApiReady: (cb: (data: { baseUrl: string }) => void) => void;
  openFile: (opts: Electron.OpenDialogOptions) => Promise<string[] | null>;
  openDirectory: (opts?: Electron.OpenDialogOptions) => Promise<string | null>;
  openPath: (filePath: string) => Promise<string>;
  showItemInFolder: (filePath: string) => Promise<void>;
  openExternal: (url: string) => Promise<void>;
}

const electronAPI: ElectronAPI = {
  onApiReady: (cb) => {
    ipcRenderer.on("api-ready", (_e, data) => cb(data));
  },
  openFile: (opts) => ipcRenderer.invoke("dialog:openFile", opts),
  openDirectory: (opts) => ipcRenderer.invoke("dialog:openDirectory", opts),
  showItemInFolder: (filePath) => ipcRenderer.invoke("shell:showItemInFolder", filePath),
  openPath: (filePath) => ipcRenderer.invoke("shell:openPath", filePath),
  openExternal: (url) => ipcRenderer.invoke("shell:openExternal", url),
};

contextBridge.exposeInMainWorld("electronAPI", electronAPI);
