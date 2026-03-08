"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { submitReview } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  const [prUrl, setPrUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [demoLoading, setDemoLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!prUrl.match(/https?:\/\/github\.com\/[^/]+\/[^/]+\/pull\/\d+/)) {
      setError("Please enter a valid GitHub PR URL");
      return;
    }

    setLoading(true);
    try {
      const review = await submitReview(prUrl);
      router.push(`/reviews/${review.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit review");
    } finally {
      setLoading(false);
    }
  };

  const handleTryDemo = () => {
    setDemoLoading(true);
    router.push("/reviews/demo-review-001");
  };

  return (
    <div className="flex flex-col items-center gap-12 pt-8">
      <div className="space-y-4 text-center">
        <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
          AI Code Review Agent
        </h1>
        <p className="mx-auto max-w-xl text-lg text-muted-foreground">
          Multi-agent system powered by LangGraph. Analyzes pull requests for
          security, performance, style, and test coverage issues in parallel.
          Supports Groq (Llama 3.3), Gemini, OpenAI, and Anthropic.
        </p>
        <div className="flex items-center justify-center gap-2">
          <Badge variant="secondary">LangGraph</Badge>
          <Badge variant="secondary">Groq / Llama 3.3</Badge>
          <Badge variant="secondary">Gemini</Badge>
          <Badge variant="secondary">OpenAI</Badge>
          <Badge variant="secondary">Anthropic</Badge>
          <Badge variant="secondary">FastAPI</Badge>
        </div>
      </div>

      <Card className="w-full max-w-2xl">
        <CardHeader>
          <CardTitle>Review a Pull Request</CardTitle>
          <CardDescription>
            Paste a GitHub PR URL to run a multi-agent code review. Typically
            takes 30-90 seconds.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              placeholder="https://github.com/owner/repo/pull/123"
              value={prUrl}
              onChange={(e) => setPrUrl(e.target.value)}
              disabled={loading}
              className="h-12 text-base"
            />
            {error && <p className="text-sm text-red-400">{error}</p>}
            <div className="flex gap-3">
              <Button
                type="submit"
                className="h-12 flex-1 text-base"
                disabled={loading || !prUrl.trim()}
              >
                {loading ? (
                  <span className="flex items-center gap-2">
                    <svg
                      className="h-4 w-4 animate-spin"
                      viewBox="0 0 24 24"
                      fill="none"
                    >
                      <circle
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                        className="opacity-25"
                      />
                      <path
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                        fill="currentColor"
                        className="opacity-75"
                      />
                    </svg>
                    Analyzing PR...
                  </span>
                ) : (
                  "Start Review"
                )}
              </Button>
              <Button
                type="button"
                variant="outline"
                className="h-12 text-base"
                onClick={handleTryDemo}
                disabled={demoLoading}
              >
                {demoLoading ? "Loading..." : "Try Demo"}
              </Button>
            </div>
            <p className="text-center text-xs text-muted-foreground">
              No API key? Click <strong>Try Demo</strong> to see a real review
              of a freeCodeCamp PR.
            </p>
          </form>
        </CardContent>
      </Card>

      <div className="grid w-full max-w-4xl grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          {
            icon: "🛡️",
            title: "Security",
            desc: "SQL injection, XSS, hardcoded secrets, auth flaws",
          },
          {
            icon: "⚡",
            title: "Performance",
            desc: "N+1 queries, memory leaks, algorithmic complexity",
          },
          {
            icon: "🎨",
            title: "Style",
            desc: "Naming, DRY, SOLID principles, readability",
          },
          {
            icon: "🧪",
            title: "Test Coverage",
            desc: "Missing tests, edge cases, assertion quality",
          },
        ].map((agent) => (
          <Card
            key={agent.title}
            className="border-border/50 bg-card/50 backdrop-blur"
          >
            <CardContent className="pt-6">
              <div className="mb-2 text-2xl">{agent.icon}</div>
              <h3 className="font-semibold">{agent.title} Agent</h3>
              <p className="mt-1 text-xs text-muted-foreground">{agent.desc}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="w-full max-w-4xl border-border/30 bg-card/30">
        <CardContent className="pt-6">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Architecture
          </h3>
          <div className="flex flex-wrap items-center justify-center gap-2 text-sm">
            <Badge variant="outline">PR Diff</Badge>
            <span className="text-muted-foreground">→</span>
            <Badge variant="outline">Smart Chunking</Badge>
            <span className="text-muted-foreground">→</span>
            <div className="flex gap-1">
              <Badge className="bg-red-500/20 text-red-400">Security</Badge>
              <Badge className="bg-amber-500/20 text-amber-400">Perf</Badge>
              <Badge className="bg-blue-500/20 text-blue-400">Style</Badge>
              <Badge className="bg-emerald-500/20 text-emerald-400">Tests</Badge>
            </div>
            <span className="text-muted-foreground">→</span>
            <Badge variant="outline">Aggregator</Badge>
            <span className="text-muted-foreground">→</span>
            <Badge variant="outline">Meta Reviewer</Badge>
            <span className="text-muted-foreground">→</span>
            <Badge className="bg-primary/20 text-primary">Report</Badge>
          </div>
          <p className="mt-3 text-center text-xs text-muted-foreground">
            4 specialist agents run in parallel via LangGraph fan-out, then
            converge through aggregation and meta-review
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
