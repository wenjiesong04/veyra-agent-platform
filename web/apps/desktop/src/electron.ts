export function isElectronDesktop(): boolean {
  return typeof window.veyraDesktop?.openExternal === "function";
}
