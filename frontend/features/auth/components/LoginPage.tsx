// @ts-nocheck
import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Lock, User, Mail, AlertCircle, Eye, EyeOff, Shield, CheckCircle, XCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import structuredLogger from '../../../utils/structuredLogger';

const API_BASE = '';

const LoginPage = ({ onLoginSuccess }) => {
    const [isRegister, setIsRegister] = useState(false);
    const [showPassword, setShowPassword] = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [formData, setFormData] = useState({
        username: '',
        email: '',
        password: '',
        confirmPassword: ''
    });
    const [errors, setErrors] = useState({});
    const [fieldTouched, setFieldTouched] = useState({});
    const [networkError, setNetworkError] = useState('');

    // Validate username
    const validateUsername = (username) => {
        if (!username) return 'Username is required';
        if (username.length < 3) return 'Username must be at least 3 characters';
        if (username.length > 20) return 'Username must be less than 20 characters';
        if (!/^[a-zA-Z0-9_]+$/.test(username)) return 'Username can only contain letters, numbers, and underscores';
        return '';
    };

    // Validate email
    const validateEmail = (email) => {
        if (!email) return 'Email is required';
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) return 'Please enter a valid email address';
        return '';
    };

    // Validate password
    const validatePassword = (password) => {
        if (!password) return 'Password is required';
        if (password.length < 8) return 'Password must be at least 8 characters';
        if (password.length > 128) return 'Password is too long';
        if (!/[A-Z]/.test(password)) return 'Password must contain at least one uppercase letter';
        if (!/[a-z]/.test(password)) return 'Password must contain at least one lowercase letter';
        if (!/\d/.test(password)) return 'Password must contain at least one number';
        if (!/[!@#$%^&*(),.?":{}|<>]/.test(password)) return 'Password must contain at least one special character';
        return '';
    };

    // Validate confirm password
    const validateConfirmPassword = (confirmPassword, password) => {
        if (!confirmPassword) return 'Please confirm your password';
        if (confirmPassword !== password) return 'Passwords do not match';
        return '';
    };

    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData({ ...formData, [name]: value });

        // Clear error for this field
        if (errors[name]) {
            setErrors({ ...errors, [name]: '' });
        }
        setNetworkError('');
    };

    const handleBlur = (e) => {
        const { name, value } = e.target;
        setFieldTouched({ ...fieldTouched, [name]: true });

        let error = '';
        switch (name) {
            case 'username':
                error = validateUsername(value);
                break;
            case 'email':
                if (isRegister) error = validateEmail(value);
                break;
            case 'password':
                error = validatePassword(value);
                break;
            case 'confirmPassword':
                if (isRegister) error = validateConfirmPassword(value, formData.password);
                break;
            default:
                break;
        }

        if (error) {
            setErrors({ ...errors, [name]: error });
        } else {
            const newErrors = { ...errors };
            delete newErrors[name];
            setErrors(newErrors);
        }
    };

    const validateForm = () => {
        const newErrors = {};

        const usernameError = validateUsername(formData.username);
        if (usernameError) newErrors.username = usernameError;

        if (isRegister) {
            const emailError = validateEmail(formData.email);
            if (emailError) newErrors.email = emailError;
        }

        const passwordError = validatePassword(formData.password);
        if (passwordError) newErrors.password = passwordError;

        if (isRegister) {
            const confirmPasswordError = validateConfirmPassword(formData.confirmPassword, formData.password);
            if (confirmPasswordError) newErrors.confirmPassword = confirmPasswordError;
        }

        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setNetworkError('');
        setErrors({});

        if (!validateForm()) {
            structuredLogger.warn('auth.validation_failed', 'Local form validation errors', { payload: errors });
            toast.error('Please fix the errors in the form');
            return;
        }

        setLoading(true);
        structuredLogger.info(`auth.${isRegister ? 'register' : 'login'}_attempt`, `Attempting authentication for username: ${formData.username}`);

        try {
            const endpoint = isRegister ? '/api/auth/register' : '/api/auth/login';
            const body = isRegister ? formData : {
                username: formData.username,
                password: formData.password
            };

            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout

            const startTime = performance.now();
            const response = await fetch(`${API_BASE}${endpoint}`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
                signal: controller.signal
            });
            const latency = Math.round(performance.now() - startTime);

            clearTimeout(timeoutId);
            structuredLogger.apiRequest(endpoint, 'POST', response.status, latency);

            let data;
            try {
                data = await response.json();
            } catch (parseError) {
                structuredLogger.error('auth.parse_error', 'Invalid JSON from server', { error: parseError });
                throw new Error('Invalid response from server');
            }

            if (!response.ok) {
                structuredLogger.warn(`auth.${isRegister ? 'register' : 'login'}_failed`, `Server rejected request with status ${response.status}`, { payload: data });
                // Handle specific error codes
                let errorMessage = data.error || 'Authentication failed';

                if (response.status === 401) {
                    errorMessage = 'Invalid username or password';
                } else if (response.status === 409) {
                    errorMessage = data.error || 'Username or email already exists';
                } else if (response.status === 400) {
                    errorMessage = data.error || 'Invalid request. Please check your input.';
                } else if (response.status === 403) {
                    errorMessage = 'Account is disabled. Please contact support.';
                } else if (response.status >= 500) {
                    errorMessage = 'Server error. Please try again later.';
                }

                throw new Error(errorMessage);
            }

            if (data.user) {
                localStorage.setItem('chainbreak_user', JSON.stringify(data.user));
            }
            if (data.permissions) {
                localStorage.setItem('chainbreak_permissions', JSON.stringify(data.permissions));
            }
            if (data.role) {
                localStorage.setItem('chainbreak_role', data.role);
            }

            toast.success(isRegister ? 'Account created successfully!' : 'Welcome back!');
            structuredLogger.info(`auth.${isRegister ? 'register' : 'login'}_success`, 'Authentication completed');

            onLoginSuccess(data.user, true);

        } catch (err) {
            structuredLogger.error(`auth.${isRegister ? 'register' : 'login'}_error`, err.message, { error: err });
            let errorMessage = 'An unexpected error occurred';

            if (err.name === 'AbortError') {
                errorMessage = 'Request timed out. Please check your connection and try again.';
            } else if (err.message.includes('Failed to fetch') || err.message.includes('NetworkError')) {
                errorMessage = 'Network error. Please check your connection and ensure the server is running.';
                setNetworkError(errorMessage);
            } else {
                errorMessage = err.message || 'Authentication failed';
            }

            setNetworkError(errorMessage);
            toast.error(errorMessage);
        } finally {
            setLoading(false);
        }
    };

    // Clear errors when switching between login/register
    useEffect(() => {
        setErrors({});
        setNetworkError('');
        setFieldTouched({});
    }, [isRegister]);

    return (
        <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 flex items-center justify-center p-4">
            <div className="absolute inset-0 overflow-hidden">
                <div className="absolute -top-40 -right-40 w-80 h-80 bg-blue-500/10 rounded-full blur-3xl" />
                <div className="absolute -bottom-40 -left-40 w-80 h-80 bg-purple-500/10 rounded-full blur-3xl" />
            </div>

            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
                className="relative w-full max-w-md"
            >
                <div className="bg-gray-800/80 backdrop-blur-xl rounded-2xl border border-gray-700/50 shadow-2xl overflow-hidden">
                    <div className="p-8">
                        <div className="flex justify-center mb-6">
                            <div className="p-4 bg-gradient-to-br from-blue-500 to-purple-600 rounded-2xl">
                                <Shield className="w-10 h-10 text-white" />
                            </div>
                        </div>

                        <h1 className="text-2xl font-bold text-white text-center mb-2">
                            SurakshaNetra
                        </h1>
                        <p className="text-gray-400 text-center mb-8">
                            {isRegister ? 'Create your account' : 'Forensic Intelligence Platform'}
                        </p>

                        {networkError && (
                            <motion.div
                                initial={{ opacity: 0, y: -10 }}
                                animate={{ opacity: 1, y: 0 }}
                                className="mb-6 p-4 bg-red-500/10 border border-red-500/50 rounded-lg flex items-start space-x-3"
                            >
                                <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                                <div className="flex-1">
                                    <span className="text-red-400 text-sm font-medium block">{networkError}</span>
                                    {networkError.includes('Network error') && (
                                        <span className="text-red-300 text-xs mt-1 block">
                                            Server URL: {API_BASE}
                                        </span>
                                    )}
                                </div>
                            </motion.div>
                        )}

                        <form onSubmit={handleSubmit} className="space-y-5">
                            <div>
                                <label className="block text-sm font-medium text-gray-300 mb-2">
                                    Username
                                </label>
                                <div className="relative">
                                    <User className={`absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 ${errors.username ? 'text-red-400' : 'text-gray-400'}`} />
                                    <input
                                        type="text"
                                        name="username"
                                        value={formData.username}
                                        onChange={handleChange}
                                        onBlur={handleBlur}
                                        required
                                        className={`w-full pl-11 pr-4 py-3 bg-gray-700/50 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 transition-all ${errors.username
                                            ? 'border-red-500 focus:ring-red-500 focus:border-red-500'
                                            : 'border-gray-600 focus:ring-blue-500 focus:border-transparent'
                                            }`}
                                        placeholder="Enter username"
                                    />
                                    {fieldTouched.username && !errors.username && formData.username && (
                                        <CheckCircle className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 text-green-400" />
                                    )}
                                </div>
                                {errors.username && (
                                    <motion.p
                                        initial={{ opacity: 0, y: -5 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        className="mt-1 text-xs text-red-400 flex items-center space-x-1"
                                    >
                                        <XCircle className="w-3 h-3" />
                                        <span>{errors.username}</span>
                                    </motion.p>
                                )}
                            </div>

                            {isRegister && (
                                <motion.div
                                    initial={{ opacity: 0, height: 0 }}
                                    animate={{ opacity: 1, height: 'auto' }}
                                    exit={{ opacity: 0, height: 0 }}
                                >
                                    <label className="block text-sm font-medium text-gray-300 mb-2">
                                        Email
                                    </label>
                                    <div className="relative">
                                        <Mail className={`absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 ${errors.email ? 'text-red-400' : 'text-gray-400'}`} />
                                        <input
                                            type="email"
                                            name="email"
                                            value={formData.email}
                                            onChange={handleChange}
                                            onBlur={handleBlur}
                                            required={isRegister}
                                            className={`w-full pl-11 pr-4 py-3 bg-gray-700/50 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 transition-all ${errors.email
                                                ? 'border-red-500 focus:ring-red-500 focus:border-red-500'
                                                : 'border-gray-600 focus:ring-blue-500 focus:border-transparent'
                                                }`}
                                            placeholder="Enter email"
                                        />
                                        {fieldTouched.email && !errors.email && formData.email && (
                                            <CheckCircle className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 text-green-400" />
                                        )}
                                    </div>
                                    {errors.email && (
                                        <motion.p
                                            initial={{ opacity: 0, y: -5 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            className="mt-1 text-xs text-red-400 flex items-center space-x-1"
                                        >
                                            <XCircle className="w-3 h-3" />
                                            <span>{errors.email}</span>
                                        </motion.p>
                                    )}
                                </motion.div>
                            )}

                            <div>
                                <label className="block text-sm font-medium text-gray-300 mb-2">
                                    Password
                                </label>
                                <div className="relative">
                                    <Lock className={`absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 ${errors.password ? 'text-red-400' : 'text-gray-400'}`} />
                                    <input
                                        type={showPassword ? 'text' : 'password'}
                                        name="password"
                                        value={formData.password}
                                        onChange={handleChange}
                                        onBlur={handleBlur}
                                        required
                                        className={`w-full pl-11 pr-12 py-3 bg-gray-700/50 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 transition-all ${errors.password
                                            ? 'border-red-500 focus:ring-red-500 focus:border-red-500'
                                            : 'border-gray-600 focus:ring-blue-500 focus:border-transparent'
                                            }`}
                                        placeholder="Enter password"
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowPassword(!showPassword)}
                                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-300"
                                    >
                                        {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                                    </button>
                                </div>
                                {errors.password && (
                                    <motion.p
                                        initial={{ opacity: 0, y: -5 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        className="mt-1 text-xs text-red-400 flex items-center space-x-1"
                                    >
                                        <XCircle className="w-3 h-3" />
                                        <span>{errors.password}</span>
                                    </motion.p>
                                )}
                                {!errors.password && formData.password && (
                                    <p className="mt-1 text-xs text-gray-500">
                                        {formData.password.length >= 8 ? '✓ Password strength: Good' : `Password strength: ${formData.password.length < 6 ? 'Weak' : 'Fair'}`}
                                    </p>
                                )}
                            </div>

                            {isRegister && (
                                <motion.div
                                    initial={{ opacity: 0, height: 0 }}
                                    animate={{ opacity: 1, height: 'auto' }}
                                    exit={{ opacity: 0, height: 0 }}
                                >
                                    <label className="block text-sm font-medium text-gray-300 mb-2">
                                        Confirm Password
                                    </label>
                                    <div className="relative">
                                        <Lock className={`absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 ${errors.confirmPassword ? 'text-red-400' : 'text-gray-400'}`} />
                                        <input
                                            type={showConfirmPassword ? 'text' : 'password'}
                                            name="confirmPassword"
                                            value={formData.confirmPassword}
                                            onChange={handleChange}
                                            onBlur={handleBlur}
                                            required={isRegister}
                                            className={`w-full pl-11 pr-12 py-3 bg-gray-700/50 border rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 transition-all ${errors.confirmPassword
                                                ? 'border-red-500 focus:ring-red-500 focus:border-red-500'
                                                : 'border-gray-600 focus:ring-blue-500 focus:border-transparent'
                                                }`}
                                            placeholder="Confirm password"
                                        />
                                        <button
                                            type="button"
                                            onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                                            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-300"
                                        >
                                            {showConfirmPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                                        </button>
                                        {fieldTouched.confirmPassword && !errors.confirmPassword && formData.confirmPassword && formData.confirmPassword === formData.password && (
                                            <CheckCircle className="absolute right-10 top-1/2 -translate-y-1/2 w-5 h-5 text-green-400" />
                                        )}
                                    </div>
                                    {errors.confirmPassword && (
                                        <motion.p
                                            initial={{ opacity: 0, y: -5 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            className="mt-1 text-xs text-red-400 flex items-center space-x-1"
                                        >
                                            <XCircle className="w-3 h-3" />
                                            <span>{errors.confirmPassword}</span>
                                        </motion.p>
                                    )}
                                    {!errors.confirmPassword && formData.confirmPassword && formData.confirmPassword === formData.password && (
                                        <p className="mt-1 text-xs text-green-400 flex items-center space-x-1">
                                            <CheckCircle className="w-3 h-3" />
                                            <span>Passwords match</span>
                                        </p>
                                    )}
                                </motion.div>
                            )}

                            <button
                                type="submit"
                                disabled={loading}
                                className="w-full py-3 bg-gradient-to-r from-blue-600 to-purple-600 text-white font-semibold rounded-lg hover:from-blue-700 hover:to-purple-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-gray-800 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {loading ? (
                                    <span className="flex items-center justify-center space-x-2">
                                        <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                        <span>Processing...</span>
                                    </span>
                                ) : (
                                    isRegister ? 'Create Account' : 'Sign In'
                                )}
                            </button>
                        </form>

                        <div className="mt-6 text-center">
                            <button
                                onClick={() => {
                                    setIsRegister(!isRegister);
                                    setErrors({});
                                    setNetworkError('');
                                    setFieldTouched({});
                                }}
                                className="text-blue-400 hover:text-blue-300 text-sm transition-colors"
                            >
                                {isRegister
                                    ? 'Already have an account? Sign in'
                                    : "Don't have an account? Register"}
                            </button>
                        </div>
                    </div>

                    <div className="px-8 py-4 bg-gray-900/50 border-t border-gray-700/50">
                        <p className="text-xs text-gray-500 text-center">
                            Protected by enterprise-grade security
                        </p>
                    </div>
                </div>
            </motion.div>
        </div>
    );
};

export default LoginPage;
