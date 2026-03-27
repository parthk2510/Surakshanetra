"use client";
import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Bitcoin, Search, Settings, Users, AlertTriangle } from 'lucide-react';
import { parseAddresses, isValidBitcoinAddress } from '../utils/formatters';

const AddressInput = ({ onSubmit, onClusterSubmit, isLoading }) => {
    const [input, setInput] = useState('');
    const [txLimit, setTxLimit] = useState(50);
    const [showAdvanced, setShowAdvanced] = useState(false);
    const [mode, setMode] = useState('single');

    const handleSubmit = (e) => {
        
        e.preventDefault();
        if (!input.trim()) return;

        const addresses = parseAddresses(input);

        const invalidAddresses = addresses.filter(addr => !isValidBitcoinAddress(addr));
        if (invalidAddresses.length > 0) {
            alert(`Invalid Bitcoin address(es): ${invalidAddresses.join(', ')}`);
            return;
        }

        if (addresses.length === 0) {
            return;
        }

        if (addresses.length === 1 || mode === 'single') {
            onSubmit(addresses[0], txLimit);
        } else {
            onClusterSubmit(addresses, txLimit);
        }
    };

    const handleTxLimitChange = (e) => {
        const value = parseInt(e.target.value) || 50;
        setTxLimit(Math.max(1, value));
    };

    const addressCount = parseAddresses(input).length;
    const isClusterMode = addressCount > 1;

    return (
        <div className="bg-gray-800/50 backdrop-blur-sm rounded-lg border border-gray-700/50 p-6">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-3">
                    <Bitcoin className="w-6 h-6 text-blue-500" />
                    <h3 className="text-lg font-semibold text-white">
                        {isClusterMode ? 'Suspect Cluster Analysis' : 'Fetch Transaction Data'}
                    </h3>
                </div>

                {isClusterMode && (
                    <div className="flex items-center space-x-2 px-3 py-1 bg-red-500/20 border border-red-500/50 rounded-full">
                        <AlertTriangle className="w-4 h-4 text-red-400" />
                        <span className="text-xs font-medium text-red-400">
                            {addressCount} Suspects
                        </span>
                    </div>
                )}
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                    <label htmlFor="address" className="block text-sm font-medium text-gray-300 mb-2">
                        {isClusterMode ? 'Suspect Addresses (comma-separated)' : 'Bitcoin Address'}
                    </label>
                    <div className="relative">
                        <textarea
                            id="address"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            placeholder={isClusterMode
                                ? "Enter multiple addresses separated by commas...\ne.g. 1A1zP..., 1BvBM..., bc1q..."
                                : "Enter Bitcoin address"
                            }
                            rows={isClusterMode ? 4 : 2}
                            className="w-full px-4 py-3 bg-gray-700/50 border border-gray-600/50 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
                            disabled={isLoading}
                        />
                        <div className="absolute top-3 right-3 flex items-center space-x-2">
                            {isClusterMode ? (
                                <Users className="w-5 h-5 text-red-400" />
                            ) : (
                                <Bitcoin className="w-5 h-5 text-gray-400" />
                            )}
                        </div>
                    </div>

                    {isClusterMode && (
                        <div className="mt-2 p-3 bg-red-900/20 border border-red-500/30 rounded-lg">
                            <p className="text-sm text-red-300">
                                <strong>Forensic Mode:</strong> Analyzing {addressCount} suspect addresses.
                                High-probability links will be highlighted in orange.
                            </p>
                        </div>
                    )}
                </div>

                <div className="flex items-center justify-between">
                    <button
                        type="button"
                        onClick={() => setShowAdvanced(!showAdvanced)}
                        className="flex items-center space-x-2 text-sm text-gray-400 hover:text-gray-300 transition-colors"
                    >
                        <Settings className="w-4 h-4" />
                        <span>Advanced Options</span>
                    </button>

                    {addressCount > 1 && (
                        <div className="flex items-center space-x-2 text-xs text-gray-400">
                            <span>Mode:</span>
                            <button
                                type="button"
                                onClick={() => setMode('single')}
                                className={`px-2 py-1 rounded ${mode === 'single'
                                    ? 'bg-blue-600 text-white'
                                    : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
                                    }`}
                            >
                                Single
                            </button>
                            <button
                                type="button"
                                onClick={() => setMode('cluster')}
                                className={`px-2 py-1 rounded ${mode === 'cluster'
                                    ? 'bg-red-600 text-white'
                                    : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
                                    }`}
                            >
                                Cluster
                            </button>
                        </div>
                    )}
                </div>

                {showAdvanced && (
                    <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className="space-y-3"
                    >
                        <div>
                            <label htmlFor="txLimit" className="block text-sm font-medium text-gray-300 mb-2">
                                Transaction Limit
                            </label>
                            <input
                                type="number"
                                id="txLimit"
                                value={txLimit}
                                onChange={handleTxLimitChange}
                                min="1"
                                max="1000"
                                className="w-full px-3 py-2 bg-gray-700/50 border border-gray-600/50 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                disabled={isLoading}
                            />
                            <p className="text-xs text-gray-400 mt-1">
                                Maximum number of transactions to fetch (1-1000)
                            </p>
                        </div>
                    </motion.div>
                )}

                <motion.button
                    type="submit"
                    disabled={!input.trim() || isLoading}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    className={`w-full flex items-center justify-center space-x-2 px-6 py-3 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors font-medium ${isClusterMode
                        ? 'bg-red-600 text-white hover:bg-red-700'
                        : 'bg-blue-600 text-white hover:bg-blue-700'
                        }`}
                >
                    {isLoading ? (
                        <>
                            <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                            <span>Analyzing...</span>
                        </>
                    ) : (
                        <>
                            {isClusterMode ? (
                                <>
                                    <Users className="w-5 h-5" />
                                    <span>Analyze Cluster</span>
                                </>
                            ) : (
                                <>
                                    <Search className="w-5 h-5" />
                                    <span>Fetch Transactions</span>
                                </>
                            )}
                        </>
                    )}
                </motion.button>
            </form>

            <div className="mt-4 space-y-2">
                <div className="p-3 bg-blue-900/20 border border-blue-500/30 rounded-lg">
                    <p className="text-sm text-blue-300">
                        <strong>Single Mode:</strong> Analyze one Bitcoin address and visualize its transaction network.
                    </p>
                </div>

                <div className="p-3 bg-red-900/20 border border-red-500/30 rounded-lg">
                    <p className="text-sm text-red-300">
                        <strong>Cluster Mode:</strong> Enter multiple addresses (comma-separated) to identify shared connections.
                        Addresses with 2+ suspect connections will be highlighted as high-probability links.
                    </p>
                </div>
            </div>
        </div>
    );
};

export default AddressInput;
