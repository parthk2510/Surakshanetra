import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ChainBreak — Blockchain Forensic Intelligence",
  description: "AI-powered blockchain fraud detection and graph analysis platform",
};

/* Inline script runs before React hydrates — prevents theme flash */
const themeInitScript = `
(function(){
  try {
    var t = localStorage.getItem('chainbreak_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', t);
    document.documentElement.classList.add(t === 'dark' ? 'dark' : 'light');
  } catch(e) {
    document.documentElement.setAttribute('data-theme', 'dark');
    document.documentElement.classList.add('dark');
  }
})();
`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full" suppressHydrationWarning>
      <head>
        {/* Inline theme init — must run before paint */}
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="h-full" suppressHydrationWarning>{children}</body>
    </html>
  );
}
