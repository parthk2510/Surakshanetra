// @ts-nocheck
import axios from 'axios';
import logger from './logger';

declare module 'axios' {
  interface InternalAxiosRequestConfig {
    metadata?: { startTime: number };
    _retry?: boolean;
  }
}

const api = axios.create({
  baseURL: '',
  timeout: 30010,
  withCredentials: true,
  xsrfCookieName: 'csrf_access_token',
  xsrfHeaderName: 'X-CSRF-TOKEN',
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use(
  (config) => {
    const startTime = performance.now();
    config.metadata = { startTime };

    // Auth is handled via httpOnly cookies (withCredentials: true above).
    // Do NOT read tokens from localStorage — that would expose them to XSS.

    logger.debug(`API Request: ${config.method?.toUpperCase()} ${config.url}`, {
      method: config.method,
      url: config.url,
      // Do NOT log request body — may contain credentials or PII
      hasData: config.data != null,
      params: config.params
    });

    return config;
  },
  (error) => {
    logger.error('API Request Error', error);
    return Promise.reject(error);
  }
);

// Token refresh function
let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach(prom => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

const refreshToken = async () => {
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

    // New access_token_cookie is set by the server as httpOnly — no localStorage storage needed.
    const data = await response.json();
    // Return token only for the immediate in-memory retry; do NOT persist to storage.
    return data.access_token || true;
  } catch (error) {
    clearSession();
    window.location.reload();
    throw error;
  }
};

export const clearSession = () => {
  isRefreshing = false;
  failedQueue = [];
  const keysToRemove = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key && (key.startsWith('chainbreak_') || key.startsWith('upi_detection_settings'))) {
      keysToRemove.push(key);
    }
  }
  keysToRemove.forEach(k => localStorage.removeItem(k));
};

api.interceptors.response.use(
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
    const duration = originalRequest?.metadata?.startTime ?
      endTime - originalRequest.metadata.startTime : 0;

    // Handle 401 Unauthorized - token expired
    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        // If already refreshing, queue this request
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then(() => {
          // Cookie was already refreshed; retry with credentials.
          return api(originalRequest);
        }).catch(err => {
          return Promise.reject(err);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        await refreshToken();
        processQueue(null, null);
        // Cookie was refreshed server-side; retry relies on withCredentials cookies.
        return api(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        logger.error('Token refresh failed', refreshError);
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
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

export const apiService = {
  async get(endpoint, config = {}) {
    try {
      const response = await api.get(endpoint, config);
      return response.data;
    } catch (error) {
      throw this.handleError(error, 'GET', endpoint);
    }
  },

  async post(endpoint, data = {}, config = {}) {
    try {
      const response = await api.post(endpoint, data, config);
      return response.data;
    } catch (error) {
      throw this.handleError(error, 'POST', endpoint);
    }
  },

  async put(endpoint, data = {}, config = {}) {
    try {
      const response = await api.put(endpoint, data, config);
      return response.data;
    } catch (error) {
      throw this.handleError(error, 'PUT', endpoint);
    }
  },

  async delete(endpoint, config = {}) {
    try {
      const response = await api.delete(endpoint, config);
      return response.data;
    } catch (error) {
      throw this.handleError(error, 'DELETE', endpoint);
    }
  },

  handleError(error, method, endpoint) {
    let errorMessage = 'An unexpected error occurred';
    let errorDetails = {};

    if (error.response) {
      const { status, data } = error.response;

      switch (status) {
        case 400:
          errorMessage = data.error || 'Bad request';
          break;
        case 401:
          errorMessage = 'Unauthorized access';
          break;
        case 403:
          errorMessage = 'Access forbidden';
          break;
        case 404:
          errorMessage = 'Resource not found';
          break;
        case 429:
          errorMessage = 'Too many requests. Please try again later.';
          break;
        case 500:
          errorMessage = 'Internal server error';
          break;
        case 502:
          errorMessage = 'Bad gateway';
          break;
        case 503:
          errorMessage = 'Service unavailable';
          break;
        default:
          errorMessage = data.error || `HTTP ${status} error`;
      }

      errorDetails = {
        status,
        data,
        method,
        endpoint
      };
    } else if (error.request) {
      errorMessage = 'No response received from server';
      errorDetails = {
        method,
        endpoint,
        request: error.request
      };
    } else {
      errorMessage = error.message || 'Network error';
      errorDetails = {
        method,
        endpoint,
        message: error.message
      };
    }

    const apiError = new Error(errorMessage) as Error & { isApiError: boolean; details: unknown; originalError: unknown };
    apiError.isApiError = true;
    apiError.details = errorDetails;
    apiError.originalError = error;

    logger.error(`API Error: ${errorMessage}`, apiError, errorDetails);

    return apiError;
  }
};

export const chainbreakAPI = {
  async getBackendMode() {
    return apiService.get('/api/mode');
  },

  async getSystemStatus() {
    return apiService.get('/api/status');
  },

  async listGraphs() {
    return apiService.get('/api/graph/list');
  },

  async getGraph(name) {
    return apiService.get('/api/graph/get', { params: { name } });
  },

  async fetchAndSaveGraph(address, txLimit = 50) {
    return apiService.post('/api/graph/address', { address, tx_limit: txLimit });
  },

  async analyzeAddress(address, blockchain = 'btc', generateVisualizations = true) {
    return apiService.post('/api/analyze', {
      address,
      blockchain,
      generate_visualizations: generateVisualizations
    });
  },

  async analyzeMultipleAddresses(addresses, blockchain = 'btc') {
    return apiService.post('/api/analyze/batch', {
      addresses,
      blockchain
    });
  },

  async exportToGephi(address, outputFile = null) {
    const params = { address };
    if (outputFile) params.output_file = outputFile;
    return apiService.get('/api/export/gephi', { params });
  },

  async generateRiskReport(addresses, outputFile = null) {
    return apiService.post('/api/report/risk', {
      addresses,
      output_file: outputFile
    });
  },

  async getAnalyzedAddresses() {
    return apiService.get('/api/addresses');
  },

  async getStatistics() {
    return apiService.get('/api/statistics');
  },

  // ── UPI Mule Detection API ──

  async analyzeUPI(csvFile, settings = null) {
    const formData = new FormData();
    formData.append('file', csvFile);
    if (settings) formData.append('settings', JSON.stringify(settings));
    return apiService.post('/api/upi/analyze', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 600000, // 10 minutes — matches Gunicorn worker timeout
    });
  },

  async getUPISettings() {
    return apiService.get('/api/upi/settings');
  },

  async getUPIHealth() {
    return apiService.get('/api/upi/health');
  },

  // ── UPI Community Detection API ──

  async detectCommunities(graphData, algorithm = 'louvain', resolution = 1.0, options = {}) {
    return apiService.post('/api/upi/communities/detect', {
      graph_data: graphData,
      algorithm,
      resolution,
      min_risk_score: options.minRiskScore ?? 60.0,
      export_results: options.exportResults ?? false,
    });
  },

  async compareCommunities(graphData, options = {}) {
    return apiService.post('/api/upi/communities/compare', {
      graph_data: graphData,
      algorithms: options.algorithms,
      run_all_algorithms: options.runAll ?? true,
      generate_validation_batch: options.generateValidationBatch ?? false,
      top_n_validation: options.topNValidation ?? 50,
      export_results: options.exportResults ?? false,
    });
  },

  async getSuspiciousCommunities(communityResults, minRiskScore = 60.0, minMembers = 3) {
    return apiService.post('/api/upi/communities/suspicious', {
      community_results: communityResults,
      min_risk_score: minRiskScore,
      min_members: minMembers,
    });
  },

  async getValidationBatch(comparisonResults, topN = 50, riskThreshold = 70.0) {
    return apiService.post('/api/upi/communities/validation', {
      comparison_results: comparisonResults,
      top_n: topN,
      risk_threshold: riskThreshold,
    });
  },
};

export default apiService;
