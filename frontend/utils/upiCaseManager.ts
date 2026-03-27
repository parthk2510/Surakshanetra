import apiService from './api';

export const UPICaseManager = {
    saveUPICase: async (fileName, analysisData) => {
        const upiFileName = fileName.startsWith('UPI-CASE-') ? fileName : `UPI-CASE-${fileName}`;

        const upiCaseData = {
            caseId: upiFileName.replace('.json', ''),
            fileName: upiFileName,
            timestamp: Date.now(),
            generatedAt: new Date().toISOString(),
            caseType: 'UPI_MULE_DETECTION',
            metadata: {
                totalAccounts: analysisData.graph?.nodes?.length || 0,
                totalTransactions: analysisData.graph?.edges?.length || 0,
                riskScore: analysisData.risk?.clusterRiskScore || analysisData.metadata?.riskScore || 0,
                riskBand: analysisData.risk?.clusterRiskBand || analysisData.metadata?.riskBand || 'unknown',
                analysisType: 'UPI_MULE_DETECTION',
                version: '1.0',
                upiSpecific: true
            },
            graph: analysisData.graph || {},
            communities: analysisData.communities || {},
            risk: analysisData.risk || {},
            counterparties: analysisData.counterparties || {},
            forensicData: analysisData.forensicData || {},
            upiAnalysis: {
                totalInAmount: analysisData.totalInAmount || 0,
                totalOutAmount: analysisData.totalOutAmount || 0,
                inTxCount: analysisData.inTxCount || 0,
                outTxCount: analysisData.outTxCount || 0,
                inUniqueCounterparties: analysisData.inUniqueCounterparties || 0,
                outUniqueCounterparties: analysisData.outUniqueCounterparties || 0,
                componentSize: analysisData.componentSize || 0
            },
            settings: analysisData.settings || {}
        };

        await apiService.post('/api/upi-cases', { case_data: upiCaseData });

        if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('upiCaseSaved', {
                detail: { fileName: upiFileName, caseId: upiCaseData.caseId }
            }));
        }

        return true;
    },

    loadUPICase: async (fileName) => {
        const upiFileName = fileName.startsWith('UPI-CASE-') ? fileName : `UPI-CASE-${fileName}`;
        const caseId = upiFileName.replace('.json', '');
        const data = await apiService.get(`/api/upi-cases/${encodeURIComponent(caseId)}`);
        return data;
    },

    listUPICases: async () => {
        const data = await apiService.get('/api/upi-cases');
        return data;
    },

    deleteUPICase: async (fileName) => {
        const upiFileName = fileName.startsWith('UPI-CASE-') ? fileName : `UPI-CASE-${fileName}`;
        const caseId = upiFileName.replace('.json', '');
        await apiService.delete(`/api/upi-cases/${encodeURIComponent(caseId)}`);

        if (typeof window !== 'undefined') {
            window.dispatchEvent(new CustomEvent('upiCaseDeleted', {
                detail: { fileName: upiFileName }
            }));
        }

        return true;
    },

    generateUPICaseFileName: (prefix = '') => {
        const timestamp = Date.now();
        const randomSuffix = Math.random().toString(36).substring(2, 8);
        const cleanPrefix = prefix.replace(/[^a-zA-Z0-9]/g, '').substring(0, 20);

        return cleanPrefix
            ? `UPI-CASE-${cleanPrefix}-${timestamp}-${randomSuffix}.json`
            : `UPI-CASE-${timestamp}-${randomSuffix}.json`;
    },

    validateUPICase: (caseData) => {
        try {
            const required = ['caseId', 'fileName', 'timestamp', 'metadata', 'caseType'];
            const hasRequired = required.every(field => caseData.hasOwnProperty(field));
            const isUPIType = caseData.caseType === 'UPI_MULE_DETECTION';
            const hasUPIAnalysis = caseData.hasOwnProperty('upiAnalysis');
            return hasRequired && isUPIType && hasUPIAnalysis;
        } catch {
            return false;
        }
    }
};

export default UPICaseManager;
