"use client";
import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { AlertTriangle, Info, CheckCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import { Z } from '../styles/z-layers';

/**
 * GraphLegend Component
 * Displays a clear legend explaining the risk color coding system
 * for nodes in the graph visualization.
 */
const GraphLegend = ({ position = 'bottom-left', className = '' }) => {
  const [collapsed, setCollapsed] = useState(false);
  const { isDark } = useTheme();
  const panelBg    = isDark ? 'rgba(15,23,42,0.95)'     : 'rgba(255,255,255,0.97)';
  const panelBorder = isDark ? 'rgba(51,65,85,0.8)'     : 'rgba(226,232,240,0.9)';
  const headerColor = isDark ? '#f1f5f9'                : '#0f172a';
  const labelColor  = isDark ? '#94a3b8'                : '#475569';
  const descColor   = isDark ? '#64748b'                : '#94a3b8';

  const riskLevels = [
    {
      color: '#ef4444',
      label: 'Critical Risk',
      description: 'Score ≥ 80',
      icon: AlertTriangle,
      bg: 'rgba(239, 68, 68, 0.1)',
      border: 'rgba(239, 68, 68, 0.3)'
    },
    {
      color: '#f97316',
      label: 'High Risk',
      description: 'Score 60-79',
      icon: AlertTriangle,
      bg: 'rgba(249, 115, 22, 0.1)',
      border: 'rgba(249, 115, 22, 0.3)'
    },
    {
      color: '#eab308',
      label: 'Medium Risk',
      description: 'Score 40-59',
      icon: Info,
      bg: 'rgba(234, 179, 8, 0.1)',
      border: 'rgba(234, 179, 8, 0.3)'
    },
    {
      color: '#22c55e',
      label: 'Low Risk',
      description: 'Score 20-39',
      icon: CheckCircle,
      bg: 'rgba(34, 197, 94, 0.1)',
      border: 'rgba(34, 197, 94, 0.3)'
    },
    {
      color: '#3b82f6',
      label: 'Minimal Risk',
      description: 'Score < 20',
      icon: CheckCircle,
      bg: 'rgba(59, 130, 246, 0.1)',
      border: 'rgba(59, 130, 246, 0.3)'
    }
  ];

  const edgeInfo = [
    {
      thickness: 4,
      label: 'High Volume',
      description: '>10k transactions'
    },
    {
      thickness: 2,
      label: 'Medium Volume',
      description: '1k-10k transactions'
    },
    {
      thickness: 1,
      label: 'Low Volume',
      description: '<1k transactions'
    }
  ];

  const positionStyles = {
    'top-left': { top: '16px', left: '16px' },
    'top-right': { top: '16px', right: '16px' },
    'bottom-left': { bottom: '16px', left: '16px' },
    'bottom-right': { bottom: '16px', right: '16px' }
  };

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className={className}
      style={{
        position: 'absolute',
        ...positionStyles[position],
        background: panelBg,
        backdropFilter: 'blur(12px)',
        borderRadius: '12px',
        padding: '16px',
        border: `1px solid ${panelBorder}`,
        boxShadow: isDark ? '0 8px 32px rgba(0,0,0,0.4)' : '0 4px 16px rgba(0,0,0,0.10)',
        minWidth: '260px',
        maxWidth: '300px',
        zIndex: Z.GRAPH_LEGEND,
        pointerEvents: 'auto'
      }}
    >
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        marginBottom: collapsed ? 0 : '14px',
        paddingBottom: collapsed ? 0 : '12px',
        borderBottom: collapsed ? 'none' : '1px solid rgba(51, 65, 85, 0.6)',
        cursor: 'pointer',
        userSelect: 'none',
      }} onClick={() => setCollapsed(c => !c)}>
        <div style={{
          width: '8px',
          height: '8px',
          borderRadius: '50%',
          background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
          boxShadow: '0 0 8px rgba(59, 130, 246, 0.5)'
        }} />
        <h3 style={{
          fontSize: '13px',
          fontWeight: '700',
          color: headerColor,
          margin: 0,
          flex: 1,
          letterSpacing: '0.02em'
        }}>
          Graph Legend
        </h3>
        {collapsed ? <ChevronUp size={14} color="#94a3b8" /> : <ChevronDown size={14} color="#94a3b8" />}
      </div>

      {!collapsed && (
        <>
          <div style={{ marginBottom: '16px' }}>
            <div style={{
              fontSize: '11px',
              fontWeight: '600',
              color: labelColor,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              marginBottom: '10px'
            }}>
              Node Risk Levels
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {riskLevels.map((level, index) => {
                const Icon = level.icon;
                return (
                  <motion.div
                    key={level.label}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.05 }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      background: level.bg,
                      border: `1px solid ${level.border}`,
                      transition: 'all 0.2s'
                    }}
                  >
                    <div style={{
                      width: '12px',
                      height: '12px',
                      borderRadius: '50%',
                      background: level.color,
                      boxShadow: `0 0 8px ${level.color}50`,
                      flexShrink: 0
                    }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{
                        fontSize: '11px',
                        fontWeight: '600',
                        color: level.color,
                        marginBottom: '2px'
                      }}>
                        {level.label}
                      </div>
                      <div style={{ fontSize: '10px', color: descColor }}>
                        {level.description}
                      </div>
                    </div>
                    <Icon size={14} color={level.color} style={{ flexShrink: 0 }} />
                  </motion.div>
                );
              })}
            </div>
          </div>

          <div>
            <div style={{
              fontSize: '11px',
              fontWeight: '600',
              color: labelColor,
              textTransform: 'uppercase',
              letterSpacing: '0.08em',
              marginBottom: '10px'
            }}>
              Edge Weight
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {edgeInfo.map((edge, index) => (
                <motion.div
                  key={edge.label}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: (riskLevels.length + index) * 0.05 }}
                  style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '6px 10px' }}
                >
                  <div style={{
                    width: '32px',
                    height: `${edge.thickness}px`,
                    background: 'rgba(107, 114, 128, 0.6)',
                    borderRadius: '2px',
                    flexShrink: 0
                  }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '11px', fontWeight: '600', color: labelColor, marginBottom: '2px' }}>
                      {edge.label}
                    </div>
                    <div style={{ fontSize: '10px', color: descColor }}>
                      {edge.description}
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>

          <div style={{
            marginTop: '12px',
            paddingTop: '12px',
            borderTop: '1px solid rgba(51, 65, 85, 0.6)',
            fontSize: '10px',
            color: descColor,
            lineHeight: '1.4'
          }}>
            <Info size={10} style={{ display: 'inline', marginRight: '4px' }} />
            Node size increases with risk score. Hover for details.
          </div>
        </>
      )}
    </motion.div>
  );
};

export default GraphLegend;
