export type ProjectStatus = "draft" | "ready" | "generating" | "completed" | "failed" | "archived";
export type JobStatus = "queued" | "validating" | "preparing" | "submitted" | "processing" | "succeeded" | "failed" | "canceled";

export interface Project {
  id: string; name: string; description: string; status: ProjectStatus; video_ratio: string; duration_seconds: number;
  created_at: string; updated_at: string; archived_at?: string | null; asset_count: number; job_count: number;
  token_usage_status: "available" | "unavailable"; token_total: number; token_input: number; token_output: number;
}
export interface Asset {
  id: string; project_id: string; asset_type: "model" | "clothing"; original_name: string; display_name: string;
  stored_path: string; mime_type: string; file_size: number; sha256: string; width?: number; height?: number;
  slot_index?: number | null; created_at: string; file_url: string; thumbnail_url: string;
}
export interface Job {
  id: string; project_id: string; provider: string; status: JobStatus; progress: number; current_node?: string | null;
  provider_job_id?: string | null; workflow_version: string; error_code?: string | null; error_message?: string | null;
  created_at: string; started_at?: string | null; finished_at?: string | null;
  token_usage_status?: "available" | "unavailable"; token_total?: number; token_input?: number; token_output?: number;
}
export interface VideoOutput { id: string; job_id: string; project_id: string; width: number; height: number; duration: number; file_size: number; sha256: string; video_url: string; thumbnail_url: string; created_at: string; }
export interface GeneratedArtifact { id: string; job_id: string; kind: string; slot_index?: number | null; relative_path: string; mime_type: string; file_size: number; width?: number | null; height?: number | null; duration?: number | null; file_url: string; remote_url?: string | null; }
export interface WorkflowLog { id: string; node_name: string; sequence: number; status: string; input_summary: string; output_summary: string; error_message?: string | null; started_at: string; finished_at?: string | null; }
export interface DashboardSummary { project_count: number; asset_count: number; job_count: number; succeeded_count: number; }
export interface TokenUsage { status: "available" | "unavailable"; has_data: boolean; input_tokens: number; output_tokens: number; total_tokens: number; step_count: number; }
