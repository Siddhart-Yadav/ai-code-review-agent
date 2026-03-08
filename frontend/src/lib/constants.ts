/**
 * Shared UI constants — single source of truth for color mappings across components.
 */

export const SEVERITY_COLORS: Record<string, string> = {
  critical: "bg-red-500/20 text-red-400 border-red-500/30",
  high: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  medium: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  low: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  info: "bg-slate-500/20 text-slate-400 border-slate-500/30",
};

export const STATUS_COLORS: Record<string, string> = {
  completed: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  in_progress: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  failed: "bg-red-500/20 text-red-400 border-red-500/30",
  pending: "bg-slate-500/20 text-slate-400 border-slate-500/30",
};

export const RECOMMENDATION_COLORS: Record<string, string> = {
  approve: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  comment: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  request_changes: "bg-red-500/20 text-red-400 border-red-500/30",
};

export const RECOMMENDATION_LABELS: Record<string, string> = {
  approve: "Approve",
  comment: "Comment",
  request_changes: "Request Changes",
};

export const RISK_COLORS: Record<string, string> = {
  low: "bg-emerald-500/20 text-emerald-400",
  medium: "bg-amber-500/20 text-amber-400",
  high: "bg-red-500/20 text-red-400",
};

export const CATEGORY_ICONS: Record<string, string> = {
  security: "shield",
  performance: "zap",
  style: "palette",
  test_coverage: "flask",
};
