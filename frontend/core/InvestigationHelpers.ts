/**
 * HELPER METHODS FOR INVESTIGATION MANAGEMENT
 */

/**
 * Check if address is already investigated
 */
export function isAddressInvestigated(caseFile: { nodes: Record<string, unknown>; metadata: { investigatedAddresses: string[] } }, address: string) {
    return caseFile.nodes[address] !== undefined &&
        caseFile.metadata.investigatedAddresses.includes(address);
}

/**
 * Estimate investigation time based on options
 */
export function estimateFetchTime(address: string, options: { fetchUTXOs?: boolean; fetchCharts?: boolean } = {}) {
    // Base: 1 request per 10 seconds due to rate limiting
    let apiCalls = 1; // Initial address fetch
    let seconds = 10;

    // Address with transactions (assume average 100 txs = 2 additional calls)
    apiCalls += 2;
    seconds += 20;

    if (options.fetchUTXOs !== false) {
        apiCalls += 1;
        seconds += 10;
    }

    if (options.fetchCharts !== false) {
        apiCalls += 4; // price, hashrate, difficulty, tx-rate
        seconds += 40;
    }

    // Add buffer
    seconds += 10;

    const minutes = Math.ceil(seconds / 60);

    return {
        seconds,
        minutes,
        apiCalls,
        formatted: minutes < 2 ? `${seconds} seconds` : `${minutes} minutes`
    };
}

/**
 * Load existing case file from backend
 */
export async function loadCaseFile(caseId) {
    try {
        const response = await fetch(`/api/cases/${caseId}`);
        if (!response.ok) {
            throw new Error(`Failed to load case file: ${response.statusText}`);
        }
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Failed to load case file:', error);
        throw error;
    }
}

/**
 * List all available case files
 */
export async function listCaseFiles() {
    try {
        const response = await fetch('/api/cases');
        if (!response.ok) {
            throw new Error(`Failed to list case files: ${response.statusText}`);
        }
        const data = await response.json();
        return data.cases || [];
    } catch (error) {
        console.error('Failed to list case files:', error);
        return [];
    }
}
