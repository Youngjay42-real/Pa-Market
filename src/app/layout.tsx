import type { Metadata } from "next";
import { Inter, Fraunces } from "next/font/google";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { ChatWidget } from "@/components/chatbot/ChatWidget";
import "./globals.css";
import styles from "./layout.module.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
  display: "swap",
  axes: ["opsz"],
});

export const metadata: Metadata = {
  title: "Lusaka City Market Allocation System",
  description:
    "Transparent, automated market stand allocation for Lusaka City vendors.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} ${fraunces.variable}`}>
      <body>
        <a href="#main-content" className={styles.skipLink}>
          Skip to main content
        </a>
        <div className={styles.shell}>
          <Header />
          <main id="main-content" className={styles.main}>
            {children}
          </main>
          <Footer />
        </div>
        <ChatWidget />
      </body>
    </html>
  );
}
