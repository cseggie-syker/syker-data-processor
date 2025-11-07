import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Syker Data Processor",
  description: "Convert Syker DTL files into Excel workbooks in your browser.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased bg-slate-50">{children}</body>
    </html>
  );
}


