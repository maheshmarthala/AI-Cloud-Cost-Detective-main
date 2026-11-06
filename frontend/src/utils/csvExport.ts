import type { Analysis, Issue } from '../types';

function escapeCsvCell(value: unknown): string {
  if (value === null || value === undefined) return '""';
  const str = String(value).replace(/"/g, '""');
  return `"${str}"`;
}

/**
 * Converts an Analysis object to a CSV file and triggers a browser download.
 */
export function exportAnalysisToCsv(analysis: Analysis): void {
  const headers = [
    'Resource Name',
    'Issue Type',
    'Severity',
    'Estimated Savings',
    'Explanation',
    'Recommended Fix Command',
    'Account Scope',
    'Regions',
    'Services',
    'Resources Scanned',
    'Issues Found',
    'Scan Date'
  ];

  const issues: Issue[] = analysis.analysis_result?.issues || [];
  const regions = analysis.scan_config?.regions?.join('; ') || 'N/A';
  const services = analysis.scan_config?.services?.join('; ') || 'N/A';
  const scanDate = analysis.created_at ? new Date(analysis.created_at).toLocaleString() : 'N/A';

  const rows: string[][] = [];

  if (issues.length === 0) {
    rows.push([
      'None',
      'No Issues Detected',
      'low',
      '$0.00',
      analysis.analysis_result?.summary || 'No issues identified from the available evidence.',
      'N/A',
      analysis.scope,
      regions,
      services,
      String(analysis.resources_scanned),
      String(analysis.issues_found),
      scanDate
    ]);
  } else {
    for (const issue of issues) {
      rows.push([
        issue.resource_name || 'N/A',
        issue.issue_type || 'N/A',
        issue.severity || 'low',
        issue.estimated_savings || '$0.00',
        issue.explanation || '',
        issue.fix_command || '',
        analysis.scope,
        regions,
        services,
        String(analysis.resources_scanned),
        String(analysis.issues_found),
        scanDate
      ]);
    }
  }

  // Prepend UTF-8 BOM (\uFEFF) so Microsoft Excel opens special characters correctly
  const csvContent = '\uFEFF' + [
    headers.map(escapeCsvCell).join(','),
    ...rows.map(row => row.map(escapeCsvCell).join(','))
  ].join('\r\n');

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;

  const sanitizedScope = analysis.scope.replace(/[^a-zA-Z0-9_-]/g, '_');
  const dateStr = analysis.created_at ? new Date(analysis.created_at).toISOString().split('T')[0] : 'export';
  link.download = `cost-analysis-${sanitizedScope}-${dateStr}.csv`;

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
