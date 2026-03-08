"use client";

interface ScoreRingProps {
  score: number;
  size?: number;
}

export function ScoreRing({ score, size = 80 }: ScoreRingProps) {
  const radius = (size - 8) / 2;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 10) * circumference;
  const remaining = circumference - progress;

  const color =
    score >= 7
      ? "text-emerald-500"
      : score >= 5
        ? "text-amber-500"
        : "text-red-500";

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={4}
          className="text-muted/30"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={4}
          strokeDasharray={`${progress} ${remaining}`}
          strokeLinecap="round"
          className={color}
        />
      </svg>
      <span className={`absolute text-lg font-bold ${color}`}>
        {score.toFixed(1)}
      </span>
    </div>
  );
}
