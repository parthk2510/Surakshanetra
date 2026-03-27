// @ts-nocheck
'use client';
import React from 'react';
import { motion } from 'framer-motion';
import { X, Info, Hash, Calendar, DollarSign, Network, MapPin, Clock, ArrowUpRight, ArrowDownLeft, Activity, Layers, Zap } from 'lucide-react';

const NodeDetails = ({ node, onClose, btcPrice, graphData, threatIntelData, onThreatIntelUpdate }: { node: unknown; onClose?: () => void; btcPrice?: unknown; graphData?: unknown; threatIntelData?: unknown; onThreatIntelUpdate?: (data: unknown) => void }) => {
  if (!node) return null;

  const formatValue = (value) => {
    if (typeof value === 'number') {
      if (value > 1000000) return `${(value / 1000000).toFixed(2)}M`;
      if (value > 1000) return `${(value / 1000).toFixed(2)}K`;
      return value.toString();
    }
    return value;
  };

  const formatSatoshi = (satoshi) => {
    if (typeof satoshi !== 'number') return '0';
    const btc = satoshi / 100000000;
    if (btc >= 1) return `${btc.toFixed(8)} BTC`;
    return `${satoshi} sat`;
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'Unknown';
    const date = new Date(timestamp * 1000);
    return date.toLocaleString();
  };

  const getNodeTypeColor = (nodeType) => {
    switch (nodeType) {
      case 'address':
        return 'text-green-400';
      case 'transaction':
        return 'text-blue-400';
      default:
        return 'text-gray-400';
    }
  };

  const getNodeTypeIcon = (nodeType) => {
    switch (nodeType) {
      case 'address':
        return <MapPin className="w-5 h-5 text-green-400" />;
      case 'transaction':
        return <Hash className="w-5 h-5 text-blue-400" />;
      default:
        return <Info className="w-5 h-5 text-gray-400" />;
    }
  };

  const getNodeType = (node) => {
    if (node.type) return node.type;
    if (node.id && node.id.length > 40) return 'transaction';
    return 'address';
  };

  const nodeType = getNodeType(node);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 20 }}
      className="bg-gray-800/90 backdrop-blur-sm rounded-lg border border-gray-700/50 p-6 shadow-2xl max-w-2xl"
    >
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center space-x-3">
          {getNodeTypeIcon(nodeType)}
          <h3 className="text-lg font-semibold text-white">Node Details</h3>
          <span className={`px-2 py-1 text-xs font-medium rounded-full bg-gray-700 ${getNodeTypeColor(nodeType)}`}>
            {nodeType.toUpperCase()}
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg transition-colors"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      <div className="space-y-6">
        {/* Node ID */}
        <div className="p-4 bg-gray-700/30 rounded-lg">
          <div className="flex items-center space-x-2 mb-3">
            <Hash className="w-4 h-4 text-blue-400" />
            <span className="text-sm font-medium text-gray-300">Node ID</span>
          </div>
          <p className="text-sm text-gray-200 font-mono break-all bg-gray-800/50 p-2 rounded">
            {node.id}
          </p>
        </div>

        {/* Address-specific information */}
        {nodeType === 'address' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {node.balance !== undefined && (
              <div className="p-4 bg-green-900/20 border border-green-500/30 rounded-lg">
                <div className="flex items-center space-x-2 mb-2">
                  <DollarSign className="w-4 h-4 text-green-400" />
                  <span className="text-sm font-medium text-green-300">Current Balance</span>
                </div>
                <p className="text-lg font-semibold text-green-200">
                  {formatSatoshi(node.balance)}
                </p>
              </div>
            )}

            {node.total_received !== undefined && (
              <div className="p-4 bg-blue-900/20 border border-blue-500/30 rounded-lg">
                <div className="flex items-center space-x-2 mb-2">
                  <ArrowDownLeft className="w-4 h-4 text-blue-400" />
                  <span className="text-sm font-medium text-blue-300">Total Received</span>
                </div>
                <p className="text-lg font-semibold text-blue-200">
                  {formatSatoshi(node.total_received)}
                </p>
              </div>
            )}

            {node.total_sent !== undefined && (
              <div className="p-4 bg-red-900/20 border border-red-500/30 rounded-lg">
                <div className="flex items-center space-x-2 mb-2">
                  <ArrowUpRight className="w-4 h-4 text-red-400" />
                  <span className="text-sm font-medium text-red-300">Total Sent</span>
                </div>
                <p className="text-lg font-semibold text-red-200">
                  {formatSatoshi(node.total_sent)}
                </p>
              </div>
            )}

            {node.transaction_count !== undefined && (
              <div className="p-4 bg-purple-900/20 border border-purple-500/30 rounded-lg">
                <div className="flex items-center space-x-2 mb-2">
                  <Activity className="w-4 h-4 text-purple-400" />
                  <span className="text-sm font-medium text-purple-300">Transactions</span>
                </div>
                <p className="text-lg font-semibold text-purple-200">
                  {formatValue(node.transaction_count)}
                </p>
              </div>
            )}
          </div>
        )}

        {/* Transaction-specific information */}
        {nodeType === 'transaction' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {node.timestamp && (
              <div className="p-4 bg-blue-900/20 border border-blue-500/30 rounded-lg">
                <div className="flex items-center space-x-2 mb-2">
                  <Clock className="w-4 h-4 text-blue-400" />
                  <span className="text-sm font-medium text-blue-300">Timestamp</span>
                </div>
                <p className="text-sm text-blue-200">
                  {formatTimestamp(node.timestamp)}
                </p>
              </div>
            )}

            {node.fee !== undefined && (
              <div className="p-4 bg-yellow-900/20 border border-yellow-500/30 rounded-lg">
                <div className="flex items-center space-x-2 mb-2">
                  <Zap className="w-4 h-4 text-yellow-400" />
                  <span className="text-sm font-medium text-yellow-300">Fee</span>
                </div>
                <p className="text-lg font-semibold text-yellow-200">
                  {formatSatoshi(node.fee)}
                </p>
              </div>
            )}

            {node.size !== undefined && (
              <div className="p-4 bg-gray-900/20 border border-gray-500/30 rounded-lg">
                <div className="flex items-center space-x-2 mb-2">
                  <Layers className="w-4 h-4 text-gray-400" />
                  <span className="text-sm font-medium text-gray-300">Size</span>
                </div>
                <p className="text-sm text-gray-200">
                  {formatValue(node.size)} bytes
                </p>
              </div>
            )}

            {node.input_count !== undefined && node.output_count !== undefined && (
              <div className="p-4 bg-indigo-900/20 border border-indigo-500/30 rounded-lg">
                <div className="flex items-center space-x-2 mb-2">
                  <Network className="w-4 h-4 text-indigo-400" />
                  <span className="text-sm font-medium text-indigo-300">I/O Count</span>
                </div>
                <div className="text-sm text-indigo-200">
                  <p>Inputs: {node.input_count}</p>
                  <p>Outputs: {node.output_count}</p>
                </div>
              </div>
            )}

            {node.total_input_value !== undefined && (
              <div className="p-4 bg-green-900/20 border border-green-500/30 rounded-lg">
                <div className="flex items-center space-x-2 mb-2">
                  <ArrowDownLeft className="w-4 h-4 text-green-400" />
                  <span className="text-sm font-medium text-green-300">Total Input Value</span>
                </div>
                <p className="text-lg font-semibold text-green-200">
                  {formatSatoshi(node.total_input_value)}
                </p>
              </div>
            )}

            {node.total_output_value !== undefined && (
              <div className="p-4 bg-red-900/20 border border-red-500/30 rounded-lg">
                <div className="flex items-center space-x-2 mb-2">
                  <ArrowUpRight className="w-4 h-4 text-red-400" />
                  <span className="text-sm font-medium text-red-300">Total Output Value</span>
                </div>
                <p className="text-lg font-semibold text-red-200">
                  {formatSatoshi(node.total_output_value)}
                </p>
              </div>
            )}
          </div>
        )}

        {/* Time information for addresses */}
        {nodeType === 'address' && (node.first_seen || node.last_seen) && (
          <div className="p-4 bg-gray-700/30 rounded-lg">
            <div className="flex items-center space-x-2 mb-3">
              <Calendar className="w-4 h-4 text-gray-400" />
              <span className="text-sm font-medium text-gray-300">Activity Timeline</span>
            </div>
            <div className="space-y-2 text-sm text-gray-200">
              {node.first_seen && (
                <p><span className="text-gray-400">First seen:</span> {formatTimestamp(node.first_seen)}</p>
              )}
              {node.last_seen && (
                <p><span className="text-gray-400">Last seen:</span> {formatTimestamp(node.last_seen)}</p>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="mt-6 p-3 bg-blue-900/20 border border-blue-500/30 rounded-lg">
        <p className="text-sm text-blue-300">
          <strong>Tip:</strong> Click on different nodes in the graph to view their details. Use the fullscreen mode for better visualization.
        </p>
      </div>
    </motion.div>
  );
};

export default NodeDetails;
