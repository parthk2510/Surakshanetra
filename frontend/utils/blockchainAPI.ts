// @ts-nocheck
// frontend/src/utils/blockchainAPI.ts
// ============================================================================
// BLOCKCHAIN API SERVICE - Communicates with Backend API
// Supports dynamic configuration from ConfigContext
// ============================================================================
import axios from 'axios';
import toast from 'react-hot-toast';
import logger from './logger';

declare module 'axios' {
  interface InternalAxiosRequestConfig {
    metadata?: { startTime: number };
    _retry?: boolean;
  }
}

const API_BASE_URL = '';

// ============================================================================
// GLOBAL CONFIG GETTER - Set by ConfigContext, used by API calls
// ============================================================================
let globalConfigGetter = null;

/**
 * Set the global config getter function (called by ConfigContext on mount)
 */
export function setConfigGetter(getter) {
    globalConfigGetter = getter;
}

/**
 * Get current config or return defaults
 */
function getConfig() {
    if (globalConfigGetter) {
        return globalConfigGetter();
    }
    // Fallback defaults if ConfigContext not yet mounted
    return {
        fetchLimit: 100,
        searchDepth: 1,
        analysisMode: 'LITE_EXPLORER',
        showDust: true,
        dustThreshold: 1000,
        enableParallelFetch: true,
        maxConcurrentRequests: 5,
    };
}

// Create axios instance with default config
const blockchainAPI = axios.create({
    baseURL: API_BASE_URL,
    timeout: 120000, // 120 seconds for large blockchain queries
    withCredentials: true,
    xsrfCookieName: 'csrf_access_token',
    xsrfHeaderName: 'X-CSRF-TOKEN',
    headers: {
        'Content-Type': 'application/json',
    },
});


// Request interceptor
blockchainAPI.interceptors.request.use(
    (config) => {
        const startTime = performance.now();
        config.metadata = { startTime };

        // Cookies are automatically sent due to withCredentials: true

        logger.debug(`Blockchain API Request: ${config.method?.toUpperCase()} ${config.url}`, {
            method: config.method,
            url: config.url,
            data: config.data,
            params: config.params
        });

        return config;
    },
    (error) => {
        logger.error('Blockchain API Request Error', error);
        return Promise.reject(error);
    }
);

// Token refresh function for blockchain API
let isRefreshingBlockchain = false;
let failedQueueBlockchain = [];

const processQueueBlockchain = (error, token = null) => {
    failedQueueBlockchain.forEach(prom => {
        if (error) {
            prom.reject(error);
        } else {
            prom.resolve(token);
        }
    });
    failedQueueBlockchain = [];
};

const refreshTokenBlockchain = async () => {
    try {
        const getCsrfToken = () => {
            const match = document.cookie.match(/(^|;)\s*csrf_refresh_token\s*=\s*([^;]+)/);
            return match ? match[2] : '';
        };

        const response = await fetch(`/api/auth/refresh`, {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-TOKEN': getCsrfToken()
            }
        });

        if (!response.ok) {
            throw new Error('Token refresh failed');
        }

        return true;
    } catch (error) {
        localStorage.removeItem('chainbreak_user');
        window.location.reload();
        throw error;
    }
};

// Response interceptor
blockchainAPI.interceptors.response.use(
    (response) => {
        const endTime = performance.now();
        const duration = endTime - response.config.metadata.startTime;

        logger.logAPIRequest(
            response.config.method,
            response.config.url,
            response.status,
            duration,
            { data: response.data }
        );

        return response;
    },
    async (error) => {
        const originalRequest = error.config;
        const endTime = performance.now();
        const duration = originalRequest?.metadata?.startTime
            ? endTime - originalRequest.metadata.startTime
            : 0;

        // Handle 401 Unauthorized - token expired
        if (error.response?.status === 401 && !originalRequest._retry) {
            if (isRefreshingBlockchain) {
                return new Promise((resolve, reject) => {
                    failedQueueBlockchain.push({ resolve, reject });
                }).then(token => {
                    originalRequest.headers.Authorization = `Bearer ${token}`;
                    return blockchainAPI(originalRequest);
                }).catch(err => {
                    return Promise.reject(err);
                });
            }

            originalRequest._retry = true;
            isRefreshingBlockchain = true;

            try {
                const newToken = await refreshTokenBlockchain();
                processQueueBlockchain(null, newToken);
                return blockchainAPI(originalRequest);
            } catch (refreshError) {
                processQueueBlockchain(refreshError, null);
                logger.error('Token refresh failed', refreshError);
                return Promise.reject(refreshError);
            } finally {
                isRefreshingBlockchain = false;
            }
        }

        logger.logAPIRequest(
            originalRequest?.method || 'UNKNOWN',
            originalRequest?.url || 'UNKNOWN',
            error.response?.status || 0,
            duration,
            {
                error: error.message,
                response: error.response?.data
            }
        );

        return Promise.reject(error);
    }
);

// ============================================================================
// RETRY LOGIC WITH EXPONENTIAL BACKOFF - For rate limiting (429 errors)
// ============================================================================

/**
 * Sleep utility for async delays
 */
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

interface RetryOptions {
    maxRetries?: number;
    baseDelay?: number;
    maxDelay?: number;
    retryOn?: number[];
    onRetry?: ((attempt: number, maxRetries: number, delay: number) => void) | null;
}

/**
 * Retry a request with exponential backoff
 * @param requestFn - Function that returns axios promise
 * @param options - Retry options
 */
async function retryRequest(requestFn: () => Promise<unknown>, options: RetryOptions = {}) {
    const {
        maxRetries = 3,
        baseDelay = 10000,  // 10 seconds for rate limiting (API allows 1 req/10s)
        maxDelay = 60000,   // Max 60 seconds
        retryOn = [429, 503, 504],  // HTTP codes to retry on
        onRetry = null      // Callback on each retry
    } = options;

    let lastError = null;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
            return await requestFn();
        } catch (error) {
            lastError = error;
            const status = error.response?.status;

            // Don't retry if not a retryable error
            if (!status || !retryOn.includes(status)) {
                throw error;
            }

            // Don't retry if we've exhausted retries
            if (attempt >= maxRetries) {
                throw error;
            }

            // Calculate delay with exponential backoff
            const delay = Math.min(baseDelay * Math.pow(2, attempt), maxDelay);

            logger.warn(`Rate limited (${status}). Retrying in ${delay / 1000}s... (attempt ${attempt + 1}/${maxRetries})`);

            if (onRetry) {
                onRetry(attempt + 1, maxRetries, delay);
            }

            // Show toast notification for rate limiting
            if (status === 429) {
                toast.loading(
                    `Rate limited. Waiting ${delay / 1000}s before retry (${attempt + 1}/${maxRetries})...`,
                    {
                        id: 'rate-limit-retry',
                        duration: delay
                    }
                );
            }

            await sleep(delay);
        }
    }

    throw lastError;
}

/**
 * Make an API request with automatic retry on rate limiting
 */
async function makeRequestWithRetry(config) {
    return retryRequest(() => blockchainAPI.request(config), {
        maxRetries: 3,
        baseDelay: 10000,
        onRetry: (attempt, maxRetries, delay) => {
            console.log(`[BlockchainAPI] Retry ${attempt}/${maxRetries} after ${delay}ms`);
        }
    });
}


/**
 * Handle API errors with user-friendly toast notifications
 */
const handleAPIError = (error, context = '') => {
    let errorMessage = 'An unexpected error occurred';

    if (error.response) {
        const { status, data } = error.response;

        switch (status) {
            case 400:
                errorMessage = data.error || 'Invalid request parameters';
                toast.error(`Bad Request: ${errorMessage}`, { duration: 4000 });
                break;
            case 404:
                errorMessage = data.error || 'Address or resource not found';
                toast.error(`Not Found: ${errorMessage}`, {
                    duration: 5000,
                    icon: '🔍'
                });
                break;
            case 429:
                errorMessage = 'Rate limit exceeded. Please wait before trying again.';
                toast.error(errorMessage, {
                    duration: 6000,
                    icon: '⏱️'
                });
                break;
            case 500:
            case 502:
            case 503:
                errorMessage = 'Server error. Please try again later.';
                toast.error(errorMessage, { duration: 5000 });
                break;
            default:
                errorMessage = data.error || `HTTP ${status} error`;
                toast.error(errorMessage, { duration: 4000 });
        }

        logger.error(`API Error [${status}]: ${context}`, errorMessage, data);
    } else if (error.request) {
        errorMessage = 'No response from server. Check your connection.';
        toast.error(errorMessage, { duration: 5000 });
        logger.error(`No Response: ${context}`, error.request);
    } else {
        errorMessage = error.message || 'Network error occurred';
        toast.error(errorMessage, { duration: 4000 });
        logger.error(`Network Error: ${context}`, error.message);
    }

    const apiError = new Error(errorMessage);
    apiError.isAPIError = true;
    apiError.status = error.response?.status;
    apiError.originalError = error;

    return apiError;
};

/**
 * Production-ready Blockchain API Service
 */
export const blockchainService = {

    // ============================================================================
    // ADDRESS ENDPOINTS
    // ============================================================================

    /**
     * Fetch single address data
     * @param {string} address - Bitcoin address
     * @param {number} limit - Transaction limit (default: 50)
     * @returns {Promise<Object>} Address data with transactions
     */
    async fetchAddress(address, limit = 50) {
        try {
            const response = await blockchainAPI.get(
                `/api/blockchain/address/${address}`,
                { params: { limit } }
            );
            return response.data;
        } catch (error) {
            throw handleAPIError(error, `fetchAddress(${address})`);
        }
    },

    /**
     * Fetch comprehensive address data (all transactions, UTXOs, balance)
     * @param {string} address - Bitcoin address
     * @returns {Promise<Object>} Comprehensive address data
     */
    async fetchAddressComprehensive(address) {
        try {
            const response = await blockchainAPI.get(
                `/api/blockchain/address-comprehensive/${address}`
            );
            return response.data;
        } catch (error) {
            throw handleAPIError(error, `fetchAddressComprehensive(${address})`);
        }
    },

    /**
     * Fetch pre-built graph data for a single address from backend graph endpoint
     * @param {string} address - Bitcoin address
     * @param {number} txLimit - Transaction limit used for graph construction
     * @returns {Promise<Object>} Backend graph response including graph, meta and stats
     */
    async fetchAddressGraph(address, txLimit = 50) {
        try {
            const response = await blockchainAPI.post('/api/graph/address', {
                address,
                tx_limit: txLimit
            });
            return response.data;
        } catch (error) {
            throw handleAPIError(error, `fetchAddressGraph(${address})`);
        }
    },

    /**
     * Fetch balance for one or more addresses
     * @param {string|string[]} addresses - Single address or array of addresses
     * @returns {Promise<Object>} Balance data
     */
    async fetchBalance(addresses) {
        try {
            const addressArray = Array.isArray(addresses) ? addresses : [addresses];
            const response = await blockchainAPI.post('/api/blockchain/balance', {
                addresses: addressArray
            });
            return response.data;
        } catch (error) {
            throw handleAPIError(error, 'fetchBalance');
        }
    },

    /**
     * Fetch cluster data for multiple addresses (SUSPECT CLUSTER ANALYSIS)
     * Uses global configuration for analysis mode, limits, and parallel settings.
     * 
     * @param {string[]} addresses - Array of Bitcoin addresses
     * @param {Object} overrides - Optional config overrides
     * @returns {Promise<Object>} Multi-address data with shared connections
     */
    async fetchClusterData(addresses, overrides = {}) {
        try {
            if (!Array.isArray(addresses) || addresses.length === 0) {
                throw new Error('Addresses must be a non-empty array');
            }

            // Get current config and apply overrides
            const config = { ...getConfig(), ...overrides };
            const isForensic = config.analysisMode === 'FORENSIC_DEEP_DIVE';

            const modeLabel = isForensic ? 'Deep forensic' : 'Quick';
            toast.loading(`${modeLabel} analysis of ${addresses.length} addresses...`, {
                id: 'cluster-fetch',
                duration: isForensic ? 60000 : 10000
            });

            // Build request body with all config parameters
            const requestBody = {
                addresses,
                limit: config.fetchLimit,
                mode: config.analysisMode,
                parallel: config.enableParallelFetch,
                max_concurrent: config.maxConcurrentRequests,
                depth: config.searchDepth,
                show_dust: config.showDust,
                dust_threshold: config.dustThreshold
            };

            logger.debug('Cluster fetch request', requestBody);

            const response = await blockchainAPI.post('/api/blockchain/multi-address', requestBody);

            const txCount = response.data?.data?.txs?.length || 0;
            const addrCount = response.data?.data?.addresses?.length || 0;
            const aggInfo = response.data?.data?.aggregation_info || {};

            toast.success(
                `Analysis complete: ${txCount} txs from ${addrCount} addresses` +
                (aggInfo.parallel_mode ? ' (parallel)' : ''),
                { id: 'cluster-fetch', duration: 4000 }
            );

            return response.data;
        } catch (error) {
            toast.dismiss('cluster-fetch');
            throw handleAPIError(error, `fetchClusterData(${addresses.length} addresses)`);
        }
    },

    // ============================================================================
    // UTXO & RISK METRICS
    // ============================================================================

    /**
     * Fetch unspent outputs (UTXOs) for address
     * @param {string|string[]} addresses - Address(es) to query
     * @param {number} limit - Max UTXOs to return
     * @param {number} confirmations - Minimum confirmations
     * @returns {Promise<Object>} UTXO data
     */
    async fetchUnspent(addresses, limit = 250, confirmations = 0) {
        try {
            const addressArray = Array.isArray(addresses) ? addresses : [addresses];
            const response = await blockchainAPI.post('/api/blockchain/unspent', {
                addresses: addressArray,
                limit,
                confirmations
            });
            return response.data;
        } catch (error) {
            throw handleAPIError(error, 'fetchUnspent');
        }
    },

    /**
     * Calculate risk metrics including holding time from UTXO data
     * @param {string} address - Bitcoin address
     * @returns {Promise<Object>} Risk metrics including holding time, fragmentation, liquidity
     */
    async fetchRiskMetrics(address) {
        try {
            // Fetch UTXOs and address data in parallel
            const [utxoData, addressData] = await Promise.all([
                this.fetchUnspent(address),
                this.fetchAddressComprehensive(address)
            ]);

            const utxos = utxoData.data?.unspent_outputs || [];
            const addressInfo = addressData.data?.basic_info || {};

            // Calculate metrics
            const metrics = this._calculateRiskMetrics(utxos, addressInfo);

            return {
                success: true,
                data: {
                    address,
                    ...metrics,
                    utxo_count: utxos.length,
                    raw_utxos: utxos
                }
            };
        } catch (error) {
            throw handleAPIError(error, `fetchRiskMetrics(${address})`);
        }
    },

    /**
     * Internal: Calculate risk metrics from UTXO data
     * @private
     */
    _calculateRiskMetrics(utxos, addressInfo) {
        const now = Date.now();
        const ONE_DAY = 24 * 60 * 60 * 1000;

        if (!utxos || utxos.length === 0) {
            return {
                holding_time_days: 0,
                avg_holding_time_days: 0,
                fragmentation_score: 0,
                fragmentation_label: 'No UTXOs',
                liquidity_btc: 0,
                liquidity_satoshis: 0,
                dust_activity: false
            };
        }

        // Calculate holding time (time since oldest UTXO)
        let oldestUtxoAge = 0;
        let totalAge = 0;
        let totalValue = 0;
        let dustCount = 0;
        const DUST_THRESHOLD = 1000; // satoshis

        utxos.forEach(utxo => {
            const value = utxo.value || 0;
            totalValue += value;

            // Check for dust
            if (value < DUST_THRESHOLD) {
                dustCount++;
            }

            // Calculate age (we'll use confirmations as a proxy for age)
            // More confirmations = older UTXO
            const age = (utxo.confirmations || 0) * 10 * 60 * 1000; // ~10 min per block
            totalAge += age;

            if (age > oldestUtxoAge) {
                oldestUtxoAge = age;
            }
        });

        const avgAge = totalAge / utxos.length;
        const holdingTimeDays = oldestUtxoAge / ONE_DAY;
        const avgHoldingTimeDays = avgAge / ONE_DAY;

        // Fragmentation Score: Higher score = more fragmented
        // Based on UTXO count and dust activity
        let fragmentationScore = 0;
        let fragmentationLabel = 'Low';

        if (utxos.length > 500) {
            fragmentationScore = 100;
            fragmentationLabel = 'Extreme - High Dust Activity';
        } else if (utxos.length > 200) {
            fragmentationScore = 80;
            fragmentationLabel = 'Very High - Mining Pool Pattern';
        } else if (utxos.length > 100) {
            fragmentationScore = 60;
            fragmentationLabel = 'High - Fragmented';
        } else if (utxos.length > 50) {
            fragmentationScore = 40;
            fragmentationLabel = 'Moderate';
        } else if (utxos.length > 20) {
            fragmentationScore = 20;
            fragmentationLabel = 'Low';
        }

        // Adjust for dust activity
        const dustPercentage = (dustCount / utxos.length) * 100;
        if (dustPercentage > 50) {
            fragmentationScore = Math.min(100, fragmentationScore + 20);
            fragmentationLabel += ' (Potential Dusting Attack)';
        }

        return {
            holding_time_days: Math.round(holdingTimeDays * 100) / 100,
            avg_holding_time_days: Math.round(avgHoldingTimeDays * 100) / 100,
            fragmentation_score: fragmentationScore,
            fragmentation_label: fragmentationLabel,
            liquidity_btc: totalValue / 100000000,
            liquidity_satoshis: totalValue,
            dust_activity: dustPercentage > 10,
            dust_count: dustCount,
            dust_percentage: Math.round(dustPercentage * 100) / 100
        };
    },

    // ============================================================================
    // TRANSACTION & BLOCK ENDPOINTS
    // ============================================================================

    /**
     * Fetch transaction by hash
     * @param {string} txHash - Transaction hash
     * @returns {Promise<Object>} Transaction data
     */
    async fetchTransaction(txHash) {
        try {
            const response = await blockchainAPI.get(
                `/api/blockchain/transaction/${txHash}`
            );
            return response.data;
        } catch (error) {
            throw handleAPIError(error, `fetchTransaction(${txHash})`);
        }
    },

    /**
     * Fetch block by hash or height
     * @param {string|number} blockIdentifier - Block hash or height
     * @param {boolean} comprehensive - Fetch comprehensive data
     * @returns {Promise<Object>} Block data
     */
    async fetchBlock(blockIdentifier, comprehensive = false) {
        try {
            const response = await blockchainAPI.get(
                `/api/blockchain/block/${blockIdentifier}`,
                { params: { comprehensive } }
            );
            return response.data;
        } catch (error) {
            throw handleAPIError(error, `fetchBlock(${blockIdentifier})`);
        }
    },

    /**
     * Fetch latest block
     * @returns {Promise<Object>} Latest block data
     */
    async fetchLatestBlock() {
        try {
            const response = await blockchainAPI.get('/api/blockchain/latest-block');
            return response.data;
        } catch (error) {
            throw handleAPIError(error, 'fetchLatestBlock');
        }
    },

    // ============================================================================
    // MEMPOOL & LIVE MONITORING
    // ============================================================================

    /**
     * Fetch unconfirmed transactions from mempool
     * @param {number} limit - Max transactions to return
     * @returns {Promise<Object>} Unconfirmed transactions
     */
    async fetchUnconfirmedTransactions(limit = 100) {
        try {
            const response = await blockchainAPI.get(
                '/api/blockchain/unconfirmed-transactions',
                { params: { limit } }
            );
            return response.data;
        } catch (error) {
            throw handleAPIError(error, 'fetchUnconfirmedTransactions');
        }
    },

    /**
     * Monitor addresses for activity in mempool
     * @param {string[]} addresses - Addresses to monitor
     * @returns {Promise<Object>} Addresses found in mempool with transactions
     */
    async monitorMempoolActivity(addresses) {
        try {
            const mempoolData = await this.fetchUnconfirmedTransactions(200);
            const transactions = mempoolData.data?.transactions || [];

            const addressSet = new Set(addresses.map(a => a.toLowerCase()));
            const foundAddresses = new Map();

            transactions.forEach(tx => {
                // Check inputs
                (tx.inputs || []).forEach(input => {
                    const addr = input.prev_out?.addr;
                    if (addr && addressSet.has(addr.toLowerCase())) {
                        if (!foundAddresses.has(addr)) {
                            foundAddresses.set(addr, []);
                        }
                        foundAddresses.get(addr).push({
                            type: 'output',
                            tx_hash: tx.hash,
                            value: input.prev_out?.value || 0
                        });
                    }
                });

                // Check outputs
                (tx.out || []).forEach(output => {
                    const addr = output.addr;
                    if (addr && addressSet.has(addr.toLowerCase())) {
                        if (!foundAddresses.has(addr)) {
                            foundAddresses.set(addr, []);
                        }
                        foundAddresses.get(addr).push({
                            type: 'input',
                            tx_hash: tx.hash,
                            value: output.value || 0
                        });
                    }
                });
            });

            return {
                success: true,
                monitored_addresses: addresses.length,
                active_addresses: foundAddresses.size,
                activity: Object.fromEntries(foundAddresses)
            };
        } catch (error) {
            throw handleAPIError(error, 'monitorMempoolActivity');
        }
    },

    // ============================================================================
    // NETWORK STATS & CHARTS
    // ============================================================================

    /**
     * Fetch network statistics
     * @returns {Promise<Object>} Network stats
     */
    async fetchNetworkStats() {
        try {
            const response = await blockchainAPI.get('/api/blockchain/network-stats');
            return response.data;
        } catch (error) {
            throw handleAPIError(error, 'fetchNetworkStats');
        }
    },

    /**
     * PRODUCTION-RESILIENT: Fetch chart data with fallback
     * If the API fails, returns sensible default data instead of throwing.
     * 
     * @param {string} chartType - Chart type (market-price, hash-rate, etc.)
     * @param {string} timespan - Timespan (1year, 30days, etc.)
     * @returns {Promise<Object>} Chart data (may be fallback on error)
     */
    async fetchChart(chartType, timespan = '30days') {
        try {
            const response = await blockchainAPI.get(
                `/api/blockchain/chart/${chartType}`,
                { params: { timespan } }
            );
            return response.data;
        } catch (error) {
            // RESILIENT: Don't throw - return fallback data
            logger.warn(`Chart API failed for ${chartType}, using fallback`, error);

            const fallbackData = {
                success: true,
                data: {
                    status: 'fallback',
                    name: chartType,
                    unit: chartType.includes('price') ? 'USD' : '',
                    period: timespan,
                    values: []
                }
            };

            // Special handling for market-price - provide a recent price estimate
            if (chartType === 'market-price') {
                fallbackData.data.current_price = 98000;  // Fallback BTC price
                fallbackData.data.currency = 'USD';
                fallbackData.data.values = [{ x: Date.now() / 1000, y: 98000 }];
            }

            return fallbackData;
        }
    },

    /**
     * PRODUCTION-RESILIENT: Get current BTC price with guaranteed return
     * Never throws - always returns a number.
     * 
     * @returns {Promise<number>} BTC price in USD
     */
    async getCurrentPrice() {
        try {
            const result = await this.fetchChart('market-price', '24hours');
            const values = result?.data?.values || [];
            if (values.length > 0) {
                return values[values.length - 1].y || 98000;
            }
            return result?.data?.current_price || 98000;
        } catch (error) {
            logger.warn('Failed to get BTC price, using fallback', error);
            return 98000;  // Fallback price
        }
    },

    /**
     * Fetch blocks mined today
     * @returns {Promise<Object>} Today's blocks
     */
    async fetchBlocksToday() {
        try {
            const response = await blockchainAPI.get('/api/blockchain/blocks-today');
            return response.data;
        } catch (error) {
            throw handleAPIError(error, 'fetchBlocksToday');
        }
    },

    /**
     * Fetch blocks by mining pool
     * @param {string} poolName - Mining pool name
     * @returns {Promise<Object>} Pool blocks
     */
    async fetchBlocksByPool(poolName) {
        try {
            const response = await blockchainAPI.get(
                `/api/blockchain/blocks-by-pool/${poolName}`
            );
            return response.data;
        } catch (error) {
            throw handleAPIError(error, `fetchBlocksByPool(${poolName})`);
        }
    },

    /**
     * Save investigation case file
     * @param {Object} caseFile - The master case file object
     * @returns {Promise<Object>} Save result
     */
    async saveCaseFile(caseFile) {
        try {
            const response = await blockchainAPI.post('/api/case/save', {
                caseFile
            });
            return response.data;
        } catch (error) {
            throw handleAPIError(error, 'saveCaseFile');
        }
    },

    async fetchRecursive(address, depth = null) {
        try {
            const config = getConfig();
            const searchDepth = depth || config.searchDepth || 1;
            const maxAddresses = config.fetchLimit || 50;

            toast.loading(`Recursive fetch (${searchDepth} hops, exploring up to ${maxAddresses} addresses)...`, {
                id: 'recursive-fetch',
                duration: 60000
            });

            const response = await blockchainAPI.get(
                `/api/blockchain/recursive-fetch/${address}`,
                {
                    params: {
                        depth: searchDepth,
                        max_addresses: maxAddresses,
                        graph: true  // Request graph format
                    }
                }
            );

            const graphData = response.data.graph || response.data.data?.graph;
            const visitedCount = response.data.data?.visited_count || graphData?.meta?.visited_count || 0;
            const nodeCount = graphData?.nodes?.length || 0;
            const edgeCount = graphData?.edges?.length || 0;

            toast.success(
                `Fetched ${visitedCount} addresses, ${nodeCount} nodes, ${edgeCount} edges`,
                { id: 'recursive-fetch', duration: 5000 }
            );

            // Return graph-compatible structure
            return {
                success: true,
                graph: graphData,
                data: response.data.data,
                settings: response.data.settings
            };
        } catch (error) {
            toast.error('Recursive fetch failed', { id: 'recursive-fetch' });
            throw handleAPIError(error, 'fetchRecursive');
        }
    },

    async fetchLogs(lines = 100, level = null) {
        try {
            const response = await blockchainAPI.get('/api/logs', {
                params: { lines, level }
            });
            return response.data;
        } catch (error) {
            throw handleAPIError(error, 'fetchLogs');
        }
    },

    async fetchGatewayStats() {
        try {
            const response = await blockchainAPI.get('/api/gateway/stats');
            return response.data;
        } catch (error) {
            throw handleAPIError(error, 'fetchGatewayStats');
        }
    }
};

export default blockchainService;
