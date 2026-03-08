const API_BASE = process.env.NEXT_PUBLIC_API_URL || (
  typeof window !== "undefined" && window.location.hostname !== "localhost"
    ? "/api/v1" // production: use relative path
    : "http://localhost:8000/api/v1"
);

export interface ReviewRequest {
  pr_url: string;
  triggered_by?: string;
}

export interface Finding {
  file?: string;
  line_start?: number;
  line_end?: number;
  severity?: string;
  category?: string;
  title?: string;
  description?: string;
  suggestion?: string;
  confidence?: number;
}

export interface MetaReview {
  overall_score?: number;
  recommendation?: string;
  summary?: string;
  key_issues?: string[];
  positive_aspects?: string[];
  risk_assessment?: string;
}

export interface ReviewResponse {
  id: string;
  repo_full_name: string;
  pr_number: number;
  pr_title: string | null;
  pr_url: string | null;
  status: string;
  overall_score: number | null;
  summary: string | null;
  recommendation: string | null;
  security_findings: Finding[];
  performance_findings: Finding[];
  style_findings: Finding[];
  test_coverage_findings: Finding[];
  meta_review: MetaReview;
  files_reviewed: number;
  total_issues: number;
  created_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  triggered_by: string | null;
}

export interface ReviewListItem {
  id: string;
  repo_full_name: string;
  pr_number: number;
  pr_title: string | null;
  status: string;
  overall_score: number | null;
  recommendation: string | null;
  total_issues: number;
  created_at: string | null;
}

export interface HealthResponse {
  status: string;
  version: string;
  database: string;
  redis: string;
}

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API error: ${res.status}`);
  }

  return res.json();
}

export async function submitReview(prUrl: string): Promise<ReviewResponse> {
  return fetchAPI<ReviewResponse>("/reviews", {
    method: "POST",
    body: JSON.stringify({ pr_url: prUrl, triggered_by: "web_ui" }),
  });
}

export async function getReview(id: string): Promise<ReviewResponse> {
  return fetchAPI<ReviewResponse>(`/reviews/${id}`);
}

export async function listReviews(
  skip = 0,
  limit = 20,
  repo?: string
): Promise<ReviewListItem[]> {
  const params = new URLSearchParams({ skip: String(skip), limit: String(limit) });
  if (repo) params.set("repo", repo);
  return fetchAPI<ReviewListItem[]>(`/reviews?${params}`);
}

export async function getHealth(): Promise<HealthResponse> {
  return fetchAPI<HealthResponse>("/health");
}

// ── Demo mode APIs ──────────────────────────────────────────────────────

export interface DemoStatus {
  demo_mode: boolean;
  llm_configured: boolean;
  available_demo_reviews: number;
}

export async function getDemoStatus(): Promise<DemoStatus> {
  return fetchAPI<DemoStatus>("/demo/status");
}

export async function listDemoReviews(): Promise<ReviewListItem[]> {
  return fetchAPI<ReviewListItem[]>("/demo/reviews");
}

export async function getDemoReview(id: string): Promise<ReviewResponse> {
  return fetchAPI<ReviewResponse>(`/demo/reviews/${id}`);
}
