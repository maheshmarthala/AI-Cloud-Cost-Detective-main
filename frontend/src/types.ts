export interface Issue { resource_name: string; issue_type: string; severity: 'high'|'medium'|'low'; explanation: string; estimated_savings: string; fix_command: string }
export interface Analysis { id: string; scope: string; scan_config: ScanConfig | null; resources_scanned: number; issues_found: number; estimated_savings: string; status: string; created_at: string; analysis_result: { summary?: string; issues?: Issue[]; limitations?: string[]; error?: string } }
export interface ProgressEvent { message: string; status: string }

export interface ScanConfig { account_id: string; regions: string[]; services: string[]; tag_filters: Record<string,string> }
export interface ScanOptions { account_id: string; regions: string[]; services: string[]; default_region: string; warnings: string[] }
