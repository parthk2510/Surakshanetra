'use client';
import { useState, useEffect, useCallback } from 'react';
import structuredLogger from '../utils/structuredLogger';

const usePermissions = () => {
    const [role, setRole] = useState<string>('');
    const [permissions, setPermissions] = useState<string[]>([]);
    const [loading, setLoading] = useState<boolean>(true);

    const refresh = useCallback(async () => {
        try {
            const res = await fetch('/api/auth/me', { credentials: 'include' });
            if (!res.ok) {
                setRole('');
                setPermissions([]);
                return;
            }
            const data = await res.json();
            if (data?.success) {
                const serverRole = data.role ?? '';
                const serverPerms: string[] = Array.isArray(data.permissions) ? data.permissions : [];
                setRole(serverRole);
                setPermissions(serverPerms);
                // Keep localStorage in sync for display-only fields (username, etc.)
                // but authoritative role/permissions come from the server, not localStorage.
                localStorage.setItem('chainbreak_role', serverRole);
                localStorage.setItem('chainbreak_permissions', JSON.stringify(serverPerms));
            } else {
                setRole('');
                setPermissions([]);
            }
        } catch (err) {
            structuredLogger.error('permissions.fetch_error', 'Failed to fetch permissions from server', { err });
            // Fall back to localStorage ONLY as a cached hint — never as the source of truth.
            // The backend will enforce RBAC regardless.
            try {
                const cached = localStorage.getItem('chainbreak_role') ?? '';
                const cachedPerms: string[] = JSON.parse(localStorage.getItem('chainbreak_permissions') ?? '[]');
                setRole(cached);
                setPermissions(cachedPerms);
            } catch {
                setRole('');
                setPermissions([]);
            }
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        refresh();
    }, [refresh]);

    const hasPermission = (permission: string): boolean =>
        permissions.includes('*') || permissions.includes(permission);

    const isAdmin = role === 'admin' || permissions.includes('*');

    return { role, permissions, hasPermission, isAdmin, loading, refresh };
};

export default usePermissions;
