"use client";
// frontend/src/components/CaseFileViewer.js
import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { FileText, Copy, Check, ChevronDown, ChevronRight } from 'lucide-react';

const CaseFileViewer = ({ caseFile }) => {
    const [copied, setCopied] = useState(false);
    const [expandedSections, setExpandedSections] = useState(new Set(['metadata']));

    const handleCopy = () => {
        navigator.clipboard.writeText(JSON.stringify(caseFile, null, 2));
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    const toggleSection = (section) => {
        const newExpanded = new Set(expandedSections);
        if (newExpanded.has(section)) {
            newExpanded.delete(section);
        } else {
            newExpanded.add(section);
        }
        setExpandedSections(newExpanded);
    };

    if (!caseFile) {
        return (
            <div className="bg-gray-800/50 backdrop-blur-sm rounded-lg border border-gray-700/50 p-6 text-center">
                <FileText className="w-12 h-12 text-gray-600 mx-auto mb-3" />
                <p className="text-sm text-gray-400">No case file loaded</p>
            </div>
        );
    }

    const sections = [
        { key: 'metadata', label: 'Metadata', data: caseFile.metadata },
        { key: 'nodes', label: 'Nodes', data: caseFile.nodes, count: Object.keys(caseFile.nodes).length },
        { key: 'edges', label: 'Edges', data: caseFile.edges, count: caseFile.edges.length },
        { key: 'transactions', label: 'Transactions', data: caseFile.transactions, count: Object.keys(caseFile.transactions).length },
        { key: 'blocks', label: 'Blocks', data: caseFile.blocks, count: Object.keys(caseFile.blocks).length },
        { key: 'globalContext', label: 'Global Context', data: caseFile.globalContext },
        { key: 'detectedCommunities', label: 'Communities', data: caseFile.detectedCommunities, count: Object.keys(caseFile.detectedCommunities).length },
        { key: 'investigativeLeads', label: 'Leads', data: caseFile.investigativeLeads, count: caseFile.investigativeLeads.length }
    ];

    return (
        <div className="bg-gray-800/50 backdrop-blur-sm rounded-lg border border-gray-700/50 overflow-hidden">
            {/* Header */}
            <div className="bg-gradient-to-r from-blue-900/30 to-purple-900/30 border-b border-blue-500/30 px-4 py-3">
                <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                        <FileText className="w-5 h-5 text-blue-400" />
                        <h3 className="text-sm font-bold text-white uppercase tracking-wide">
                            Case File JSON
                        </h3>
                    </div>
                    <button
                        onClick={handleCopy}
                        className="flex items-center space-x-1 px-2 py-1 bg-gray-700/50 hover:bg-gray-700 rounded text-xs text-gray-300 transition-colors"
                    >
                        {copied ? (
                            <>
                                <Check className="w-3 h-3" />
                                <span>Copied!</span>
                            </>
                        ) : (
                            <>
                                <Copy className="w-3 h-3" />
                                <span>Copy</span>
                            </>
                        )}
                    </button>
                </div>
            </div>

            {/* Case File Sections */}
            <div className="max-h-[600px] overflow-y-auto">
                {sections.map((section) => (
                    <div key={section.key} className="border-b border-gray-700/50 last:border-0">
                        <button
                            onClick={() => toggleSection(section.key)}
                            className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-700/30 transition-colors"
                        >
                            <div className="flex items-center space-x-2">
                                {expandedSections.has(section.key) ? (
                                    <ChevronDown className="w-4 h-4 text-gray-400" />
                                ) : (
                                    <ChevronRight className="w-4 h-4 text-gray-400" />
                                )}
                                <span className="text-sm font-medium text-gray-300">{section.label}</span>
                                {section.count !== undefined && (
                                    <span className="text-xs text-gray-500">({section.count})</span>
                                )}
                            </div>
                        </button>

                        {expandedSections.has(section.key) && (
                            <motion.div
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: 'auto', opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                className="px-4 pb-3"
                            >
                                <pre className="text-xs font-mono text-gray-400 bg-gray-900/50 p-3 rounded overflow-x-auto max-h-60">
                                    {JSON.stringify(section.data, null, 2)}
                                </pre>
                            </motion.div>
                        )}
                    </div>
                ))}
            </div>

            {/* Footer */}
            <div className="px-4 py-2 border-t border-gray-700/50 bg-gray-900/30">
                <p className="text-xs text-gray-500 font-mono">
                    Total Size: {(JSON.stringify(caseFile).length / 1024).toFixed(2)} KB
                </p>
            </div>
        </div>
    );
};

export default CaseFileViewer;
