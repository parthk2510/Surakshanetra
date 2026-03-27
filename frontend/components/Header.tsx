import React from 'react';
import { motion } from 'framer-motion';
import {
  Bitcoin,
  Database,
  FileText,
  AlertTriangle,
  BarChart3,
  Settings,
  FileText as LogsIcon,
  Sun,
  Moon,
  Brain,
} from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import { useConfig } from '../context/ConfigContext';
import { Z } from '../styles/z-layers';

const Header = ({ backendMode, systemStatus, onShowLogs }) => {
  const { isDark, toggleTheme } = useTheme();
  const { toggleSettingsPanel } = useConfig();

  const getBackendStatusColor = () => {
    switch (backendMode) {
      case 'neo4j':
        return 'text-green-400 bg-green-400/10 border-green-400/20';
      case 'json':
        return 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20';
      default:
        return 'text-red-400 bg-red-400/10 border-red-400/20';
    }
  };

  const getBackendStatusIcon = () => {
    switch (backendMode) {
      case 'neo4j': return <Database className="w-4 h-4" />;
      case 'json': return <FileText className="w-4 h-4" />;
      default: return <AlertTriangle className="w-4 h-4" />;
    }
  };

  const getBackendStatusText = () => {
    switch (backendMode) {
      case 'neo4j': return 'Neo4j Database';
      case 'json': return 'JSON Backend';
      default: return 'Unknown Backend';
    }
  };

  return (
    <motion.header
      initial={{ y: -100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      className="fixed top-0 left-0 right-0 backdrop-blur-md border-b"
      style={{
        zIndex: Z.HEADER,
        background: 'var(--header-bg)',
        borderColor: 'var(--border)',
      }}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand */}
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-3">
              <Bitcoin className="w-8 h-8 text-blue-500" />
              <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
                SurakshaNetra
              </h1>
            </div>

            <div className="hidden md:flex items-center space-x-2">
              <BarChart3 className="w-4 h-4" style={{ color: 'var(--text-muted)' }} />
              <span className="text-sm" style={{ color: 'var(--text-muted)' }}>
                Blockchain Analysis
              </span>
            </div>

            {/* RGCN indicator */}
            <div className="hidden lg:flex items-center space-x-1.5 px-2 py-1 rounded-full text-xs font-medium border"
              style={{
                background: 'rgba(139,92,246,0.08)',
                borderColor: 'rgba(139,92,246,0.3)',
                color: '#a78bfa',
              }}
            >
              <Brain className="w-3 h-3" />
              <span>RGCN + Decision Engine</span>
            </div>
          </div>

          {/* Right controls */}
          <div className="flex items-center space-x-3">
            {/* Backend badge */}
            <div className={`flex items-center space-x-2 px-3 py-1.5 rounded-full border text-xs font-medium ${getBackendStatusColor()}`}>
              {getBackendStatusIcon()}
              <span className="hidden sm:inline">{getBackendStatusText()}</span>
            </div>

            {/* System status dot */}
            {systemStatus && (
              <div className="hidden sm:flex items-center space-x-2 text-xs">
                <div className={`w-2 h-2 rounded-full ${systemStatus.system_status === 'operational' ? 'bg-green-400' : 'bg-red-400'
                  }`} />
                <span style={{ color: 'var(--text-secondary)' }}>
                  {systemStatus.system_status === 'operational' ? 'Online' : 'Offline'}
                </span>
              </div>
            )}

            {/* Action buttons */}
            <div className="flex items-center space-x-1">
              {/* Theme toggle */}
              <motion.button
                whileTap={{ scale: 0.9 }}
                onClick={toggleTheme}
                className="p-2 rounded-lg transition-colors"
                style={{ color: 'var(--text-secondary)' }}
                title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
              >
                {isDark
                  ? <Sun className="w-5 h-5 text-yellow-400" />
                  : <Moon className="w-5 h-5 text-blue-500" />
                }
              </motion.button>

              {/* Logs */}
              <button
                onClick={onShowLogs}
                className="p-2 rounded-lg transition-colors"
                style={{ color: 'var(--text-secondary)' }}
                title="View Logs"
              >
                <LogsIcon className="w-5 h-5" />
              </button>

              {/* Settings */}
              {/* <button
                onClick={toggleSettingsPanel}
                className="p-2 rounded-lg transition-colors"
                style={{ color: 'var(--text-secondary)' }}
                title="Settings"
              >
                <Settings className="w-5 h-5" />
              </button> */}
            </div>
          </div>
        </div>
      </div>
    </motion.header>
  );
};

export default Header;
