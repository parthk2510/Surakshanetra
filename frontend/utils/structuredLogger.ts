// @ts-nocheck
/**
 * Structured Logger for ChainBreak Frontend
 * 
 * Provides structured logging with format:
 * {timestamp, request_id, user_id, route, action, status, latency_ms, payload_hash}
 * 
 * Syncs critical events to backend for centralized logging.
 */

// Simple ID generator (no external dependencies)
const generateId = () => {
    return Math.random().toString(36).substring(2, 10) + Date.now().toString(36).slice(-4);
};

// Simple hash function for payload traceability
const hashPayload = (payload) => {
    if (!payload) return null;
    try {
        const str = typeof payload === 'string' ? payload : JSON.stringify(payload);
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash;
        }
        return Math.abs(hash).toString(16).substring(0, 12);
    } catch {
        return null;
    }
};

// Get or create session ID
const getSessionId = () => {
    let sessionId = sessionStorage.getItem('chainbreak_session_id');
    if (!sessionId) {
        sessionId = generateId();
        sessionStorage.setItem('chainbreak_session_id', sessionId);
    }
    return sessionId;
};

// Get user ID from stored user profile or mark as anonymous
const getUserId = () => {
    try {
        const user = localStorage.getItem('chainbreak_user');
        if (user) {
            const parsed = JSON.parse(user);
            return parsed.id || parsed.username || 'authenticated';
        }
    } catch { }
    return 'anonymous';
};

class StructuredLogger {
    logs: object[];
    maxLogs: number;
    sessionId: string;
    syncEnabled: boolean;
    syncBatchSize: number;
    syncInterval: number;
    pendingSync: object[];

    constructor() {
        this.logs = [];
        this.maxLogs = 500;
        this.sessionId = getSessionId();
        this.syncEnabled = true;
        this.syncBatchSize = 10;
        this.syncInterval = 30000; // 30 seconds
        this.pendingSync = [];

        // Start sync timer
        this._startSyncTimer();
    }

    /**
     * Create a structured log record
     */
    _createRecord(action, status, options = {}) {
        const { latency_ms, payload, message, level, extra } = options;

        return {
            timestamp: new Date().toISOString(),
            request_id: generateId(),
            user_id: getUserId(),
            route: window.location.pathname,
            action,
            status,
            latency_ms: latency_ms ? Math.round(latency_ms) : null,
            payload_hash: hashPayload(payload),
            level: level || 'INFO',
            message: message || '',
            ...extra
        };
    }

    /**
     * Add log to internal store and optionally queue for sync
     */
    _log(record, syncToBackend = false) {
        // Add to internal logs
        this.logs.push(record);
        if (this.logs.length > this.maxLogs) {
            this.logs.shift();
        }

        // Console output with formatting
        const logFn = record.level === 'ERROR' ? console.error :
            record.level === 'WARN' ? console.warn :
                record.level === 'DEBUG' ? console.debug : console.log;

        const prefix = `[${record.timestamp.split('T')[1].split('.')[0]}] [${record.action}]`;
        if (record.latency_ms) {
            logFn(`${prefix} ${record.status} (${record.latency_ms}ms)`, record.message);
        } else {
            logFn(`${prefix} ${record.status}`, record.message);
        }

        // Queue for backend sync if needed
        if (syncToBackend && this.syncEnabled) {
            this.pendingSync.push(record);
        }

        // Emit event for LogViewer
        window.dispatchEvent(new CustomEvent('structured-log', { detail: record }));
    }

    // ========================================================================
    // Core Logging Methods
    // ========================================================================

    info(action, message = '', options = {}) {
        const record = this._createRecord(action, 'success', {
            ...options,
            message,
            level: 'INFO'
        });
        this._log(record, options.sync);
    }

    warn(action, message = '', options = {}) {
        const record = this._createRecord(action, 'warning', {
            ...options,
            message,
            level: 'WARN'
        });
        this._log(record, options.sync);
    }

    error(action, message = '', options = {}) {
        const record = this._createRecord(action, 'error', {
            ...options,
            message,
            level: 'ERROR',
            extra: options.error ? { error_type: options.error.name, error_msg: options.error.message } : {}
        });
        this._log(record, true); // Always sync errors
    }

    debug(action, message = '', options = {}) {
        const record = this._createRecord(action, 'debug', {
            ...options,
            message,
            level: 'DEBUG'
        });
        this._log(record, false);
    }

    // ========================================================================
    // Specialized Logging Methods
    // ========================================================================

    /**
     * Log an API request
     */
    apiRequest(endpoint, method, status, latency_ms, options = {}) {
        this.info(`api.${endpoint.replace(/\//g, '.')}`, `${method} ${status}`, {
            latency_ms,
            payload: options.payload,
            sync: status >= 400,
            extra: { method, status_code: status }
        });
    }

    /**
     * Log a user action
     */
    userAction(action, details = '', payload = null) {
        this.info(`user.${action}`, details, {
            payload,
            sync: true
        });
    }

    /**
     * Log a state transition
     */
    stateTransition(from, to, entity = '') {
        this.info('state.transition', `${entity}: ${from} -> ${to}`, {
            extra: { from_state: from, to_state: to, entity },
            sync: true
        });
    }

    /**
     * Log temporal analysis events
     */
    temporalAnalysis(action, details = {}, latency_ms = null) {
        this.info(`temporal.${action}`, JSON.stringify(details), {
            latency_ms,
            payload: details,
            sync: true
        });
    }

    /**
     * Log graph interaction events
     */
    graphInteraction(action, details = {}) {
        this.info(`graph.${action}`, '', {
            payload: details,
            sync: action.includes('error')
        });
    }

    /**
     * Log investigation events
     */
    investigation(action, address = '', details = {}) {
        this.info(`investigation.${action}`, address, {
            payload: details,
            sync: true
        });
    }

    // ========================================================================
    // Performance Tracking
    // ========================================================================

    /**
     * Start timing an operation
     */
    startTimer(operation) {
        return {
            operation,
            startTime: performance.now()
        };
    }

    /**
     * End timing and log
     */
    endTimer(timer, status = 'success', details = '') {
        const latency_ms = performance.now() - timer.startTime;
        this.info(`perf.${timer.operation}`, details, { latency_ms, sync: latency_ms > 5000 });
        return latency_ms;
    }

    // ========================================================================
    // Log Management
    // ========================================================================

    getLogs(level = null, limit = 100) {
        let filtered = this.logs;
        if (level) {
            filtered = this.logs.filter(log => log.level === level);
        }
        return filtered.slice(-limit);
    }

    clearLogs() {
        this.logs = [];
        this.info('logger.clear', 'Logs cleared');
    }

    exportLogs() {
        const data = {
            exportTime: new Date().toISOString(),
            sessionId: this.sessionId,
            totalLogs: this.logs.length,
            logs: this.logs
        };

        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `chainbreak-logs-${new Date().toISOString().split('T')[0]}.json`;
        a.click();
        URL.revokeObjectURL(url);
    }

    // ========================================================================
    // Backend Sync
    // ========================================================================

    _startSyncTimer() {
        setInterval(() => {
            this._syncToBackend();
        }, this.syncInterval);
    }

    async _syncToBackend() {
        if (!this.syncEnabled || this.pendingSync.length === 0) return;

        const logsToSync = this.pendingSync.splice(0, this.syncBatchSize);

        try {
            await fetch('/api/logs/sync', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ logs: logsToSync })
            });
        } catch (error) {
            // Re-add failed logs to queue
            this.pendingSync.unshift(...logsToSync);
            console.debug('Log sync failed, will retry:', error);
        }
    }

    disableSync() {
        this.syncEnabled = false;
    }

    enableSync() {
        this.syncEnabled = true;
    }
}

// Create singleton instance
const structuredLogger = new StructuredLogger();

// Only expose globally in development — prevents log data leakage via XSS in production
if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
    (window as any).slog = structuredLogger;
}

export default structuredLogger;
