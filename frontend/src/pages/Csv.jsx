import { ArrowDownUp, ShieldCheck } from "lucide-react";

export default function Csv() {
  return (
    <div className="space-y-5">
      <div><h1 className="font-heading text-3xl font-bold tracking-tight">CSV Import / Export</h1>
        <p className="mt-1 text-sm text-muted-foreground">Safe import with validation preview. Only SEO columns accepted; commerce columns rejected.</p></div>
      <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-24 text-center">
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/15"><ArrowDownUp className="h-6 w-6 text-primary" /></div>
        <h2 className="font-heading text-xl font-semibold">Phase 4 — CSV Tools</h2>
        <p className="mt-2 max-w-md text-sm text-muted-foreground">
          Export filtered products (shopify_product_id, handle, current/new SEO title & meta, score, issue_codes) and import
          with a Ready/Warnings/Errors preview. Forbidden columns (price, inventory, SKU, product title) will be rejected.
        </p>
        <div className="mt-4 flex items-center gap-1.5 text-xs text-emerald-400"><ShieldCheck className="h-3.5 w-3.5" /> CSV can never modify non-SEO fields.</div>
      </div>
    </div>
  );
}
