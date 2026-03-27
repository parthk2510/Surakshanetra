"use client";
// frontend/src/components/ErrorBoundary.js
// ============================================================================
// ERROR BOUNDARY - Graceful Error Handling for React Components
// ============================================================================
import React, { Component } from 'react';
import { AlertTriangle, RefreshCw, Home, Bug, ChevronDown, ChevronUp } from 'lucide-react';

interface ErrorBoundaryProps {
    children?: React.ReactNode;
    onError?: (error: Error, info: React.ErrorInfo) => void;
    onReset?: () => void;
    fallbackTitle?: string;
    fallbackDescription?: string;
    showResetButton?: boolean;
    showHomeButton?: boolean;
    showErrorDetails?: boolean;
    variant?: 'default' | 'minimal' | 'graph';
}

interface ErrorBoundaryState {
    hasError: boolean;
    error: Error | null;
    errorInfo: React.ErrorInfo | null;
    showDetails: boolean;
}

/**
 * ErrorBoundary - Catches JavaScript errors in child components
 * and displays a fallback UI instead of crashing the whole app.
 */
class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
    constructor(props: ErrorBoundaryProps) {
        super(props);
        this.state = {
            hasError: false,
            error: null,
            errorInfo: null,
            showDetails: false
        };
    }

    static getDerivedStateFromError(error) {
        // Update state so the next render shows the fallback UI
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
        // Log error to console and potentially to a service
        console.error('ErrorBoundary caught an error:', error);
        console.error('Component stack:', errorInfo.componentStack);

        this.setState({ errorInfo });

        // Log to external service if configured
        if (this.props.onError) {
            this.props.onError(error, errorInfo);
        }
    }

    handleReset = () => {
        this.setState({
            hasError: false,
            error: null,
            errorInfo: null,
            showDetails: false
        });

        // Call optional reset callback
        if (this.props.onReset) {
            this.props.onReset();
        }
    };

    handleGoHome = () => {
        window.location.href = '/';
    };

    toggleDetails = () => {
        this.setState(prev => ({ showDetails: !prev.showDetails }));
    };

    render() {
        if (this.state.hasError) {
            const { error, errorInfo, showDetails } = this.state;
            const {
                fallbackTitle = 'Something went wrong',
                fallbackDescription = 'An error occurred in this component.',
                showResetButton = true,
                showHomeButton = false,
                showErrorDetails = true,
                variant = 'default' // 'default' | 'minimal' | 'graph'
            } = this.props;

            // Minimal variant for inline errors
            if (variant === 'minimal') {
                return (
                    <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center space-x-2">
                                <AlertTriangle className="w-4 h-4 text-red-400" />
                                <span className="text-sm text-red-400">{fallbackTitle}</span>
                            </div>
                            {showResetButton && (
                                <button
                                    onClick={this.handleReset}
                                    className="text-xs text-red-400 hover:text-red-300 underline"
                                >
                                    Retry
                                </button>
                            )}
                        </div>
                    </div>
                );
            }

            // Graph variant for visualization errors
            if (variant === 'graph') {
                return (
                    <div className="w-full h-full min-h-[400px] flex items-center justify-center bg-gray-900 rounded-lg border-2 border-red-500/30">
                        <div className="text-center p-8 max-w-md">
                            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-red-500/20 flex items-center justify-center">
                                <AlertTriangle className="w-8 h-8 text-red-400" />
                            </div>
                            <h3 className="text-xl font-semibold text-white mb-2">
                                Visualization Error
                            </h3>
                            <p className="text-gray-400 mb-6">
                                The graph could not be rendered. This may be due to invalid data or a rendering issue.
                            </p>
                            <div className="flex items-center justify-center space-x-3">
                                <button
                                    onClick={this.handleReset}
                                    className="flex items-center space-x-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                                >
                                    <RefreshCw className="w-4 h-4" />
                                    <span>Click to Reset</span>
                                </button>
                            </div>

                            {showErrorDetails && error && (
                                <div className="mt-6">
                                    <button
                                        onClick={this.toggleDetails}
                                        className="flex items-center space-x-1 mx-auto text-xs text-gray-500 hover:text-gray-400"
                                    >
                                        <Bug className="w-3 h-3" />
                                        <span>Technical Details</span>
                                        {showDetails ? (
                                            <ChevronUp className="w-3 h-3" />
                                        ) : (
                                            <ChevronDown className="w-3 h-3" />
                                        )}
                                    </button>

                                    {showDetails && (
                                        <div className="mt-3 p-3 bg-gray-800 rounded text-left text-xs">
                                            <p className="text-red-400 font-mono break-all">
                                                {error.toString()}
                                            </p>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                );
            }

            // Default full-page error
            return (
                <div className="min-h-[300px] flex items-center justify-center bg-gray-900/50 backdrop-blur-sm rounded-lg border border-red-500/30 p-8">
                    <div className="text-center max-w-lg">
                        {/* Error Icon */}
                        <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-red-500/20 flex items-center justify-center">
                            <AlertTriangle className="w-10 h-10 text-red-400" />
                        </div>

                        {/* Title */}
                        <h2 className="text-2xl font-bold text-white mb-3">
                            {fallbackTitle}
                        </h2>

                        {/* Description */}
                        <p className="text-gray-400 mb-6">
                            {fallbackDescription}
                        </p>

                        {/* Action Buttons */}
                        <div className="flex items-center justify-center space-x-4 mb-6">
                            {showResetButton && (
                                <button
                                    onClick={this.handleReset}
                                    className="flex items-center space-x-2 px-6 py-3 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors font-medium"
                                >
                                    <RefreshCw className="w-5 h-5" />
                                    <span>Try Again</span>
                                </button>
                            )}

                            {showHomeButton && (
                                <button
                                    onClick={this.handleGoHome}
                                    className="flex items-center space-x-2 px-6 py-3 bg-gray-700 text-white rounded-lg hover:bg-gray-600 transition-colors font-medium"
                                >
                                    <Home className="w-5 h-5" />
                                    <span>Go Home</span>
                                </button>
                            )}
                        </div>

                        {/* Error Details (Collapsible) */}
                        {showErrorDetails && error && (
                            <div className="border-t border-gray-700 pt-6">
                                <button
                                    onClick={this.toggleDetails}
                                    className="flex items-center space-x-2 mx-auto text-sm text-gray-500 hover:text-gray-400 transition-colors"
                                >
                                    <Bug className="w-4 h-4" />
                                    <span>Show Technical Details</span>
                                    {showDetails ? (
                                        <ChevronUp className="w-4 h-4" />
                                    ) : (
                                        <ChevronDown className="w-4 h-4" />
                                    )}
                                </button>

                                {showDetails && (
                                    <div className="mt-4 p-4 bg-gray-800 rounded-lg text-left overflow-auto max-h-48">
                                        <div className="mb-3">
                                            <span className="text-xs text-gray-500 uppercase tracking-wide">Error:</span>
                                            <p className="text-red-400 font-mono text-sm mt-1 break-all">
                                                {error.toString()}
                                            </p>
                                        </div>

                                        {errorInfo && (
                                            <div>
                                                <span className="text-xs text-gray-500 uppercase tracking-wide">Component Stack:</span>
                                                <pre className="text-gray-400 text-xs mt-1 whitespace-pre-wrap break-all">
                                                    {errorInfo.componentStack}
                                                </pre>
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}

/**
 * GraphErrorBoundary - Specialized boundary for graph visualization
 */
export const GraphErrorBoundary = ({ children, onReset }: { children: React.ReactNode; onReset?: () => void }) => {
    return (
        <ErrorBoundary
            variant="graph"
            fallbackTitle="Visualization Error"
            fallbackDescription="The graph could not be rendered."
            showErrorDetails={true}
            onReset={onReset}
        >
            {children}
        </ErrorBoundary>
    );
};

/**
 * InspectorErrorBoundary - Specialized boundary for inspector panel
 */
export const InspectorErrorBoundary = ({ children, onReset }: { children: React.ReactNode; onReset?: () => void }) => {
    return (
        <ErrorBoundary
            variant="minimal"
            fallbackTitle="Inspector Error"
            showErrorDetails={false}
            onReset={onReset}
        >
            {children}
        </ErrorBoundary>
    );
};

/**
 * withErrorBoundary - HOC to wrap components with error boundary
 */
export function withErrorBoundary(Component, errorBoundaryProps = {}) {
    return function WrappedComponent(props) {
        return (
            <ErrorBoundary {...errorBoundaryProps}>
                <Component {...props} />
            </ErrorBoundary>
        );
    };
}

export default ErrorBoundary;
