/**
 * Case File Manager
 * Handles saving and loading UPI-Case files to/from the server data folder
 */

const API_BASE_URL = '';

export const CaseFileManager = {
    /**
     * Save analysis data as a UPI-Case file in the data/cases folder
     * @param {string} fileName - Name of the case file
     * @param {Object} analysisData - Complete analysis data including graph, metadata, etc.
     * @returns {Promise<boolean>} Success status
     */
    saveCaseFile: async (fileName, analysisData) => {
        try {
            // Ensure filename has proper format
            const caseFileName = fileName.startsWith('CASE-') ? fileName : `CASE-${fileName}`;
            
            // Prepare case file structure
            const caseData = {
                caseId: caseFileName.replace('.json', ''),
                fileName: caseFileName,
                timestamp: Date.now(),
                generatedAt: new Date().toISOString(),
                metadata: {
                    caseId: caseFileName.replace('.json', ''),
                    totalAccounts: analysisData.graph?.nodes?.length || 0,
                    totalTransactions: analysisData.graph?.edges?.length || 0,
                    riskScore: analysisData.risk?.clusterRiskScore || analysisData.metadata?.riskScore || 0,
                    riskBand: analysisData.risk?.clusterRiskBand || analysisData.metadata?.riskBand || 'unknown',
                    analysisType: 'UPI_MULE_DETECTION',
                    version: '1.0'
                },
                graph: analysisData.graph || {},
                communities: analysisData.communities || {},
                risk: analysisData.risk || {},
                counterparties: analysisData.counterparties || {},
                forensicData: analysisData.forensicData || {},
                settings: analysisData.settings || {}
            };

            const response = await fetch(`/api/upi-cases/save`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ case_data: caseData })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            console.log('[CASE_FILE_MANAGER] Case saved successfully:', result);
            
            // Also save to localStorage for backward compatibility
            if (typeof window !== 'undefined') {
                const event = new CustomEvent('caseFileSaved', { 
                    detail: { fileName: caseFileName, caseId: caseData.caseId } 
                });
                window.dispatchEvent(event);
            }

            return true;
        } catch (error) {
            console.error('[CASE_FILE_MANAGER] Error saving case file:', error);
            throw error;
        }
    },

    /**
     * Load a UPI-Case file from the data/cases folder
     * @param {string} fileName - Name of the case file to load
     * @returns {Promise<Object|null>} Case data or null if not found
     */
    loadCaseFile: async (fileName) => {
        try {
            const caseFileName = fileName.startsWith('CASE-') ? fileName : `CASE-${fileName}`;
            
            const response = await fetch(`/api/upi-cases/${encodeURIComponent(caseFileName)}`);
            
            if (!response.ok) {
                if (response.status === 404) {
                    console.warn(`[CASE_FILE_MANAGER] Case file not found: ${caseFileName}`);
                    return null;
                }
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const caseData = await response.json();
            console.log(`[CASE_FILE_MANAGER] Case loaded successfully: ${caseFileName}`);
            
            return { data: caseData };
        } catch (error) {
            console.error('[CASE_FILE_MANAGER] Error loading case file:', error);
            throw error;
        }
    },

    /**
     * Get list of all available case files
     * @returns {Promise<Array>} List of case file metadata
     */
    listCaseFiles: async () => {
        try {
            const response = await fetch(`/api/upi-cases`);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const res = await response.json();
            const mappedCases = (res?.cases || []).map(c => ({
                ...c,
                totalAccounts: c?.metadata?.totalAccounts ?? 0,
                totalTransactions: c?.metadata?.totalTransactions ?? 0,
            }));

            const cases = { ...(res || {}), cases: mappedCases };

            console.log('[CASE_FILE_MANAGER] Case files listed:', mappedCases.length);
            
            return cases;
        } catch (error) {
            console.error('[CASE_FILE_MANAGER] Error listing case files:', error);
            throw error;
        }
    },

    /**
     * Delete a case file
     * @param {string} fileName - Name of the case file to delete
     * @returns {Promise<boolean>} Success status
     */
    deleteCaseFile: async (fileName) => {
        try {
            const caseFileName = fileName.startsWith('CASE-') ? fileName : `CASE-${fileName}`;
            
            const response = await fetch(`/api/upi-cases/${encodeURIComponent(caseFileName)}`, {
                method: 'DELETE'
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            console.log('[CASE_FILE_MANAGER] Case deleted successfully:', result);
            
            // Notify components
            if (typeof window !== 'undefined') {
                const event = new CustomEvent('caseFileDeleted', { 
                    detail: { fileName: caseFileName } 
                });
                window.dispatchEvent(event);
            }

            return true;
        } catch (error) {
            console.error('[CASE_FILE_MANAGER] Error deleting case file:', error);
            throw error;
        }
    },

    /**
     * Generate a unique case filename
     * @param {string} prefix - Optional prefix for the filename
     * @returns {string} Generated case filename
     */
    generateCaseFileName: (prefix = '') => {
        const timestamp = Date.now();
        const randomSuffix = Math.random().toString(36).substring(2, 8);
        const cleanPrefix = prefix.replace(/[^a-zA-Z0-9]/g, '').substring(0, 20);
        
        return cleanPrefix 
            ? `CASE-${cleanPrefix}-${timestamp}-${randomSuffix}.json`
            : `CASE-${timestamp}-${randomSuffix}.json`;
    },

    /**
     * Validate case file structure
     * @param {Object} caseData - Case data to validate
     * @returns {boolean} True if valid
     */
    validateCaseFile: (caseData) => {
        try {
            const required = ['caseId', 'fileName', 'timestamp', 'metadata'];
            return required.every(field => caseData.hasOwnProperty(field));
        } catch (error) {
            console.error('[CASE_FILE_MANAGER] Error validating case file:', error);
            return false;
        }
    }
};

export default CaseFileManager;
