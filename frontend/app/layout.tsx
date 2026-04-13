import type { Metadata, Viewport } from "next";
import { Cormorant_Garamond, Inter } from "next/font/google";
import "./globals.css";

const cormorant = Cormorant_Garamond({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "RAG Playas — Jurisprudencia Costera de Colombia",
    template: "%s | RAG Playas",
  },
  description:
    "Consulte jurisprudencia colombiana en materia de playas, bienes de uso público costero y derecho marítimo mediante inteligencia artificial fundamentada en fuentes verificadas.",
  openGraph: {
    type: "website",
    locale: "es_CO",
    siteName: "RAG Playas",
    title: "RAG Playas — Jurisprudencia Costera de Colombia",
    description:
      "Respuestas jurídicas fundamentadas en jurisprudencia colombiana verificada sobre playas y derecho marítimo.",
  },
  twitter: {
    card: "summary",
    title: "RAG Playas",
    description: "Jurisprudencia costera colombiana con IA.",
  },
};

export const viewport: Viewport = {
  themeColor: "#18182b",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="es"
      className={`${cormorant.variable} ${inter.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <a href="#main-content" className="skip-link">
          Saltar al contenido principal
        </a>
        {children}
      </body>
    </html>
  );
}
