'use client';
import React, { useState, useEffect, useCallback, useRef } from 'react';
import blockchainService from '../utils/blockchainAPI';
import toast from 'react-hot-toast';

const useMempoolMonitor = (addresses: string[] = [], enabled = false) => {
    const [mempoolActivity, setMempoolActivity] = useState<Record<string, unknown> | null>(null);
    const [isMonitoring, setIsMonitoring] = useState(false);
    const [lastCheck, setLastCheck] = useState<number | null>(null);
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const previousActivityRef = useRef(new Set<string>());

    const checkMempool = useCallback(async () => {
        if (!addresses || addresses.length === 0) {
            return;
        }

        try {
            const result = await blockchainService.monitorMempoolActivity(addresses) as Record<string, unknown>;

            if (result.success && (result.active_addresses as number) > 0) {
                setMempoolActivity(result);
                setLastCheck(Date.now());

                const activity = result.activity as Record<string, unknown[]>;
                const currentActivitySet = new Set(Object.keys(activity));
                const newAddresses: string[] = [];

                currentActivitySet.forEach(address => {
                    if (!previousActivityRef.current.has(address)) {
                        newAddresses.push(address);
                    }
                });

                if (newAddresses.length > 0) {
                    newAddresses.forEach(address => {
                        const activityCount = activity[address]?.length || 0;
                        toast.custom((t) => (
                            <div className={`${t.visible ? 'animate-enter' : 'animate-leave'} max-w-md w-full bg-gradient-to-r from-red-600 to-orange-600 shadow-lg rounded-lg pointer-events-auto flex ring-1 ring-black ring-opacity-5`}>
                                <div className="flex-1 w-0 p-4">
                                    <div className="flex items-start">
                                        <div className="flex-shrink-0 pt-0.5">
                                            <div className="h-10 w-10 rounded-full bg-white/20 flex items-center justify-center">
                                                <svg className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                                                </svg>
                                            </div>
                                        </div>
                                        <div className="ml-3 flex-1">
                                            <p className="text-sm font-medium text-white">🔴 Live Movement Alert</p>
                                            <p className="mt-1 text-sm text-white/90">
                                                {address.substring(0, 12)}... has {activityCount} unconfirmed transaction{activityCount > 1 ? 's' : ''}
                                            </p>
                                        </div>
                                    </div>
                                </div>
                                <div className="flex border-l border-white/20">
                                    <button
                                        onClick={() => toast.dismiss(t.id)}
                                        className="w-full border border-transparent rounded-none rounded-r-lg p-4 flex items-center justify-center text-sm font-medium text-white hover:bg-white/10 focus:outline-none"
                                    >
                                        Close
                                    </button>
                                </div>
                            </div>
                        ), {
                            duration: 10000,
                            position: 'top-right',
                        });
                    });
                }

                previousActivityRef.current = currentActivitySet;
            } else {
                setMempoolActivity(null);
                setLastCheck(Date.now());
            }
        } catch (error) {
            console.error('Mempool check failed:', error);
        }
    }, [addresses]);

    const startMonitoring = useCallback(() => {
        if (addresses.length === 0 || isMonitoring) {
            return;
        }

        setIsMonitoring(true);
        checkMempool();

        intervalRef.current = setInterval(() => {
            checkMempool();
        }, 30010);

        toast.success('Mempool monitoring started', {
            icon: '👁️',
            duration: 3001
        });
    }, [addresses, isMonitoring, checkMempool]);

    const stopMonitoring = useCallback(() => {
        if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
        }

        setIsMonitoring(false);
        setMempoolActivity(null);
        previousActivityRef.current = new Set();

        toast('Mempool monitoring stopped', {
            icon: '⏸️',
            duration: 2000
        });
    }, []);

    const refreshMempool = useCallback(async () => {
        toast.loading('Checking mempool...', { id: 'mempool-refresh' });
        await checkMempool();
        toast.success('Mempool checked', { id: 'mempool-refresh' });
    }, [checkMempool]);

    useEffect(() => {
        if (enabled && addresses.length > 0 && !isMonitoring) {
            startMonitoring();
        } else if (!enabled && isMonitoring) {
            stopMonitoring();
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [enabled, addresses.length]);

    useEffect(() => {
        return () => {
            if (intervalRef.current) {
                clearInterval(intervalRef.current);
            }
        };
    }, []);

    const getAddressActivity = useCallback((address: string) => {
        if (!mempoolActivity || !mempoolActivity.activity) {
            return null;
        }
        return (mempoolActivity.activity as Record<string, unknown>)[address] || null;
    }, [mempoolActivity]);

    const hasActivity = useCallback((address: string) => {
        return getAddressActivity(address) !== null;
    }, [getAddressActivity]);

    return {
        mempoolActivity,
        isMonitoring,
        lastCheck,
        activeAddressCount: (mempoolActivity?.active_addresses as number) || 0,
        monitoredAddressCount: addresses.length,
        startMonitoring,
        stopMonitoring,
        refreshMempool,
        getAddressActivity,
        hasActivity
    };
};

export default useMempoolMonitor;
