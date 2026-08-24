import { Globe } from "lucide-react";

export default function SerpPreview({ title, description, handle, testid }) {
  const url = `urbandotted.com › products › ${handle || "product-handle"}`;
  const displayTitle = (title || "Your SEO title preview will appear here").slice(0, 65);
  const truncTitle = title && title.length > 60;
  const displayDesc = (description || "Your meta description preview will appear here. It updates live as you type.").slice(0, 170);
  const truncDesc = description && description.length > 160;
  return (
    <div data-testid={testid} className="rounded-lg border border-border bg-card p-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">SERP Preview</span>
      </div>
      <div className="rounded-md bg-white p-4 dark:bg-[#1f1f1f]">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-200 dark:bg-slate-700">
            <Globe className="h-3.5 w-3.5 text-slate-500" />
          </div>
          <div className="leading-tight">
            <div className="text-[13px] text-slate-800 dark:text-slate-200">UrbanDotted</div>
            <div className="text-[12px] text-slate-500 dark:text-slate-400">{url}</div>
          </div>
        </div>
        <div className="mt-1 text-[18px] leading-6 text-[#1a0dab] hover:underline dark:text-[#8ab4f8]">
          {displayTitle}{truncTitle ? "…" : ""}
        </div>
        <div className="mt-1 text-[13px] leading-5 text-slate-600 dark:text-slate-400">
          {displayDesc}{truncDesc ? "…" : ""}
        </div>
      </div>
      <p className="mt-2 text-[11px] text-muted-foreground">
        Preview only — Google may rewrite titles and snippets.
      </p>
    </div>
  );
}
