import type { Metadata } from "next";
import { DM_Sans, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const display = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

const body = DM_Sans({
  subsets: ["latin"],
  variable: "--font-body",
  display: "swap",
});

export const metadata: Metadata = {
  title: "SENTINEL | BESCOM Smart Grid Intelligence",
  description:
    "Smart Energy Network Theft & Efficiency Intelligence Layer — AI for Smart Meter Intelligence & Loss Detection",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${display.variable} ${body.variable} min-h-screen bg-[#0A0E1A] text-[#E8EDF5]`}>
        {children}
      </body>
    </html>
  );
}
