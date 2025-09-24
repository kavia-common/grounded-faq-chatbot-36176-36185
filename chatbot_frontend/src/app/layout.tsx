import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ocean Chat – Grounded QA",
  description:
    "Modern, minimalist RAG chatbot UI with Ocean Professional theme. Centered chat panel, sidebar history, streaming answers.",
  applicationName: "Ocean Chat",
  icons: [{ rel: "icon", url: "/favicon.ico" }],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased">
        <div className="app-shell">
          <aside className="sidebar">
            <div className="brand">
              <div
                style={{
                  width: "32px",
                  height: "32px",
                  borderRadius: "8px",
                  background: "#2563EB",
                  display: "grid",
                  placeItems: "center",
                  color: "white",
                  fontWeight: 700,
                }}
              >
                OC
              </div>
              <div>
                <div style={{ fontWeight: 600 }}>Ocean Chat</div>
                <div className="small-muted" aria-label="theme">Ocean Professional</div>
              </div>
            </div>
            <div className="small-muted" style={{ margin: ".25rem 0 .75rem" }}>
              Recent chats
            </div>
            <div className="history-list" role="navigation" aria-label="Recent chats">
              {/* Placeholder items for now; page hydrates real history */}
              <button className="history-item" type="button">Welcome tour</button>
              <button className="history-item" type="button">Getting started</button>
              <button className="history-item" type="button">Pricing & limits</button>
            </div>
            <div style={{ marginTop: "1rem" }} className="small-muted">
              Tip: Press <span className="kbd">Shift</span> + <span className="kbd">Enter</span> for a new line
            </div>
          </aside>
          <main className="main">
            <header className="header">
              <div style={{ display: "flex", alignItems: "center", gap: ".75rem", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: ".5rem" }}>
                  <span className="badge" aria-label="status">
                    <span
                      style={{ display: "inline-block", width: "8px", height: "8px", borderRadius: "999px", background: "#10B981" }}
                    />
                    Ready
                  </span>
                  <span className="small-muted">Ask anything about your documents</span>
                </div>
              </div>
            </header>
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
