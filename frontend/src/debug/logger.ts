export interface LogEntry {
  timestamp: string;
  level: "debug" | "info" | "warn" | "error";
  module: string;
  message: string;
  data?: unknown;
  correlationId?: string;
}

const MAX_ENTRIES = 1000;
const logBuffer: LogEntry[] = [];

let currentCorrelationId: string | undefined;

export function setCorrelationId(id: string): void {
  currentCorrelationId = id;
}

export function clearCorrelationId(): void {
  currentCorrelationId = undefined;
}

function addEntry(
  level: LogEntry["level"],
  module: string,
  message: string,
  data?: unknown,
): void {
  const entry: LogEntry = {
    timestamp: new Date().toISOString(),
    level,
    module,
    message,
    ...(data !== undefined && { data }),
    ...(currentCorrelationId && { correlationId: currentCorrelationId }),
  };
  logBuffer.push(entry);
  if (logBuffer.length > MAX_ENTRIES) {
    logBuffer.shift();
  }
}

export type Logger = ReturnType<typeof createLogger>;

export function createLogger(module: string) {
  return {
    debug(message: string, data?: unknown): void {
      addEntry("debug", module, message, data);
    },
    info(message: string, data?: unknown): void {
      addEntry("info", module, message, data);
    },
    warn(message: string, data?: unknown): void {
      addEntry("warn", module, message, data);
    },
    error(message: string, data?: unknown): void {
      addEntry("error", module, message, data);
    },
  };
}

export function getLogs(): readonly LogEntry[] {
  return logBuffer;
}

export function exportLogs(): string {
  return JSON.stringify(logBuffer, null, 2);
}

export function clearLogs(): void {
  logBuffer.length = 0;
}
