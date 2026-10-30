const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("anki", {
  api: (command, payload) => ipcRenderer.invoke("api", { command, payload }),
  sync: (rebuild) => ipcRenderer.invoke("sync", { rebuild: Boolean(rebuild) }),
  onSyncProgress: (callback) => {
    const listener = (_event, data) => callback(data);
    ipcRenderer.on("sync-progress", listener);
    return () => ipcRenderer.removeListener("sync-progress", listener);
  },
  server: (action) => ipcRenderer.invoke("server", { action }),
  onServerExit: (callback) => {
    const listener = (_event, data) => callback(data);
    ipcRenderer.on("server-exit", listener);
    return () => ipcRenderer.removeListener("server-exit", listener);
  },
});
