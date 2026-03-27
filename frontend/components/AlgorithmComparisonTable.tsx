'use client';
import React from 'react';
import { BarChart3, TrendingUp, Clock, CheckCircle, XCircle } from 'lucide-react';
import { motion } from 'framer-motion';

const AlgorithmComparisonTable = ({ results }) => {
  const algorithms = [
    { key: 'louvain', name: 'Louvain', colorClass: 'bg-purple-500' },
    { key: 'leiden', name: 'Leiden', colorClass: 'bg-emerald-500' },
    { key: 'labelPropagation', name: 'Label Propagation', colorClass: 'bg-blue-500' },
    { key: 'infomap', name: 'Infomap', colorClass: 'bg-amber-500' }
  ];

  const getResult = (algorithmKey) => {
    return results[algorithmKey] || null;
  };

  const formatModularity = (value) => {
    if (value === null || value === undefined) return 'N/A';
    return value.toFixed(4);
  };

  const getQualityBadge = (modularity) => {
    if (modularity === null || modularity === undefined) {
      return <span className="text-gray-400 text-xs">Not run</span>;
    }
    if (modularity > 0.5) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-500/20 text-green-400 rounded text-xs">
          <CheckCircle className="w-3 h-3" />
          Excellent
        </span>
      );
    } else if (modularity > 0.3) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-1 bg-yellow-500/20 text-yellow-400 rounded text-xs">
          <CheckCircle className="w-3 h-3" />
          Good
        </span>
      );
    } else {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-1 bg-orange-500/20 text-orange-400 rounded text-xs">
          <XCircle className="w-3 h-3" />
          Weak
        </span>
      );
    }
  };

  const hasAnyResults = algorithms.some(algo => getResult(algo.key) !== null);

  if (!hasAnyResults) {
    return (
      <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
        <div className="flex items-center gap-2 text-gray-400 mb-2">
          <BarChart3 className="w-5 h-5" />
          <h3 className="text-lg font-semibold">Algorithm Comparison</h3>
        </div>
        <p className="text-gray-500 text-sm">
          Run community detection algorithms to see comparison results
        </p>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="bg-gray-800 rounded-lg border border-gray-700 overflow-hidden"
    >
      <div className="p-4 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-blue-400" />
          <h3 className="text-lg font-semibold text-white">Algorithm Comparison</h3>
        </div>
        <p className="text-gray-400 text-sm mt-1">
          Compare performance metrics across different community detection algorithms
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-700">
              <th className="text-left p-4 text-sm font-medium text-gray-300">Algorithm</th>
              <th className="text-center p-4 text-sm font-medium text-gray-300">
                <div className="flex items-center justify-center gap-1">
                  <TrendingUp className="w-4 h-4" />
                  Communities
                </div>
              </th>
              <th className="text-center p-4 text-sm font-medium text-gray-300">
                <div className="flex items-center justify-center gap-1">
                  <BarChart3 className="w-4 h-4" />
                  Modularity
                </div>
              </th>
              <th className="text-center p-4 text-sm font-medium text-gray-300">
                <div className="flex items-center justify-center gap-1">
                  <Clock className="w-4 h-4" />
                  Status
                </div>
              </th>
              <th className="text-center p-4 text-sm font-medium text-gray-300">Quality</th>
            </tr>
          </thead>
          <tbody>
            {algorithms.map((algorithm, index) => {
              const result = getResult(algorithm.key);
              const isAvailable = result !== null;

              return (
                <motion.tr
                  key={algorithm.key}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.3, delay: index * 0.1 }}
                  className={`border-b border-gray-700/50 hover:bg-gray-750 transition-colors ${isAvailable ? '' : 'opacity-50'
                    }`}
                >
                  <td className="p-4">
                    <div className="flex items-center gap-2">
                      <div className={`w-3 h-3 rounded-full ${algorithm.colorClass}`} />
                      <span className="font-medium text-white">{algorithm.name}</span>
                    </div>
                  </td>
                  <td className="p-4 text-center">
                    {isAvailable ? (
                      <span className="text-white font-semibold">
                        {result.num_communities || result.numCommunities || 0}
                      </span>
                    ) : (
                      <span className="text-gray-500">-</span>
                    )}
                  </td>
                  <td className="p-4 text-center">
                    {isAvailable ? (
                      <span className="text-white font-mono">
                        {formatModularity(result.modularity)}
                      </span>
                    ) : (
                      <span className="text-gray-500">-</span>
                    )}
                  </td>
                  <td className="p-4 text-center">
                    {isAvailable ? (
                      <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-500/20 text-green-400 rounded text-xs">
                        <CheckCircle className="w-3 h-3" />
                        Completed
                      </span>
                    ) : (
                      <span className="text-gray-500 text-xs">Not run</span>
                    )}
                  </td>
                  <td className="p-4 text-center">
                    {isAvailable ? getQualityBadge(result.modularity) : (
                      <span className="text-gray-500 text-xs">-</span>
                    )}
                  </td>
                </motion.tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="p-4 bg-gray-900/50 border-t border-gray-700">
        <div className="flex items-start gap-2 text-xs text-gray-400">
          <div className="w-4 h-4 flex items-center justify-center">
            <BarChart3 className="w-3 h-3" />
          </div>
          <div>
            <p className="font-medium text-gray-300 mb-1">About Modularity:</p>
            <p>
              Modularity measures the quality of community detection. Higher values (closer to 1.0) indicate
              better-defined communities. Values above 0.3 are generally considered good, while values above 0.5
              indicate excellent community structure.
            </p>
          </div>
        </div>
      </div>
    </motion.div>
  );
};

export default AlgorithmComparisonTable;

