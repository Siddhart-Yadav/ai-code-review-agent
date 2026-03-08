"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { listReviews, type ReviewListItem } from "@/lib/api";
import { STATUS_COLORS, RECOMMENDATION_COLORS } from "@/lib/constants";

export default function ReviewsPage() {
  const router = useRouter();
  const [reviews, setReviews] = useState<ReviewListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listReviews()
      .then(setReviews)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Review History</h1>
        <p className="mt-1 text-muted-foreground">
          All pull request reviews performed by the agent
        </p>
      </div>

      {error && (
        <Card className="border-red-500/30 bg-red-500/5">
          <CardContent className="pt-6">
            <p className="text-sm text-red-400">{error}</p>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-lg" />
          ))}
        </div>
      ) : reviews.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-12">
            <p className="text-lg font-medium">No reviews yet</p>
            <p className="text-sm text-muted-foreground">
              Submit a PR URL to create your first review
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {reviews.map((review) => (
            <Card
              key={review.id}
              className="cursor-pointer transition-colors hover:bg-accent/50"
              onClick={() => router.push(`/reviews/${review.id}`)}
            >
              <CardContent className="flex items-center gap-4 py-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-bold">
                  {review.overall_score != null
                    ? review.overall_score.toFixed(1)
                    : "—"}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-sm font-medium">
                      {review.repo_full_name}
                      <span className="text-muted-foreground">
                        #{review.pr_number}
                      </span>
                    </p>
                  </div>
                  <p className="truncate text-sm text-muted-foreground">
                    {review.pr_title || "Untitled PR"}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Badge
                    variant="outline"
                    className={STATUS_COLORS[review.status] || STATUS_COLORS.pending}
                    aria-label={`Status: ${review.status}`}
                  >
                    {review.status}
                  </Badge>
                  {review.recommendation && (
                    <Badge
                      variant="outline"
                      className={
                        RECOMMENDATION_COLORS[review.recommendation] || RECOMMENDATION_COLORS.comment
                      }
                    >
                      {review.recommendation}
                    </Badge>
                  )}
                  <span className="text-xs text-muted-foreground">
                    {review.total_issues} issues
                  </span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
