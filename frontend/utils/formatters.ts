// frontend/src/utils/formatters.js

/**
 * Format satoshis to BTC with 8 decimal places
 * @param {number} satoshis - Amount in satoshis
 * @returns {string} Formatted BTC amount
 */
export const formatBTC = (satoshis) => {
    if (satoshis === null || satoshis === undefined) return '0.00000000';
    const btc = satoshis / 100000000;
    return btc.toFixed(8);
};

/**
 * Format BTC amount with appropriate precision
 * @param {number} btc - Amount in BTC
 * @param {number} decimals - Number of decimal places (default: 8)
 * @returns {string} Formatted BTC amount
 */
export const formatBTCAmount = (btc, decimals = 8) => {
    if (btc === null || btc === undefined) return '0.00000000';
    return parseFloat(btc).toFixed(decimals);
};

/**
 * Format satoshis to BTC with readable format (removes trailing zeros)
 * @param {number} satoshis - Amount in satoshis
 * @returns {string} Formatted BTC amount
 */
export const formatBTCReadable = (satoshis) => {
    if (satoshis === null || satoshis === undefined) return '0';
    const btc = satoshis / 100000000;
    return btc.toFixed(8).replace(/\.?0+$/, '');
};

/**
 * Format USD amount
 * @param {number} usd - USD amount
 * @returns {string} Formatted USD amount
 */
export const formatUSD = (usd) => {
    if (usd === null || usd === undefined) return '$0.00';
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(usd);
};

/**
 * Convert satoshis to USD using BTC price
 * @param {number} satoshis - Amount in satoshis
 * @param {number} btcPrice - Current BTC price in USD
 * @returns {number} USD amount
 */
export const satoshisToUSD = (satoshis, btcPrice) => {
    if (!satoshis || !btcPrice) return 0;
    const btc = satoshis / 100000000;
    return btc * btcPrice;
};

/**
 * Format satoshis with BTC and USD
 * @param {number} satoshis - Amount in satoshis
 * @param {number} btcPrice - Current BTC price in USD (optional)
 * @returns {string} Formatted amount with BTC and optionally USD
 */
export const formatBTCWithUSD = (satoshis, btcPrice = null) => {
    const btc = formatBTC(satoshis);
    if (btcPrice) {
        const usd = satoshisToUSD(satoshis, btcPrice);
        return `${btc} BTC (${formatUSD(usd)})`;
    }
    return `${btc} BTC`;
};

/**
 * Format large numbers with commas
 * @param {number} num - Number to format
 * @returns {string} Formatted number
 */
export const formatNumber = (num) => {
    if (num === null || num === undefined) return '0';
    return new Intl.NumberFormat('en-US').format(num);
};

/**
 * Format hash (address, tx hash) with ellipsis
 * @param {string} hash - Hash to format
 * @param {number} startChars - Characters to show at start (default: 8)
 * @param {number} endChars - Characters to show at end (default: 8)
 * @returns {string} Formatted hash
 */
export const formatHash = (hash, startChars = 8, endChars = 8) => {
    if (!hash) return '';
    if (hash.length <= startChars + endChars) return hash;
    return `${hash.slice(0, startChars)}...${hash.slice(-endChars)}`;
};

/**
 * Format timestamp to readable date
 * @param {number} timestamp - Unix timestamp (seconds or milliseconds)
 * @returns {string} Formatted date
 */
export const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'Unknown';

    // Convert to milliseconds if in seconds
    const ms = timestamp < 10000000000 ? timestamp * 1000 : timestamp;

    const date = new Date(ms);
    return new Intl.DateTimeFormat('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    }).format(date);
};

/**
 * Format time ago (relative time)
 * @param {number} timestamp - Unix timestamp (seconds or milliseconds)
 * @returns {string} Relative time string
 */
export const formatTimeAgo = (timestamp) => {
    if (!timestamp) return 'Unknown';

    // Convert to milliseconds if in seconds
    const ms = timestamp < 10000000000 ? timestamp * 1000 : timestamp;

    const now = Date.now();
    const diff = now - ms;

    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    const months = Math.floor(days / 30);
    const years = Math.floor(days / 365);

    if (years > 0) return `${years} year${years > 1 ? 's' : ''} ago`;
    if (months > 0) return `${months} month${months > 1 ? 's' : ''} ago`;
    if (days > 0) return `${days} day${days > 1 ? 's' : ''} ago`;
    if (hours > 0) return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    if (minutes > 0) return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
    return `${seconds} second${seconds !== 1 ? 's' : ''} ago`;
};

/**
 * Format percentage
 * @param {number} value - Value to format as percentage
 * @param {number} decimals - Decimal places (default: 2)
 * @returns {string} Formatted percentage
 */
export const formatPercentage = (value, decimals = 2) => {
    if (value === null || value === undefined) return '0%';
    return `${value.toFixed(decimals)}%`;
};

/**
 * Format file size
 * @param {number} bytes - Size in bytes
 * @returns {string} Formatted file size
 */
export const formatBytes = (bytes) => {
    if (bytes === 0) return '0 Bytes';

    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

/**
 * Parse comma-separated addresses
 * @param {string} input - Comma-separated address string
 * @returns {string[]} Array of trimmed addresses
 */
export const parseAddresses = (input) => {
    if (!input || typeof input !== 'string') return [];

    return input
        .split(',')
        .map(addr => addr.trim())
        .filter(addr => addr.length > 0);
};

/**
 * Validate Bitcoin address format
 * @param {string} address - Bitcoin address to validate
 * @returns {boolean} True if valid
 */
export const isValidBitcoinAddress = (address) => {
    if (!address || typeof address !== 'string') return false;

    // P2PKH addresses (start with 1)
    // P2SH addresses (start with 3)
    // Bech32 addresses (start with bc1)
    const regex = /^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$|^bc1[a-z0-9]{39,59}$/;

    return regex.test(address);
};

/**
 * Get risk level color
 * @param {number} score - Risk score (0-100)
 * @returns {string} Tailwind color class
 */
export const getRiskColor = (score) => {
    if (score >= 80) return 'text-red-500';
    if (score >= 60) return 'text-orange-500';
    if (score >= 40) return 'text-yellow-500';
    if (score >= 20) return 'text-blue-500';
    return 'text-green-500';
};

/**
 * Get risk level background color
 * @param {number} score - Risk score (0-100)
 * @returns {string} Tailwind background color class
 */
export const getRiskBgColor = (score) => {
    if (score >= 80) return 'bg-red-500/20 border-red-500/50';
    if (score >= 60) return 'bg-orange-500/20 border-orange-500/50';
    if (score >= 40) return 'bg-yellow-500/20 border-yellow-500/50';
    if (score >= 20) return 'bg-blue-500/20 border-blue-500/50';
    return 'bg-green-500/20 border-green-500/50';
};

/**
 * Get risk level label
 * @param {number} score - Risk score (0-100)
 * @returns {string} Risk level label
 */
export const getRiskLabel = (score) => {
    if (score >= 80) return 'Critical';
    if (score >= 60) return 'High';
    if (score >= 40) return 'Medium';
    if (score >= 20) return 'Low';
    return 'Minimal';
};

export default {
    formatBTC,
    formatBTCAmount,
    formatBTCReadable,
    formatUSD,
    satoshisToUSD,
    formatBTCWithUSD,
    formatNumber,
    formatHash,
    formatTimestamp,
    formatTimeAgo,
    formatPercentage,
    formatBytes,
    parseAddresses,
    isValidBitcoinAddress,
    getRiskColor,
    getRiskBgColor,
    getRiskLabel
};
