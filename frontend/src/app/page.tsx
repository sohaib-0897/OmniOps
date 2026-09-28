import type { Metadata } from "next";
import { LandingV2 } from "@/components/landing/LandingV2";
import "@/components/landing/landing-v2.css";

export const metadata: Metadata = {
  title: "OmniOps — Follow the evidence",
  description: "Investigate documents, tables, images and audio. Trace each conclusion through its evidence to the source passage.",
};

export default function LandingPage() {
  return <LandingV2 />;
}
