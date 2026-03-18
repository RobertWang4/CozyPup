import { exportLogs } from "./logger";

export function downloadLogs(): void {
  const blob = new Blob([exportLogs()], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `petpal-logs-${Date.now()}.json`;
  document.body.appendChild(a);
  try {
    a.click();
  } finally {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }
}

export function isCapacitorAvailable(): boolean {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return typeof (window as any).Capacitor !== "undefined";
}

export async function writeLogsToFile(): Promise<string | null> {
  if (!isCapacitorAvailable()) {
    downloadLogs();
    return null;
  }
  try {
    // Dynamic import — Capacitor packages are only available in native builds.
    // Use a variable to prevent tsc from resolving the module at compile time.
    const fsModule = "@capacitor/filesystem";
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const mod: any = await import(fsModule);
    const fileName = `petpal-logs-${Date.now()}.json`;
    const result = await mod.Filesystem.writeFile({
      path: fileName,
      data: exportLogs(),
      directory: mod.Directory.Documents,
      encoding: mod.Encoding.UTF8,
    });
    return result.uri as string;
  } catch {
    downloadLogs();
    return null;
  }
}

export async function shareLogFile(): Promise<void> {
  const path = await writeLogsToFile();
  if (!path || !isCapacitorAvailable()) return;
  try {
    const shareModule = "@capacitor/share";
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const shareMod: any = await import(shareModule);
    await shareMod.Share.share({
      title: "PetPal Debug Logs",
      url: path,
    });
  } catch {
    // Share not available, file was already written
  }
}
