// @ts-nocheck
"use client";
import React, { useState } from 'react';
import { Download, FileText, AlertTriangle } from 'lucide-react';
import { jsPDF } from 'jspdf';
import 'jspdf-autotable';

/**
 * CaseExportButton Component
 * Generates PDF case reports with all UPI IDs, transaction volumes,
 * and layering accounts for detected fraudulent communities.
 */
const CaseExportButton = ({
    communityData,
    graphData,
    analysisMetadata = {},
    className = ''
}) => {
    const [isExporting, setIsExporting] = useState(false);
    const [error, setError] = useState(null);

    const generatePDFReport = async () => {
        try {
            setIsExporting(true);
            setError(null);

            // Create new PDF document
            const doc = new jsPDF();
            const pageWidth = doc.internal.pageSize.getWidth();
            const pageHeight = doc.internal.pageSize.getHeight();
            let yPos = 20;

            // Helper to add new page if needed
            const checkPageBreak = (requiredSpace = 20) => {
                if (yPos + requiredSpace > pageHeight - 20) {
                    doc.addPage();
                    yPos = 20;
                    return true;
                }
                return false;
            };

            // ===== HEADER =====
            doc.setFillColor(15, 23, 42);
            doc.rect(0, 0, pageWidth, 40, 'F');

            doc.setTextColor(59, 130, 246);
            doc.setFontSize(24);
            doc.setFont('helvetica', 'bold');
            doc.text('FRAUD CASE REPORT', pageWidth / 2, 20, { align: 'center' });

            doc.setFontSize(10);
            doc.setTextColor(148, 163, 184);
            doc.text('ChainBreak UPI Mule Detection System', pageWidth / 2, 28, { align: 'center' });

            yPos = 50;

            // ===== CASE METADATA =====
            doc.setFillColor(30, 41, 59);
            doc.roundedRect(14, yPos, pageWidth - 28, 30, 3, 3, 'F');

            doc.setFontSize(9);
            doc.setTextColor(226, 232, 240);
            doc.setFont('helvetica', 'normal');

            const caseId = analysisMetadata.caseId || `CASE-${Date.now()}`;
            const timestamp = new Date().toLocaleString();
            const totalNodes = graphData?.nodes?.length || 0;
            const totalEdges = graphData?.edges?.length || 0;

            doc.text(`Case ID: ${caseId}`, 20, yPos + 10);
            doc.text(`Generated: ${timestamp}`, 20, yPos + 17);
            doc.text(`Network Size: ${totalNodes} accounts, ${totalEdges} transactions`, 20, yPos + 24);

            yPos += 40;

            // ===== EXECUTIVE SUMMARY =====
            checkPageBreak(40);

            doc.setFontSize(14);
            doc.setTextColor(239, 68, 68);
            doc.setFont('helvetica', 'bold');
            doc.text('EXECUTIVE SUMMARY', 14, yPos);
            yPos += 10;

            const suspiciousCommunities = communityData ?
                Object.values(communityData).filter(c => c.suspicion_score > 3).length : 0;
            const totalAccounts = graphData?.nodes?.length || 0;
            const totalVolume = (graphData?.edges || []).reduce((sum, e) => sum + (e.amount || 0), 0);

            doc.setFontSize(10);
            doc.setTextColor(226, 232, 240);
            doc.setFont('helvetica', 'normal');

            const summary = [
                `• ${suspiciousCommunities} suspicious communities detected`,
                `• ${totalAccounts} UPI accounts involved`,
                `• Total transaction volume: ₹${totalVolume.toLocaleString()}`,
                `• Analysis completed: ${timestamp}`
            ];

            summary.forEach(line => {
                doc.text(line, 20, yPos);
                yPos += 7;
            });

            yPos += 10;

            // ===== DETAILED COMMUNITY ANALYSIS =====
            if (communityData && Object.keys(communityData).length > 0) {
                checkPageBreak(40);

                doc.setFontSize(14);
                doc.setTextColor(249, 115, 22);
                doc.setFont('helvetica', 'bold');
                doc.text('DETAILED COMMUNITY ANALYSIS', 14, yPos);
                yPos += 12;

                // Sort communities by suspicion score
                const sortedCommunities = Object.entries(communityData)
                    .sort(([, a], [, b]) => (b.suspicion_score || 0) - (a.suspicion_score || 0));

                for (const [commId, comm] of sortedCommunities) {
                    checkPageBreak(60);

                    // Community header
                    doc.setFillColor(51, 65, 85);
                    doc.roundedRect(14, yPos, pageWidth - 28, 8, 2, 2, 'F');

                    doc.setFontSize(11);
                    doc.setTextColor(234, 179, 8);
                    doc.setFont('helvetica', 'bold');
                    doc.text(`Community ${commId} - Risk Score: ${(comm.avg_risk_score || 0).toFixed(1)}`, 20, yPos + 5.5);
                    yPos += 12;

                    // Community metrics
                    doc.setFontSize(9);
                    doc.setTextColor(203, 213, 225);
                    doc.setFont('helvetica', 'normal');

                    const metrics = [
                        `Members: ${comm.member_count}`,
                        `Total Amount: ₹${(comm.total_amount || 0).toLocaleString()}`,
                        `Transactions: ${comm.total_transactions}`,
                        `Density: ${(comm.density || 0).toFixed(3)}`,
                        `Velocity: ${(comm.daily_velocity || 0).toFixed(1)} tx/day`,
                        `Avg In/Out Ratio: ${(comm.avg_in_out_ratio || 0).toFixed(2)}`
                    ];

                    // Display in 2 columns
                    metrics.forEach((metric, idx) => {
                        const col = idx % 2;
                        const row = Math.floor(idx / 2);
                        doc.text(metric, 20 + (col * 90), yPos + (row * 6));
                    });

                    yPos += 20;

                    // Suspicious indicators
                    if (comm.suspicious_indicators && Object.keys(comm.suspicious_indicators).length > 0) {
                        doc.setFontSize(9);
                        doc.setTextColor(251, 146, 60);
                        doc.setFont('helvetica', 'bold');
                        doc.text('Suspicious Indicators:', 20, yPos);
                        yPos += 6;

                        doc.setFont('helvetica', 'normal');
                        doc.setTextColor(252, 165, 165);

                        Object.entries(comm.suspicious_indicators).forEach(([key, value]) => {
                            if (value) {
                                doc.text(`✓ ${key.replace(/_/g, ' ').toUpperCase()}`, 25, yPos);
                                yPos += 5;
                            }
                        });
                        yPos += 3;
                    }

                    // Layering accounts (high betweenness centrality)
                    if (comm.betweenness_scores && Object.keys(comm.betweenness_scores).length > 0) {
                        checkPageBreak(30);

                        const layeringAccounts = Object.entries(comm.betweenness_scores)
                            .sort(([, a], [, b]) => b - a)
                            .slice(0, 5);

                        if (layeringAccounts.length > 0) {
                            doc.setFontSize(9);
                            doc.setTextColor(147, 51, 234);
                            doc.setFont('helvetica', 'bold');
                            doc.text('Primary Layering Accounts (High Betweenness):', 20, yPos);
                            yPos += 6;

                            doc.setFont('helvetica', 'normal');
                            doc.setTextColor(203, 213, 225);
                            doc.setFontSize(8);

                            layeringAccounts.forEach(([accountId, betweenness]) => {
                                doc.text(`${accountId}: ${betweenness.toFixed(4)}`, 25, yPos);
                                yPos += 5;
                            });

                            yPos += 5;
                        }
                    }

                    // List all UPI IDs in this community
                    if (comm.members && comm.members.length > 0) {
                        checkPageBreak(30);

                        doc.setFontSize(9);
                        doc.setTextColor(100, 116, 139);
                        doc.setFont('helvetica', 'italic');
                        doc.text(`All ${comm.members.length} UPI IDs in this community:`, 20, yPos);
                        yPos += 6;

                        doc.setFontSize(7);
                        doc.setFont('helvetica', 'normal');

                        // Display in columns
                        const idsPerColumn = 15;
                        const columnWidth = 60;
                        let currentCol = 0;
                        let currentRow = 0;

                        comm.members.forEach((memberId, idx) => {
                            if (currentRow >= idsPerColumn) {
                                currentRow = 0;
                                currentCol++;
                            }

                            if (currentCol > 2) {
                                // Need new page
                                checkPageBreak(30);
                                currentCol = 0;
                                currentRow = 0;
                            }

                            const xPos = 25 + (currentCol * columnWidth);
                            const yOffset = currentRow * 4;

                            doc.text(`${idx + 1}. ${memberId}`, xPos, yPos + yOffset);
                            currentRow++;
                        });

                        yPos += Math.ceil(Math.min(comm.members.length, idsPerColumn) * 4) + 10;
                    }

                    yPos += 5;
                }
            }

            // ===== RECOMMENDATIONS =====
            checkPageBreak(50);

            doc.setFontSize(14);
            doc.setTextColor(34, 197, 94);
            doc.setFont('helvetica', 'bold');
            doc.text('RECOMMENDATIONS', 14, yPos);
            yPos += 10;

            doc.setFontSize(10);
            doc.setTextColor(226, 232, 240);
            doc.setFont('helvetica', 'normal');

            const recommendations = [
                '1. Immediately freeze accounts identified as primary layering accounts',
                '2. Submit Suspicious Transaction Reports (STRs) for all high-risk communities',
                '3. Coordinate with law enforcement for accounts with critical risk scores',
                '4. Monitor related accounts for 90 days for additional suspicious activity',
                '5. Implement enhanced KYC verification for flagged account holders'
            ];

            recommendations.forEach(rec => {
                checkPageBreak(10);
                doc.text(rec, 20, yPos);
                yPos += 7;
            });

            // ===== FOOTER =====
            const pageCount = doc.internal.getNumberOfPages();
            for (let i = 1; i <= pageCount; i++) {
                doc.setPage(i);
                doc.setFontSize(8);
                doc.setTextColor(100, 116, 139);
                doc.text(
                    `Page ${i} of ${pageCount} | Generated by ChainBreak | CONFIDENTIAL`,
                    pageWidth / 2,
                    pageHeight - 10,
                    { align: 'center' }
                );
            }

            // Save the PDF
            const filename = `ChainBreak_Case_${caseId}_${new Date().toISOString().split('T')[0]}.pdf`;
            doc.save(filename);

            setIsExporting(false);
        } catch (err) {
            console.error('PDF generation error:', err);
            setError('Failed to generate PDF report. Please try again.');
            setIsExporting(false);
        }
    };

    return (
        <div className={className}>
            {error && (
                <div style={{
                    padding: '10px 12px',
                    background: 'rgba(239, 68, 68, 0.1)',
                    border: '1px solid rgba(239, 68, 68, 0.25)',
                    borderRadius: '8px',
                    color: '#fca5a5',
                    fontSize: '12px',
                    marginBottom: '12px',
                    display: 'flex',
                    gap: '8px',
                    alignItems: 'center'
                }}>
                    <AlertTriangle size={14} />
                    {error}
                </div>
            )}

            <button
                onClick={generatePDFReport}
                disabled={isExporting || !communityData || !graphData}
                style={{
                    width: '100%',
                    background: isExporting || !communityData || !graphData
                        ? '#1e293b'
                        : 'linear-gradient(135deg, #8b5cf6, #6366f1)',
                    color: isExporting || !communityData || !graphData ? '#64748b' : '#ffffff',
                    fontWeight: '700',
                    padding: '12px 16px',
                    borderRadius: '8px',
                    border: 'none',
                    cursor: isExporting || !communityData || !graphData ? 'not-allowed' : 'pointer',
                    fontSize: '13px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '8px',
                    transition: 'all 0.2s',
                    letterSpacing: '0.02em',
                    boxShadow: isExporting || !communityData || !graphData
                        ? 'none'
                        : '0 4px 12px rgba(139,92,246,0.3)'
                }}
            >
                {isExporting ? (
                    <>
                        <div style={{
                            width: '14px',
                            height: '14px',
                            borderRadius: '50%',
                            border: '2px solid #ffffff',
                            borderTopColor: 'transparent',
                            animation: 'spin 1s linear infinite'
                        }} />
                        Generating PDF...
                    </>
                ) : (
                    <>
                        <FileText size={14} />
                        Export Case Report (PDF)
                    </>
                )}
            </button>

            <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
        </div>
    );
};

export default CaseExportButton;
