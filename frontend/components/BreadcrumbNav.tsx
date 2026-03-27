// src/components/BreadcrumbNav.js
// Clean breadcrumb navigation with proper back functionality
import React from 'react';
import { ChevronRight, Home, Network, FileText, Shield, Users, Edit2 } from 'lucide-react';
import forensicDataManager from '../core/ForensicDataManager';
import toast from 'react-hot-toast';

const BreadcrumbNav = ({
    caseId,
    currentView = 'dashboard',
    selectedNode = null,
    onNavigate,
    onClearSelection,
    onRenameCase
}) => {
    const handleChainBreakClick = () => {
        // Clear all selections and go back to main view
        if (onClearSelection) {
            onClearSelection();
        }
        // Optionally navigate to home
        if (onNavigate) {
            onNavigate('/');
        }
        toast.success('Returned to main dashboard');
    };

    const handleCaseRename = () => {
        if (onRenameCase) {
            onRenameCase();
        } else {
            // Default rename behavior
            forensicDataManager.promptCaseName().then(newName => {
                if (newName) {
                    toast.success(`Case renamed to: ${newName}`);
                }
            });
        }
    };

    const formatCaseLabel = (id) => {
        if (!id) return 'New Investigation';
        return id.replace('CASE-', '').replace('.json', '').replace(/-/g, ' ');
    };

    return (
        <nav className="flex items-center justify-between px-6 py-2 backdrop-blur-sm border-b" style={{ background: 'var(--header-bg)', borderColor: 'var(--border)' }}>
            <div className="flex items-center space-x-2 text-sm">
                {/* ChainBreak Logo/Home - Clickable to go back */}
                <button
                    onClick={handleChainBreakClick}
                    className="flex items-center space-x-2 px-3 py-1.5 rounded-lg text-emerald-400 hover:bg-emerald-500/10 transition-all group"
                >
                    <div className="w-6 h-6 bg-gradient-to-br from-emerald-400 to-blue-500 rounded-lg flex items-center justify-center">
                        <span className="text-white text-xs font-bold">CB</span>
                    </div>
                    <span className="font-semibold">SurakshaNetra</span>
                </button>

                <ChevronRight className="w-4 h-4" style={{ color: 'var(--text-muted)' }} />

                {/* Investigation Dashboard */}
                <button
                    onClick={() => {
                        if (selectedNode && onClearSelection) {
                            onClearSelection();
                        }
                    }}
                    className={`px-3 py-1.5 rounded-lg transition-all ${!selectedNode
                            ? 'text-blue-400 bg-blue-500/10'
                            : 'hover:text-white hover:bg-gray-700/50'
                        }`}
                    style={selectedNode ? { color: 'var(--text-muted)' } : {}}
                >
                    Investigation Dashboard
                </button>

                {/* Case Name with Edit */}
                {caseId && (
                    <>
                        <ChevronRight className="w-4 h-4" style={{color: 'var(--text-muted)'}} />
                        <div className="flex items-center space-x-1">
                            <span className="px-2 py-1 rounded text-xs font-medium" style={{ background: 'var(--surface-2)', color: 'var(--text-secondary)' }}>
                                {formatCaseLabel(caseId)}
                            </span>
                            <button
                                onClick={handleCaseRename}
                                className="p-1 hover:text-blue-400 hover:bg-blue-500/10 rounded transition-all"
                                style={{ color: 'var(--text-muted)' }}
                                title="Rename case"
                            >
                                <Edit2 className="w-3 h-3" />
                            </button>
                        </div>
                    </>
                )}

                {/* Selected Node */}
                {selectedNode && (
                    <>
                        <ChevronRight className="w-4 h-4" style={{ color: 'var(--text-muted)' }} />
                        <div className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg ${selectedNode.isMalicious
                                ? 'bg-red-500/10 text-red-400'
                                : 'bg-blue-500/10 text-blue-400'
                            }`}>
                            {selectedNode.isMalicious ? (
                                <Shield className="w-3.5 h-3.5" />
                            ) : selectedNode.type === 'transaction' ? (
                                <FileText className="w-3.5 h-3.5" />
                            ) : (
                                <Users className="w-3.5 h-3.5" />
                            )}
                            <span className="font-mono text-xs">
                                {selectedNode.type === 'transaction'
                                    ? `Tx: ${selectedNode.id?.substring(0, 12)}...`
                                    : `${selectedNode.id?.substring(0, 12)}...`
                                }
                            </span>
                        </div>
                    </>
                )}
            </div>
        </nav>
    );
};

export default BreadcrumbNav;
