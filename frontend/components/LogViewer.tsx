"use client";
import React, { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { Terminal, RefreshCw, Download, Filter, AlertCircle, Info, Bug, CheckCircle } from 'lucide-react';
import blockchainService from '../utils/blockchainAPI';
import toast from 'react-hot-toast';

const LogViewer = ({ isAdmin = false }) => {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState('all');
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [lines, setLines] = useState(100);
  const logContainerRef = useRef(null);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const response = await blockchainService.fetchLogs(lines, filter === 'all' ? null : filter);
      if (response.success) {
        setLogs(response.logs);
      }
    } catch (error) {
      toast.error('Failed to fetch logs');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [lines, filter]);

  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(fetchLogs, 5000);
      return () => clearInterval(interval);
    }
  }, [autoRefresh]);

  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs]);

  const getLogColor = (log) => {
    if (log.includes('[ERROR]') || log.includes('[error]')) return 'text-red-400';
    if (log.includes('[WARNING]') || log.includes('[warning]')) return 'text-yellow-400';
    if (log.includes('[INFO]') || log.includes('[info]')) return 'text-blue-400';
    if (log.includes('[DEBUG]') || log.includes('[debug]')) return 'text-gray-400';
    return 'text-gray-300';
  };

  const getLogIcon = (log) => {
    if (log.includes('[ERROR]')) return <AlertCircle className="w-3 h-3 text-red-400" />;
    if (log.includes('[WARNING]')) return <AlertCircle className="w-3 h-3 text-yellow-400" />;
    if (log.includes('[INFO]')) return <Info className="w-3 h-3 text-blue-400" />;
    if (log.includes('[DEBUG]')) return <Bug className="w-3 h-3 text-gray-400" />;
    return <CheckCircle className="w-3 h-3 text-gray-400" />;
  };

  const exportLogs = () => {
    const content = logs.join('\n');
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `chainbreak-logs-${new Date().toISOString().split('T')[0]}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Logs exported');
  };

  return (
    <div className="bg-gray-800/50 backdrop-blur-sm rounded-lg border border-gray-700/50 overflow-hidden">
      <div className="p-4 border-b border-gray-700 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <Terminal className="w-5 h-5 text-green-400" />
          <h3 className="text-lg font-semibold text-white">System Logs</h3>
          <span className="px-2 py-1 bg-gray-700 rounded text-xs text-gray-300">
            {logs.length} entries
          </span>
        </div>

        <div className="flex items-center space-x-2">
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="px-3 py-1.5 bg-gray-700 border border-gray-600 rounded-lg text-sm text-white"
          >
            <option value="all">All Levels</option>
            <option value="ERROR">Errors Only</option>
            <option value="WARNING">Warnings</option>
            <option value="INFO">Info</option>
            <option value="DEBUG">Debug</option>
          </select>

          <select
            value={lines}
            onChange={(e) => setLines(Number(e.target.value))}
            className="px-3 py-1.5 bg-gray-700 border border-gray-600 rounded-lg text-sm text-white"
          >
            <option value={50}>50 lines</option>
            <option value={100}>100 lines</option>
            <option value={250}>250 lines</option>
            <option value={500}>500 lines</option>
          </select>

          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`p-2 rounded-lg transition-colors ${autoRefresh ? 'bg-green-600 text-white' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            title={autoRefresh ? 'Stop auto-refresh' : 'Start auto-refresh'}
          >
            <RefreshCw className={`w-4 h-4 ${autoRefresh ? 'animate-spin' : ''}`} />
          </button>

          <button
            onClick={fetchLogs}
            disabled={loading}
            className="p-2 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600 transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>

          <button
            onClick={exportLogs}
            className="p-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            title="Export logs"
          >
            <Download className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div
        ref={logContainerRef}
        className="h-96 overflow-auto p-4 font-mono text-xs bg-gray-900/50"
      >
        {logs.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-500">
            No logs available
          </div>
        ) : (
          <div className="space-y-1">
            {logs.map((log, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.01 }}
                className={`flex items-start space-x-2 ${getLogColor(log)} hover:bg-gray-800/50 px-2 py-1 rounded`}
              >
                <span className="flex-shrink-0 mt-0.5">{getLogIcon(log)}</span>
                <span className="break-all">{log}</span>
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default LogViewer;
