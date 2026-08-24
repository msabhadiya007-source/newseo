// Client-side SEO helpers (mirror backend recommended ranges for live UX only)

export function lengthStatus(len, min, max) {
  if (len === 0) return { label: "Missing", tone: "critical" };
  if (len < min) return { label: "Too short", tone: "warn" };
  if (len > max) return { label: "Above recommended", tone: "warn" };
  return { label: "Good", tone: "good" };
}

export function progressPercent(len, max) {
  return Math.min(100, Math.round((len / max) * 100));
}

export const toneColor = {
  good: "text-emerald-500",
  warn: "text-amber-500",
  critical: "text-rose-500",
};
export const toneBar = {
  good: "bg-emerald-500",
  warn: "bg-amber-500",
  critical: "bg-rose-500",
};

export const BUCKET_META = {
  missing: { label: "Missing SEO", color: "rose", testid: "missing" },
  critical: { label: "Critical", color: "rose", testid: "critical" },
  needs_improvement: { label: "Needs Improvement", color: "amber", testid: "needs-improvement" },
  good: { label: "Good", color: "emerald", testid: "good" },
  optimised: { label: "Fully Optimised", color: "emerald", testid: "optimised" },
};

export function bucketBadgeClasses(bucket) {
  switch (bucket) {
    case "missing":
    case "critical":
      return "bg-rose-500/15 text-rose-400 border-rose-500/30";
    case "needs_improvement":
      return "bg-amber-500/15 text-amber-400 border-amber-500/30";
    case "good":
      return "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
    case "optimised":
      return "bg-emerald-500/20 text-emerald-300 border-emerald-500/40";
    default:
      return "bg-slate-500/15 text-slate-400 border-slate-500/30";
  }
}

export function scoreColor(score) {
  if (score >= 85) return "#10B981";
  if (score >= 50) return "#F59E0B";
  return "#EF4444";
}
