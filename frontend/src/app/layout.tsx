import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import { THEME_BOOTSTRAP_SCRIPT } from "@/lib/theme";
import "./globals.css";

const plexSans = localFont({
  src: [
    { path: "../fonts/ibm-plex-sans-latin-400-normal.woff2", weight: "400", style: "normal" },
    { path: "../fonts/ibm-plex-sans-latin-500-normal.woff2", weight: "500", style: "normal" },
    { path: "../fonts/ibm-plex-sans-latin-600-normal.woff2", weight: "600", style: "normal" },
  ],
  variable: "--font-plex-sans",
  display: "swap",
  fallback: ["system-ui", "Segoe UI", "sans-serif"],
});

const sourceSerif = localFont({
  // wght + opsz axes: auto optical sizing matches the Figma rendering of Source Serif 4.
  src: "../fonts/source-serif-4-latin-opsz-normal.woff2",
  weight: "200 900",
  variable: "--font-source-serif",
  display: "swap",
  fallback: ["Georgia", "Times New Roman", "serif"],
});

const plexMono = localFont({
  src: "../fonts/ibm-plex-mono-latin-400-normal.woff2",
  weight: "400",
  variable: "--font-plex-mono",
  display: "swap",
  fallback: ["ui-monospace", "Consolas", "monospace"],
});

export const metadata: Metadata = {
  title: "OmniOps",
  description: "Every answer, traced to the passage it came from.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#111315" },
    { media: "(prefers-color-scheme: light)", color: "#F6F7F8" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${plexSans.variable} ${sourceSerif.variable} ${plexMono.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Resolves System/Light/Dark before first paint so there is no theme flash. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP_SCRIPT }} />
      </head>
      <body>
        <a href="#main-content" className="skip-link">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
