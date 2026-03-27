// @ts-nocheck
"use client";
// src/components/AnomalyTimeline.js
// Timeline visualization for detected anomalies and risk events
import React, { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
    Clock, AlertTriangle, Shield, TrendingUp, Activity,
    ChevronLeft, ChevronRight, Filter, Calendar
} from 'lucide-react';
import { formatTimeAgo, formatTimestamp, formatBTC } from '../utils/formatters';

const AnomalyTimeline = ({
    leads = [],
    transactions = {},
    onEventClick,
    maxItems = 15
}) => {
    const [filter, setFilter] = useState('all');
    const [page, setPage] = useState(0);

    // Combine leads and high-value transactions into timeline events
    const timelineEvents = useMemo(() => {
        const events = [];

        // Add leads as events
        leads.forEach((lead, idx) => {
            events.push({
                id: `lead-${lead.id ?? idx}`,
                type: 'lead',
                priority: lead.priority,
                title: lead.type?.replace(/_/g, ' ').toUpperCase() || 'Lead',
                description: lead.description,
                timestamp: lead.timestamp || lead.createdAt,
                nodeId: lead.nodeId,
                data: lead
            });
        });

        // Add high-value or anomalous transactions
        Object.values(transactions).forEach(tx => {
            const totalValue = tx.total_input_value || tx.result || 0;
            const isHighValue = totalValue > 100000000000; // > 1000 BTC
            const isAnomalous = tx.is_anomalous || tx.fee > totalValue * 0.1; // High fee ratio

            if (isHighValue || isAnomalous) {
                events.push({
                    id: `tx-${tx.hash}`,
                    type: 'transaction',
                    priority: isAnomalous ? 'high' : 'medium',
                    title: isAnomalous ? 'Anomalous Transaction' : 'High-Value Transaction',
                    description: `${formatBTC(totalValue)} BTC moved`,
                    timestamp: tx.time ? tx.time * 1000 : null,
                    nodeId: tx.hash,
                    data: tx
                });
            }
        });

        // Sort by timestamp (newest first)
        return events
            .sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0))
            .filter(e => filter === 'all' || e.priority === filter);
    }, [leads, transactions, filter]);

    const paginatedEvents = timelineEvents.slice(page * maxItems, (page + 1) * maxItems);
    const totalPages = Math.ceil(timelineEvents.length / maxItems);

    const getEventColor = (priority, type) => {
        if (type === 'transaction') return 'border-blue-500 bg-blue-500/20';
        switch (priority) {
            case 'critical': return 'border-red-500 bg-red-500/20';
            case 'high': return 'border-orange-500 bg-orange-500/20';
            case 'medium': return 'border-yellow-500 bg-yellow-500/20';
            default: return 'border-green-500 bg-green-500/20';
        }
    };

    const getEventIcon = (type, priority) => {
        if (type === 'transaction') return TrendingUp;
        switch (priority) {
            case 'critical':
            case 'high':
                return AlertTriangle;
            case 'medium':
                return Activity;
            default:
                return Shield;
        }
    };

    if (timelineEvents.length === 0) {
        return (
            <div className="bg-gray-800/50 backdrop-blur-sm rounded-lg border border-gray-700/50 p-4">
                <h3 className="text-sm font-semibold text-white mb-4 flex items-center">
                    <Clock className="w-4 h-4 mr-2 text-blue-400" />
                    Anomaly Timeline
                </h3>
                <div className="text-center py-6 text-gray-500">
                    <Clock className="w-8 h-8 mx-auto mb-2 text-gray-600" />
                    <p className="text-sm">No anomalies detected yet</p>
                </div>
            </div>
        );
    }

    return (
        <div className="bg-gray-800/50 backdrop-blur-sm rounded-lg border border-gray-700/50 overflow-hidden">
            {/* Header */}
            <div className="px-4 py-3 bg-gray-700/30 border-b border-gray-700/50">
                <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-white flex items-center">
                        <Clock className="w-4 h-4 mr-2 text-blue-400" />
                        Anomaly Timeline
                        <span className="ml-2 px-2 py-0.5 bg-gray-600/50 rounded text-xs text-gray-400">
                            {timelineEvents.length} events
                        </span>
                    </h3>
                    <div className="flex items-center space-x-1">
                        <Filter className="w-3 h-3 text-gray-400" />
                        <select
                            value={filter}
                            onChange={(e) => { setFilter(e.target.value); setPage(0); }}
                            className="bg-gray-700/50 border border-gray-600/50 rounded text-xs text-gray-300 px-2 py-1"
                        >
                            <option value="all">All</option>
                            <option value="critical">Critical</option>
                            <option value="high">High</option>
                            <option value="medium">Medium</option>
                            <option value="low">Low</option>
                        </select>
                    </div>
                </div>
            </div>

            {/* Timeline */}
            <div className="p-4 max-h-80 overflow-y-auto">
                <div className="relative">
                    {/* Vertical line */}
                    <div className="absolute left-3 top-0 bottom-0 w-0.5 bg-gray-700" />

                    {/* Events */}
                    <div className="space-y-3">
                        {paginatedEvents.map((event, idx) => {
                            const EventIcon = getEventIcon(event.type, event.priority);
                            const colorClass = getEventColor(event.priority, event.type);

                            return (
                                <motion.div
                                    key={event.id}
                                    initial={{ opacity: 0, x: -20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ delay: idx * 0.05 }}
                                    className="relative pl-8"
                                >
                                    {/* Dot */}
                                    <div className={`absolute left-1 top-1 w-5 h-5 rounded-full border-2 flex items-center justify-center ${colorClass}`}>
                                        <EventIcon className="w-2.5 h-2.5 text-white" />
                                    </div>

                                    {/* Event Card */}
                                    <div
                                        className={`p-2.5 rounded border cursor-pointer transition-colors hover:bg-gray-700/30 ${colorClass.split(' ')[0]}/10 border-gray-700/50`}
                                        onClick={() => onEventClick?.(event)}
                                    >
                                        <div className="flex items-start justify-between">
                                            <div className="flex-1 min-w-0">
                                                <p className="text-xs font-semibold text-white mb-0.5">
                                                    {event.title}
                                                </p>
                                                <p className="text-xs text-gray-400 line-clamp-2">
                                                    {event.description}
                                                </p>
                                            </div>
                                            <span className={`px-1.5 py-0.5 rounded text-xs font-medium ml-2 ${event.priority === 'critical' ? 'bg-red-500/30 text-red-400' :
                                                    event.priority === 'high' ? 'bg-orange-500/30 text-orange-400' :
                                                        event.priority === 'medium' ? 'bg-yellow-500/30 text-yellow-400' :
                                                            'bg-green-500/30 text-green-400'
                                                }`}>
                                                {event.priority?.toUpperCase()}
                                            </span>
                                        </div>
                                        {event.timestamp && (
                                            <p className="text-xs text-gray-500 mt-1 flex items-center">
                                                <Calendar className="w-3 h-3 mr-1" />
                                                {formatTimeAgo(event.timestamp)}
                                            </p>
                                        )}
                                    </div>
                                </motion.div>
                            );
                        })}
                    </div>
                </div>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
                <div className="px-4 py-2 bg-gray-700/30 border-t border-gray-700/50 flex items-center justify-between">
                    <button
                        onClick={() => setPage(Math.max(0, page - 1))}
                        disabled={page === 0}
                        className="p-1 rounded hover:bg-gray-600/50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        <ChevronLeft className="w-4 h-4 text-gray-400" />
                    </button>
                    <span className="text-xs text-gray-400">
                        Page {page + 1} of {totalPages}
                    </span>
                    <button
                        onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                        disabled={page >= totalPages - 1}
                        className="p-1 rounded hover:bg-gray-600/50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                        <ChevronRight className="w-4 h-4 text-gray-400" />
                    </button>
                </div>
            )}
        </div>
    );
};

export default AnomalyTimeline;
