import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import { clerkAppearance } from "@/lib/clerk-appearance";
import { isClerkEnabled } from "@/lib/clerk-config";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Ecuery — Ask the planet anything",
  description:
    "Search environmental data in plain English. Sea levels, wildfires, air quality, temperature — answered with real data and charts.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  const page = (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col font-sans">{children}</body>
    </html>
  );

  return isClerkEnabled ? (
    <ClerkProvider appearance={clerkAppearance}>{page}</ClerkProvider>
  ) : (
    page
  );
}
