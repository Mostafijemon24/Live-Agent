import Link from "next/link";

export default function NotFound() {
  return (
    <div data-screen-label="Not found" className="flex min-h-[60vh] flex-col items-center justify-center gap-2.5 p-6 text-center">
      <span className="font-mono text-[13px] text-primary">404</span>
      <h1 className="text-[26px] font-semibold tracking-[-.015em]">This page doesn&apos;t exist</h1>
      <p className="max-w-[420px] text-muted">The link may be old, or the item may have been removed. Nothing in your workspace was changed.</p>
      <div className="mt-2 flex gap-2">
        <Link href="/overview" className="inline-flex h-[38px] items-center rounded-lg bg-primary px-3.5 text-sm font-medium text-white hover:bg-primary-hover hover:text-white hover:no-underline">
          Go to overview
        </Link>
        <Link href="/help" className="inline-flex h-[38px] items-center rounded-lg border border-line-strong bg-surface px-3.5 text-sm font-medium text-ink hover:bg-subtle hover:text-ink hover:no-underline">
          Get help
        </Link>
      </div>
    </div>
  );
}
