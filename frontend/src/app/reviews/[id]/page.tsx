"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { ScoreRing } from "@/components/score-ring";
import { FindingsList } from "@/components/findings-list";
import { getReview, type ReviewResponse, type MetaReview } from "@/lib/api";
import {
  RECOMMENDATION_COLORS,
  RECOMMENDATION_LABELS,
  RISK_COLORS,
} from "@/lib/constants";

export default function ReviewDetailPage() {
  const params = useParams();
  const [review, setReview] = useState<ReviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params.id) return;
    const id = Array.isArray(params.id) ? params.id[0] : params.id;

    getReview(id)
      .then(setReview)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [params.id]);

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <div className="grid grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error || !review) {
    return (
      <Card className="border-red-500/30 bg-red-500/5">
        <CardContent className="pt-6">
          <p className="text-red-400">{error || "Review not found"}</p>
        </CardContent>
      </Card>
    );
  }

  const meta: MetaReview = review.meta_review ?? {};
  const keyIssues = meta.key_issues ?? [];
  const positives = meta.positive_aspects ?? [];
  const risk = meta.risk_assessment ?? "unknown";
  const recKey = review.recommendation || "comment";
  const rec = {
    label: RECOMMENDATION_LABELS[recKey] || "Comment",
    className: RECOMMENDATION_COLORS[recKey] || RECOMMENDATION_COLORS.comment,
  };

  const agentTabs = [
    {
      value: "security",
      label: "Security",
      icon: "🛡️",
      findings: review.security_findings,
    },
    {
      value: "performance",
      label: "Performance",
      icon: "⚡",
      findings: review.performance_findings,
    },
    {
      value: "style",
      label: "Style",
      icon: "🎨",
      findings: review.style_findings,
    },
    {
      value: "test_coverage",
      label: "Tests",
      icon: "🧪",
      findings: review.test_coverage_findings,
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight">
              {review.repo_full_name}
            </h1>
            <span className="text-xl text-muted-foreground">
              #{review.pr_number}
            </span>
          </div>
          <p className="mt-1 text-muted-foreground">
            {review.pr_title || "Untitled PR"}
          </p>
          {review.pr_url && (
            <a
              href={review.pr_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 inline-block text-sm text-primary hover:underline"
            >
              View on GitHub →
            </a>
          )}
        </div>
        <Badge variant="outline" className={rec.className}>
          {rec.label}
        </Badge>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="flex items-center gap-4 pt-6">
            <ScoreRing score={review.overall_score || 0} />
            <div>
              <p className="text-sm font-medium">Overall Score</p>
              <p className="text-xs text-muted-foreground">out of 10</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-3xl font-bold">{review.total_issues}</p>
            <p className="text-sm text-muted-foreground">Issues Found</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-3xl font-bold">{review.files_reviewed}</p>
            <p className="text-sm text-muted-foreground">Files Reviewed</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-3xl font-bold">
              {review.duration_seconds
                ? `${review.duration_seconds.toFixed(1)}s`
                : "—"}
            </p>
            <p className="text-sm text-muted-foreground">Duration</p>
          </CardContent>
        </Card>
      </div>

      {review.summary && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Summary</CardTitle>
            <CardDescription>
              Risk:{" "}
              <Badge
                variant="outline"
                className={RISK_COLORS[risk] || RISK_COLORS.high}
                aria-label={`Risk level: ${risk}`}
              >
                {risk}
              </Badge>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm leading-relaxed">{review.summary}</p>

            {keyIssues.length > 0 && (
              <div>
                <p className="mb-2 text-sm font-semibold text-red-400">
                  Key Issues
                </p>
                <ul className="space-y-1">
                  {keyIssues.map((issue) => (
                    <li
                      key={issue}
                      className="flex items-start gap-2 text-sm text-muted-foreground"
                    >
                      <span className="mt-1 text-red-400" aria-hidden="true">•</span>
                      {issue}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {positives.length > 0 && (
              <div>
                <p className="mb-2 text-sm font-semibold text-emerald-400">
                  Positive Aspects
                </p>
                <ul className="space-y-1">
                  {positives.map((pos) => (
                    <li
                      key={pos}
                      className="flex items-start gap-2 text-sm text-muted-foreground"
                    >
                      <span className="mt-1 text-emerald-400" aria-hidden="true">+</span>
                      {pos}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <Separator />

      <Tabs defaultValue="security">
        <TabsList className="w-full justify-start">
          {agentTabs.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value} className="gap-1.5">
              <span>{tab.icon}</span>
              {tab.label}
              {tab.findings.length > 0 && (
                <Badge
                  variant="secondary"
                  className="ml-1 h-5 min-w-[20px] px-1.5 text-xs"
                >
                  {tab.findings.length}
                </Badge>
              )}
            </TabsTrigger>
          ))}
        </TabsList>
        {agentTabs.map((tab) => (
          <TabsContent key={tab.value} value={tab.value} className="mt-4">
            <FindingsList findings={tab.findings} category={tab.value} />
          </TabsContent>
        ))}
      </Tabs>

      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <span>
          Triggered by:{" "}
          <Badge variant="outline" className="text-xs">
            {review.triggered_by || "unknown"}
          </Badge>
        </span>
        {review.created_at && (
          <span>Created: {new Date(review.created_at).toLocaleString()}</span>
        )}
        {review.completed_at && (
          <span>
            Completed: {new Date(review.completed_at).toLocaleString()}
          </span>
        )}
      </div>
    </div>
  );
}
