export interface ElectronAPI {
  onApiReady: (cb: (data: { baseUrl: string }) => void) => void;
  openFile: (opts: { title?: string; filters?: { name: string; extensions: string[] }[]; defaultPath?: string }) => Promise<string[] | null>;
  openDirectory: (opts?: { title?: string; defaultPath?: string }) => Promise<string | null>;
  openPath: (filePath: string) => Promise<string>;
  showItemInFolder: (filePath: string) => Promise<void>;
  openExternal: (url: string) => Promise<void>;
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}

export {};
