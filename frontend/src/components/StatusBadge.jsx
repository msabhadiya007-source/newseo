import { bucketBadgeClasses, BUCKET_META } from "@/lib/seo";

export function StatusBadge({ bucket, testid }) {
  const meta = BUCKET_META[bucket] || { label: bucket };
  return (
    <span data-testid={testid}
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${bucketBadgeClasses(bucket)}`}>
      {meta.label}
    </span>
  );
}

export function PubBadge({ status }) {
  const map = {
    draft: "bg-sky-500/15 text-sky-400 border-sky-500/30",
    verified: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    published: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    publishing: "bg-sky-500/15 text-sky-400 border-sky-500/30",
    failed: "bg-rose-500/15 text-rose-400 border-rose-500/30",
    queued: "bg-slate-500/15 text-slate-400 border-slate-500/30",
  };
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${map[status] || map.published}`}>
      {(status || "published").replace(/^\w/, (c) => c.toUpperCase())}
    </span>
  );
}
