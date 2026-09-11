import { LoadingState } from "@/components/ui/Primitives";

export default function Loading() {
  return (
    <main id="main-content" className="app-container py-8">
      <LoadingState label="Loading workspace" />
    </main>
  );
}
