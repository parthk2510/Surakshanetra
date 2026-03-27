interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  data: unknown;
  id: number;
}

interface SyncEntry {
  timestamp: string;
  level: string;
  message: string;
  component: string;
}

interface AuditEntry {
  timestamp: string;
  action: string;
  component: string;
  message: string;
  level: string;
  extra: Record<string, unknown>;
}

class Logger {
  private logs: LogEntry[];
  private maxLogs: number;
  private levels: Record<string, number>;
  private currentLevel: number;
  private _syncBuffer: SyncEntry[];
  private _auditBuffer: AuditEntry[];
  private _syncInterval: ReturnType<typeof setInterval> | null;
  private _auditInterval: ReturnType<typeof setInterval> | null;

  constructor() {
    this.logs = [];
    this.maxLogs = 1000;
    this.levels = { DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3, CRITICAL: 4 };
    this.currentLevel = this.levels.INFO;
    this._syncBuffer = [];
    this._auditBuffer = [];
    this._syncInterval = null;
    this._auditInterval = null;

    if (typeof window !== 'undefined') {
      this._syncInterval = setInterval(() => this.flushToBackend(), 15000);
      this._auditInterval = setInterval(() => this.flushAuditToBackend(), 5000);
      window.addEventListener('beforeunload', () => {
        this.flushToBackend();
        this.flushAuditToBackend();
      });
    }
  }

  setLevel(level: string) {
    if (this.levels[level] !== undefined) {
      this.currentLevel = this.levels[level];
      this.info(`Log level set to: ${level}`);
    }
  }

  formatMessage(level: string, message: string, data: unknown = null): LogEntry {
    const timestamp = new Date().toISOString();
    const logEntry: LogEntry = { timestamp, level, message, data, id: Date.now() + Math.random() };
    this.logs.push(logEntry);
    if (this.logs.length > this.maxLogs) this.logs.shift();
    this._syncBuffer.push({ timestamp, level, message, component: 'ChainBreak' });
    return logEntry;
  }

  shouldLog(level: string): boolean {
    return this.levels[level] >= this.currentLevel;
  }

  debug(message: string, data: unknown = null) {
    if (this.shouldLog('DEBUG')) {
      const logEntry = this.formatMessage('DEBUG', message, data);
      console.debug(`[DEBUG] ${message}`, data);
      this.emitLogEvent(logEntry);
    }
  }

  info(message: string, data: unknown = null) {
    if (this.shouldLog('INFO')) {
      const logEntry = this.formatMessage('INFO', message, data);
      console.info(`[INFO] ${message}`, data);
      this.emitLogEvent(logEntry);
    }
  }

  warn(message: string, data: unknown = null) {
    if (this.shouldLog('WARN')) {
      const logEntry = this.formatMessage('WARN', message, data);
      console.warn(`[WARN] ${message}`, data);
      this.emitLogEvent(logEntry);
    }
  }

  error(message: string, error: unknown = null, data: unknown = null) {
    if (this.shouldLog('ERROR')) {
      const logEntry = this.formatMessage('ERROR', message, { error, data });
      console.error(`[ERROR] ${message}`, error, data);
      this.emitLogEvent(logEntry);
    }
  }

  critical(message: string, error: unknown = null, data: unknown = null) {
    if (this.shouldLog('CRITICAL')) {
      const logEntry = this.formatMessage('CRITICAL', message, { error, data });
      console.error(`[CRITICAL] ${message}`, error, data);
      this.emitLogEvent(logEntry);
    }
  }

  emitLogEvent(logEntry: LogEntry) {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('log', { detail: logEntry }));
    }
  }

  async flushToBackend() {
    if (this._syncBuffer.length === 0) return;
    const batch = this._syncBuffer.splice(0, this._syncBuffer.length);
    try {
      await fetch('/api/logs/sync', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ logs: batch }),
      });
    } catch {
    }
  }

  /** Send UI interaction audit events to backend for persistent logging. */
  audit(action: string, component: string, message: string, extra: Record<string, unknown> = {}) {
    const entry: AuditEntry = {
      timestamp: new Date().toISOString(),
      action,
      component,
      message,
      level: 'INFO',
      extra,
    };
    this._auditBuffer.push(entry);
    // Also emit to in-memory log
    this.formatMessage('INFO', `[AUDIT] ${component}:${action} — ${message}`, extra);
  }

  async flushAuditToBackend() {
    if (this._auditBuffer.length === 0) return;
    const batch = this._auditBuffer.splice(0, this._auditBuffer.length);
    for (const entry of batch) {
      try {
        await fetch('/api/audit/event', {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(entry),
        });
      } catch {
      }
    }
  }

  getLogs(level: string | null = null, limit = 100): LogEntry[] {
    let filteredLogs = this.logs;
    if (level) filteredLogs = this.logs.filter(log => log.level === level);
    return filteredLogs.slice(-limit);
  }

  clearLogs() {
    this.logs = [];
    this.info('Logs cleared');
  }

  exportLogs() {
    const logData = {
      exportTime: new Date().toISOString(),
      totalLogs: this.logs.length,
      logs: this.logs
    };
    const blob = new Blob([JSON.stringify(logData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `chainbreak-logs-${new Date().toISOString().split('T')[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
    this.info('Logs exported successfully');
  }

  logPerformance(operation: string, startTime: number, endTime: number, metadata: Record<string, unknown> = {}) {
    const duration = endTime - startTime;
    this.info(`Performance: ${operation} completed in ${duration.toFixed(2)}ms`, {
      operation, duration, startTime, endTime, ...metadata
    });
  }

  logGraphOperation(operation: string, nodeCount: number, edgeCount: number, metadata: Record<string, unknown> = {}) {
    this.info(`Graph Operation: ${operation}`, {
      operation, nodeCount, edgeCount, timestamp: new Date().toISOString(), ...metadata
    });
  }

  logAPIRequest(method: string | undefined, endpoint: string | undefined, status: number, duration: number, metadata: Record<string, unknown> = {}) {
    const level = (status >= 400 ? 'WARN' : 'INFO') as 'WARN' | 'INFO';
    if (level === 'WARN') {
      this.warn(`API Request: ${method} ${endpoint}`, {
        method, endpoint, status, duration: `${duration.toFixed(2)}ms`, timestamp: new Date().toISOString(), ...metadata
      });
    } else {
      this.info(`API Request: ${method} ${endpoint}`, {
        method, endpoint, status, duration: `${duration.toFixed(2)}ms`, timestamp: new Date().toISOString(), ...metadata
      });
    }
  }
}

const logger = new Logger();

declare global {
  interface Window {
    logger?: Logger;
    toast?: { error: (msg: string) => void };
  }
}

// Only expose globally in development — prevents log data leakage via XSS in production
if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
  (window as any).logger = logger;
}

export default logger;
