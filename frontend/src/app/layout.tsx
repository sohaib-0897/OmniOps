import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OmniOps - Evidence-grounded intelligence",
  description:
    "A focused workspace for investigating business questions with traceable evidence.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className="min-h-screen text-zinc-100 antialiased">
        <a href="#main-content" className="skip-link">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
