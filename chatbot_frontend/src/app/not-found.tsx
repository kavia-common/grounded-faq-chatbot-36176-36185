import React from "react";

export default function NotFound() {
  return (
    <main className="chat-wrap">
      <section className="chat-panel">
        <div className="messages" role="alert" aria-live="assertive">
          <div className="msg assistant">
            <div className="avatar avatar-assistant">A</div>
            <div>
              <div className="bubble">
                <h1 style={{ fontSize: "1.25rem", fontWeight: 600, marginBottom: ".25rem" }}>
                  404 – Page Not Found
                </h1>
                <p className="small-muted">The page you’re looking for doesn’t exist.</p>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
