import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OmniOps — Evidence-Grounded Business Intelligence Platform",
  description: "Evidence-grounded investigation workspace for enterprise business intelligence.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body
        suppressHydrationWarning
        className="min-h-screen bg-[#07090e] text-slate-100 antialiased selection:bg-blue-500/20 selection:text-blue-200"
      >
        {children}
      </body>
    </html>
  );
}
