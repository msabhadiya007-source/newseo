import { Table2, Construction } from "lucide-react";

export default function BulkEditor() {
  return (
    <div className="space-y-5">
      <div><h1 className="font-heading text-3xl font-bold tracking-tight">Bulk Spreadsheet Editor</h1>
        <p className="mt-1 text-sm text-muted-foreground">Server-paginated inline SEO editing for large batches. SEO fields only.</p></div>
      <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-24 text-center">
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/15"><Table2 className="h-6 w-6 text-primary" /></div>
        <h2 className="font-heading text-xl font-semibold">Phase 4 — Bulk Editor</h2>
        <p className="mt-2 max-w-md text-sm text-muted-foreground">
          The spreadsheet grid, batch draft/validate/publish and find-and-replace build on the foundation already in place
          (server-side pagination, SEO-only allowlist, background jobs). Coming in the next phase.
        </p>
        <div className="mt-4 flex items-center gap-1.5 text-xs text-amber-500"><Construction className="h-3.5 w-3.5" /> Editing remains restricted to SEO title, meta & ALT only.</div>
      </div>
    </div>
  );
}
