"use client";

import { Badge } from "@/components/ui/badge";
import type { Finding } from "@/lib/api";
import { SEVERITY_COLORS } from "@/lib/constants";

interface FindingsListProps {
  findings: Finding[];
  category: string;
}

const categoryIcons: Record<string, string> = {
  security: "🛡️",
  performance: "⚡",
  style: "🎨",
  test_coverage: "🧪",
};

export function FindingsList({ findings, category }: FindingsListProps) {
  if (!findings.length) {
    return (
      <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
        <span className="text-lg">✓</span>
        No {category.replace("_", " ")} issues found
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {findings.map((finding, i) => (
        <div
          key={`${finding.file ?? ""}-${finding.line_start ?? ""}-${finding.title ?? i}`}
          className="rounded-lg border border-border bg-card p-4 transition-colors hover:bg-accent/50"
          role="article"
          aria-label={`${finding.severity ?? "info"} finding: ${finding.title ?? "Finding"}`}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-start gap-2">
              <span className="mt-0.5 text-base">
                {categoryIcons[category] || "📋"}
              </span>
              <div className="space-y-1">
                <p className="text-sm font-medium leading-tight">
                  {finding.title || "Finding"}
                </p>
                <p className="text-sm text-muted-foreground">
                  {finding.description || "No description"}
                </p>
                {finding.suggestion && (
                  <div className="mt-2 rounded border border-emerald-500/20 bg-emerald-500/5 p-2">
                    <p className="text-xs font-medium text-emerald-400">
                      Suggestion
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {finding.suggestion}
                    </p>
                  </div>
                )}
              </div>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1.5">
              <Badge
                variant="outline"
                className={
                  SEVERITY_COLORS[finding.severity || "info"] || SEVERITY_COLORS.info
                }
                aria-label={`Severity: ${finding.severity || "info"}`}
              >
                {finding.severity || "info"}
              </Badge>
              {finding.file && (
                <span className="text-xs text-muted-foreground">
                  {finding.file}
                  {finding.line_start ? `:${finding.line_start}` : ""}
                </span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
