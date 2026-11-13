const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('veyraDesktop', {
  openExternal: (url) => ipcRenderer.invoke('veyra:open-external', url),
});
