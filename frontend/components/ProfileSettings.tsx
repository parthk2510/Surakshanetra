"use client";
import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Lock, Save, Users, UserPlus, Key, Shield, Eye, EyeOff, RefreshCw, Trash2, Activity } from 'lucide-react';
import apiService from '../utils/api';
import toast from 'react-hot-toast';
import structuredLogger from '../utils/structuredLogger';
import usePermissions from '../hooks/usePermissions';

const ROLES = ['admin', 'investigator', 'analyst', 'viewer'];

const csrf = () => document.cookie.match(/(^|;)\s*csrf_access_token\s*=\s*([^;]+)/)?.[2] || '';

const PasswordInput = ({ label, value, onChange, required }) => {
    const [show, setShow] = useState(false);
    return (
        <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">{label}</label>
            <div className="relative">
                <input
                    type={show ? 'text' : 'password'}
                    value={value}
                    onChange={onChange}
                    required={required}
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 pr-10 text-white focus:outline-none focus:border-blue-500 transition-colors"
                />
                <button
                    type="button"
                    onClick={() => setShow(!show)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-200"
                >
                    {show ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
            </div>
        </div>
    );
};

const ChangePasswordTab = ({ user }) => {
    const [oldPassword, setOldPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');

    const validatePassword = (p) => {
        if (!p) return 'Password is required';
        if (p.length < 8) return 'At least 8 characters';
        if (!/[A-Z]/.test(p)) return 'Needs an uppercase letter';
        if (!/[a-z]/.test(p)) return 'Needs a lowercase letter';
        if (!/\d/.test(p)) return 'Needs a number';
        if (!/[!@#$%^&*(),.?":{}|<>]/.test(p)) return 'Needs a special character';
        return '';
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        if (newPassword !== confirmPassword) { setError('Passwords do not match'); return; }
        const ve = validatePassword(newPassword);
        if (ve) { setError(ve); return; }
        setIsLoading(true);
        try {
            const response = await apiService.put('/api/auth/password-change', {
                old_password: oldPassword,
                new_password: newPassword,
            });
            if (response.success) {
                toast.success('Password updated successfully');
                setOldPassword(''); setNewPassword(''); setConfirmPassword('');
            } else {
                setError(response.error || 'Failed to update password');
            }
        } catch (err) {
            structuredLogger.error('profile.update_error', err.message, { error: err });
            setError(err.message || 'An error occurred');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <form onSubmit={handleSubmit} className="space-y-4">
            {error && <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">{error}</div>}
            <PasswordInput label="Current Password" value={oldPassword} onChange={e => setOldPassword(e.target.value)} required />
            <PasswordInput label="New Password" value={newPassword} onChange={e => setNewPassword(e.target.value)} required />
            <PasswordInput label="Confirm New Password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} required />
            <p className="text-xs text-gray-500">Min 8 chars · uppercase · lowercase · number · special character</p>
            <button type="submit" disabled={isLoading} className="w-full mt-2 bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 rounded-lg transition-colors flex justify-center items-center gap-2 disabled:opacity-50">
                {isLoading ? <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <><Save size={16} /> Update Password</>}
            </button>
        </form>
    );
};

const AdminUsersTab = () => {
    const [users, setUsers] = useState([]);
    const [loading, setLoading] = useState(false);
    const [showCreate, setShowCreate] = useState(false);
    const [resetUserId, setResetUserId] = useState(null);
    const [resetPassword, setResetPassword] = useState('');
    const [createForm, setCreateForm] = useState({ username: '', email: '', password: '', role: 'analyst' });
    const [createError, setCreateError] = useState('');
    const [resetError, setResetError] = useState('');

    const loadUsers = async () => {
        setLoading(true);
        try {
            const data = await apiService.get('/api/auth/users');
            if (data.success) setUsers(data.users);
        } catch (err) {
            toast.error('Failed to load users');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { loadUsers(); }, []);

    const handleCreateUser = async (e) => {
        e.preventDefault();
        setCreateError('');
        try {
            const response = await apiService.post('/api/users/create', createForm);
            if (response.success) {
                toast.success(`User '${createForm.username}' created`);
                setShowCreate(false);
                setCreateForm({ username: '', email: '', password: '', role: 'analyst' });
                loadUsers();
            } else {
                setCreateError(response.error || response.detail || 'Failed to create user');
            }
        } catch (err) {
            setCreateError(err.response?.data?.detail || err.message || 'Failed to create user');
        }
    };

    const handleResetPassword = async (e) => {
        e.preventDefault();
        setResetError('');
        try {
            const response = await apiService.post(`/api/users/${resetUserId}/reset-password`, { new_password: resetPassword });
            if (response.success) {
                toast.success(response.message);
                setResetUserId(null);
                setResetPassword('');
            } else {
                setResetError(response.error || response.detail || 'Failed to reset password');
            }
        } catch (err) {
            setResetError(err.response?.data?.detail || err.message || 'Failed to reset password');
        }
    };

    const handleToggleActive = async (userId, currentActive) => {
        try {
            await apiService.put(`/api/auth/users/${userId}`, { is_active: !currentActive });
            toast.success(`User ${currentActive ? 'deactivated' : 'activated'}`);
            loadUsers();
        } catch {
            toast.error('Failed to update user');
        }
    };

    const handleRoleChange = async (userId, newRole) => {
        try {
            await apiService.post('/api/users/assign-role', { user_id: userId, role: newRole });
            toast.success('Role updated');
            loadUsers();
        } catch (err) {
            toast.error(err.response?.data?.detail || 'Failed to update role');
        }
    };

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <span className="text-sm text-gray-400">{users.length} user{users.length !== 1 ? 's' : ''}</span>
                <button
                    onClick={() => setShowCreate(!showCreate)}
                    className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg transition-colors"
                >
                    <UserPlus size={14} /> New User
                </button>
            </div>

            {showCreate && (
                <form onSubmit={handleCreateUser} className="p-4 bg-gray-800 rounded-lg border border-gray-700 space-y-3">
                    <p className="text-sm font-medium text-white">Create User</p>
                    {createError && <div className="text-red-400 text-xs p-2 bg-red-500/10 rounded">{createError}</div>}
                    <input
                        type="text" placeholder="Username" required
                        value={createForm.username} onChange={e => setCreateForm({ ...createForm, username: e.target.value })}
                        className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                    />
                    <input
                        type="email" placeholder="Email" required
                        value={createForm.email} onChange={e => setCreateForm({ ...createForm, email: e.target.value })}
                        className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                    />
                    <input
                        type="password" placeholder="Password" required
                        value={createForm.password} onChange={e => setCreateForm({ ...createForm, password: e.target.value })}
                        className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                    />
                    <select
                        value={createForm.role} onChange={e => setCreateForm({ ...createForm, role: e.target.value })}
                        className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
                    >
                        {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                    </select>
                    <div className="flex gap-2">
                        <button type="submit" className="flex-1 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded transition-colors">Create</button>
                        <button type="button" onClick={() => setShowCreate(false)} className="flex-1 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 text-sm rounded transition-colors">Cancel</button>
                    </div>
                </form>
            )}

            {resetUserId && (
                <form onSubmit={handleResetPassword} className="p-4 bg-gray-800 rounded-lg border border-yellow-700/50 space-y-3">
                    <p className="text-sm font-medium text-yellow-400">Reset Password — User #{resetUserId}</p>
                    {resetError && <div className="text-red-400 text-xs p-2 bg-red-500/10 rounded">{resetError}</div>}
                    <PasswordInput label="New Password" value={resetPassword} onChange={e => setResetPassword(e.target.value)} required />
                    <div className="flex gap-2">
                        <button type="submit" className="flex-1 py-2 bg-yellow-600 hover:bg-yellow-700 text-white text-sm rounded transition-colors">Set Password</button>
                        <button type="button" onClick={() => { setResetUserId(null); setResetPassword(''); setResetError(''); }} className="flex-1 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 text-sm rounded transition-colors">Cancel</button>
                    </div>
                </form>
            )}

            {loading ? (
                <div className="flex justify-center py-6"><div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>
            ) : (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                    {users.map(u => (
                        <div key={u.id} className="flex items-center gap-3 p-3 bg-gray-800 rounded-lg border border-gray-700">
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                    <span className="text-sm font-medium text-white truncate">{u.username}</span>
                                    {!u.is_active && <span className="text-xs px-1.5 py-0.5 bg-red-500/20 text-red-400 rounded">disabled</span>}
                                </div>
                                <p className="text-xs text-gray-500 truncate">{u.email}</p>
                            </div>
                            <select
                                value={u.role}
                                onChange={e => handleRoleChange(u.id, e.target.value)}
                                className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-xs text-white focus:outline-none"
                            >
                                {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                            </select>
                            <button
                                onClick={() => setResetUserId(u.id)}
                                title="Reset password"
                                className="p-1.5 hover:bg-yellow-500/20 rounded text-yellow-400 hover:text-yellow-300 transition-colors"
                            >
                                <Key size={14} />
                            </button>
                            <button
                                onClick={() => handleToggleActive(u.id, u.is_active)}
                                title={u.is_active ? 'Deactivate' : 'Activate'}
                                className={`p-1.5 rounded transition-colors ${u.is_active ? 'hover:bg-red-500/20 text-red-400 hover:text-red-300' : 'hover:bg-green-500/20 text-green-400 hover:text-green-300'}`}
                            >
                                <Shield size={14} />
                            </button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

const REVOCABLE_ROLES = ['investigator', 'analyst', 'observer', 'viewer'];

const ActiveSessionsTab = () => {
    const [sessions, setSessions] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);
    const [revoking, setRevoking] = useState<string | null>(null);

    const fetchSessions = async () => {
        setLoading(true);
        try {
            const r = await fetch('/api/auth/sessions', { credentials: 'include', headers: { 'X-CSRF-TOKEN': csrf() } });
            if (!r.ok) throw new Error(`Failed to fetch sessions: ${r.status}`);
            const d = await r.json();
            setSessions(d.sessions || []);
        } catch (e: any) {
            structuredLogger.error('sessions.fetch_error', e.message, { error: e });
            toast.error('Failed to load sessions');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchSessions(); }, []);

    const handleRevoke = async (sessionToken: string) => {
        if (!confirm('Revoke this session? The user will be logged out immediately.')) return;
        setRevoking(sessionToken);
        try {
            const r = await fetch('/api/auth/revoke-session', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json', 'X-CSRF-TOKEN': csrf() },
                body: JSON.stringify({ session_token: sessionToken }),
            });
            const d = await r.json();
            if (!r.ok) throw new Error(d.error || 'Failed to revoke');
            toast.success('Session revoked — user will be logged out');
            fetchSessions();
        } catch (e: any) {
            structuredLogger.error('sessions.revoke_error', e.message, { error: e });
            toast.error(e.message || 'Failed to revoke session');
        } finally {
            setRevoking(null);
        }
    };

    const handleRevokeByRole = async (role: string) => {
        const targets = sessions.filter(s => s.role === role || s.username?.includes(role));
        if (targets.length === 0) { toast('No active sessions for that role'); return; }
        if (!confirm(`Revoke all ${targets.length} active ${role} session(s)?`)) return;
        for (const s of targets) {
            await handleRevoke(s.session_token);
        }
    };

    const groupedByRole = sessions.reduce((acc, s) => {
        const role = s.role || 'unknown';
        if (!acc[role]) acc[role] = [];
        acc[role].push(s);
        return acc;
    }, {} as Record<string, any[]>);

    return (
        <div className="space-y-3">
            <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-gray-400">{sessions.length} active session{sessions.length !== 1 ? 's' : ''}</span>
                <button onClick={fetchSessions} disabled={loading} className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200 disabled:opacity-50">
                    <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                    Refresh
                </button>
            </div>

            {/* Bulk revoke by role */}
            {REVOCABLE_ROLES.some(r => groupedByRole[r]?.length > 0) && (
                <div className="p-3 bg-gray-800/50 rounded-lg border border-gray-700 space-y-2">
                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Revoke All Sessions by Role</p>
                    <div className="flex flex-wrap gap-2">
                        {REVOCABLE_ROLES.filter(r => groupedByRole[r]?.length > 0).map(role => (
                            <button
                                key={role}
                                onClick={() => handleRevokeByRole(role)}
                                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-400 bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 rounded-lg transition-colors"
                            >
                                <Trash2 className="w-3 h-3" />
                                {role} ({groupedByRole[role].length})
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {loading ? (
                <div className="flex justify-center py-6"><div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>
            ) : (
                <>
                    {sessions.map(s => (
                        <div key={s.id} className="flex items-center justify-between p-3 bg-gray-800 rounded-lg border border-gray-700">
                            <div>
                                <p className="text-sm font-medium text-white">{s.username}</p>
                                <p className="text-xs text-gray-500">{s.ip_address} · {new Date(s.last_activity).toLocaleString()}</p>
                                {s.user_agent && <p className="text-xs text-gray-600 truncate max-w-[200px]">{s.user_agent.split(' ')[0]}</p>}
                            </div>
                            <button
                                onClick={() => handleRevoke(s.session_token || s.id)}
                                disabled={revoking === (s.session_token || s.id)}
                                className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 px-2 py-1 rounded hover:bg-red-900/20 transition-colors disabled:opacity-50"
                            >
                                {revoking === (s.session_token || s.id)
                                    ? <div className="w-3.5 h-3.5 border border-red-400 border-t-transparent rounded-full animate-spin" />
                                    : <Trash2 className="w-3.5 h-3.5" />}
                                Revoke
                            </button>
                        </div>
                    ))}
                    {sessions.length === 0 && (
                        <p className="text-center text-gray-500 text-sm py-8">No active sessions</p>
                    )}
                </>
            )}
        </div>
    );
};

const TABS = [
    { id: 'security', label: 'Security', icon: Lock, adminOnly: false },
    { id: 'users', label: 'Users', icon: Users, adminOnly: true },
    { id: 'sessions', label: 'Sessions', icon: Activity, adminOnly: true },
];

const ProfileSettings = ({ isOpen, onClose, user, initialTab = 'security' }) => {
    const { isAdmin } = usePermissions();
    const [activeTab, setActiveTab] = useState(initialTab);
    const visibleTabs = TABS.filter(t => !t.adminOnly || isAdmin);

    return (
        <AnimatePresence>
        {isOpen && (
            <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    className="bg-gray-900 border border-gray-800 rounded-xl w-full max-w-lg overflow-hidden shadow-2xl"
                >
                    <div className="flex items-center justify-between p-4 border-b border-gray-800 bg-gray-800/50">
                        <div className="flex items-center space-x-3">
                            <div className="p-2 bg-blue-500/20 rounded-lg">
                                <Lock className="w-5 h-5 text-blue-400" />
                            </div>
                            <div>
                                <h2 className="text-lg font-semibold text-white">Profile Settings</h2>
                                <p className="text-xs text-gray-400">{user?.username || 'User'} · {isAdmin ? 'Admin' : (localStorage.getItem('chainbreak_role') || user?.role || 'User')}</p>
                            </div>
                        </div>
                        <button onClick={onClose} className="p-2 hover:bg-gray-800 rounded-lg transition-colors text-gray-400 hover:text-white">
                            <X className="w-5 h-5" />
                        </button>
                    </div>

                    <div className="flex border-b border-gray-800">
                        {visibleTabs.map(tab => (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={`flex items-center gap-2 px-5 py-3 text-sm font-medium transition-colors ${activeTab === tab.id ? 'text-blue-400 border-b-2 border-blue-400' : 'text-gray-400 hover:text-gray-300'}`}
                            >
                                <tab.icon size={14} />
                                {tab.label}
                            </button>
                        ))}
                    </div>

                    <div className="p-6 max-h-[70vh] overflow-y-auto">
                        {activeTab === 'security' && <ChangePasswordTab user={user} />}
                        {activeTab === 'users' && isAdmin && <AdminUsersTab />}
                        {activeTab === 'sessions' && isAdmin && <ActiveSessionsTab />}
                    </div>
                </motion.div>
            </div>
        )}
        </AnimatePresence>
    );
};

export default ProfileSettings;
