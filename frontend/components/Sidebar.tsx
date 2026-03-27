"use client";
import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Download,
  Upload,
  RefreshCw,
  FileText,
  Search,
  Play,
  FolderOpen,
  AlertTriangle,
  CheckCircle,
  Loader2
} from 'lucide-react';
import logger from '../utils/logger';

const Sidebar = ({
  availableGraphs,
  onFetchGraph,
  onLoadGraph,
  onRefreshGraphs,
  onRunLouvain,
  isLoading,
  backendMode
}) => {
  const [address, setAddress] = useState('');
  const [txLimit, setTxLimit] = useState(1000);
  const [selectedGraph, setSelectedGraph] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);

  const handleFetchGraph = () => {
    if (!address.trim()) {
      logger.warn('Attempted to fetch graph with empty address');
      return;
    }
    onFetchGraph(address.trim(), txLimit);
    setAddress('');
  };

  const handleLoadGraph = () => {
    if (!selectedGraph) {
      logger.warn('Attempted to load graph without selection');
      return;
    }
    onLoadGraph(selectedGraph);
    setSelectedGraph('');
  };

  const handleRefreshGraphs = () => {
    logger.info('Refreshing graph list');
    onRefreshGraphs();
  };

  const handleRunLouvain = () => {
    logger.info('Running Louvain community detection');
    onRunLouvain();
  };

  const getBackendWarning = () => {
    if (backendMode === 'json') {
      return (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-3 mb-4"
        >
          <div className="flex items-center space-x-2 text-yellow-400 text-sm">
            <AlertTriangle className="w-4 h-4" />
            <span>Running in JSON mode - limited functionality</span>
          </div>
        </motion.div>
      );
    }
    return null;
  };

  return (
    <motion.aside
      initial={{ x: -300, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      className="w-80 bg-dark-800 border-r border-dark-700 flex flex-col"
    >
      <div className="p-6 border-b border-dark-700">
        <h2 className="text-lg font-semibold text-dark-100 mb-4">Graph Controls</h2>

        {getBackendWarning()}

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-dark-300 mb-2">
              UPI ID
            </label>
            <input
              type="text"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="Enter UPI ID..."
              className="input-field w-full"
              disabled={isLoading}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-dark-300 mb-2">
              Transaction Limit
            </label>
            <input
              type="number"
              value={txLimit}
              onChange={(e) => setTxLimit(Math.max(1, Math.min(1000, parseInt(e.target.value) || 1000)))}
              min="1"
              max="1000"
              className="input-field w-full"
              disabled={isLoading}
            />
          </div>

          <button
            onClick={handleFetchGraph}
            disabled={isLoading || !address.trim()}
            className="btn-primary w-full flex items-center justify-center space-x-2"
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Download className="w-4 h-4" />
            )}
            <span>Fetch & Save Graph</span>
          </button>
        </div>

        <div className="mt-6 pt-6 border-t border-dark-700">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-dark-300">Saved Graphs</h3>
            <button
              onClick={handleRefreshGraphs}
              disabled={isLoading}
              className="p-1.5 text-dark-400 hover:text-dark-200 hover:bg-dark-700 rounded transition-colors duration-200"
              title="Refresh"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          <div className="space-y-2 max-h-48 overflow-y-auto scrollbar-hide">
            <AnimatePresence>
              {availableGraphs.length === 0 ? (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="text-center py-4 text-dark-400 text-sm"
                >
                  <FileText className="w-8 h-8 mx-auto mb-2 opacity-50" />
                  <p>No graphs available</p>
                </motion.div>
              ) : (
                availableGraphs.map((graph, index) => (
                  <motion.div
                    key={graph}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.05 }}
                    className="flex items-center space-x-2 p-2 hover:bg-dark-700 rounded-lg transition-colors duration-200 cursor-pointer"
                    onClick={() => setSelectedGraph(graph)}
                  >
                    <FileText className="w-4 h-4 text-blue-400" />
                    <span className="text-sm text-dark-200 truncate flex-1">
                      {graph.replace('.json', '')}
                    </span>
                    {selectedGraph === graph && (
                      <CheckCircle className="w-4 h-4 text-green-400" />
                    )}
                  </motion.div>
                ))
              )}
            </AnimatePresence>
          </div>

          {availableGraphs.length > 0 && (
            <button
              onClick={handleLoadGraph}
              disabled={!selectedGraph || isLoading}
              className="btn-secondary w-full mt-3 flex items-center justify-center space-x-2"
            >
              <FolderOpen className="w-4 h-4" />
              <span>Load Selected Graph</span>
            </button>
          )}
        </div>

        <div className="mt-6 pt-6 border-t border-dark-700">
          <button
            onClick={handleRunLouvain}
            disabled={isLoading}
            className="btn-primary w-full flex items-center justify-center space-x-2"
          >
            <Play className="w-4 h-4" />
            <span>Run Louvain Algorithm</span>
          </button>

          <p className="text-xs text-dark-400 mt-2 text-center">
            Detects communities in the loaded graph
          </p>
        </div>

        <div className="mt-6 pt-6 border-t border-dark-700">
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="w-full text-left text-sm text-dark-400 hover:text-dark-200 transition-colors duration-200"
          >
            Advanced Options
          </button>

          <AnimatePresence>
            {showAdvanced && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="mt-3 space-y-3"
              >
                <div className="text-xs text-dark-400 space-y-2">
                  <p>• Backend Mode: {backendMode.toUpperCase()}</p>
                  <p>• Available Graphs: {availableGraphs.length}</p>
                  <p>• Status: {isLoading ? 'Processing' : 'Ready'}</p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.aside>
  );
};

export default Sidebar;
