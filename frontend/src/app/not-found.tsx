import Link from "next/link";
import { BrandMark } from "@/components/ui/Primitives";

export default function NotFound() {
  return (
    <main id="main-content" className="app-container max-w-xl space-y-6 py-16">
      <BrandMark />
      <div className="surface p-6">
        <p className="eyebrow">404</p>
        <h1 className="page-title mt-3">Page not found</h1>
        <p className="body-copy mt-3">
          This page is unavailable. Return to your workspaces to continue.
        </p>
        <Link href="/" className="btn-secondary mt-5">
          All workspaces
        </Link>
      </div>
    </main>
  );
}
