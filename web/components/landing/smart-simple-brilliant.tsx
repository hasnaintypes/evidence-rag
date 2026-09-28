import type React from "react"

interface SmartSimpleBrilliantProps {
  width?: number | string
  height?: number | string
  className?: string
  theme?: "light" | "dark"
}

/**
 * "Structure-aware, not chunk-first" - two tilted cards showing a document
 * broken into typed sections (heading / table / warning) instead of one
 * flat wall of text.
 */
const SmartSimpleBrilliant: React.FC<SmartSimpleBrilliantProps> = ({
  width = 482,
  height = 300,
  className = "",
  theme = "dark",
}) => {
  const themeVars =
    theme === "light"
      ? ({
          "--ssb-surface": "#ffffff",
          "--ssb-text": "#1b1919",
          "--ssb-border": "rgba(0,0,0,0.08)",
          "--ssb-inner-border": "rgba(0,0,0,0.12)",
          "--ssb-shadow": "rgba(0,0,0,0.12)",
          "--ssb-purple-text": "#581C87",
          "--ssb-emerald-text": "#064E3B",
        } as React.CSSProperties)
      : ({
          "--ssb-surface": "#333937",
          "--ssb-text": "#f8f8f8",
          "--ssb-border": "rgba(255,255,255,0.16)",
          "--ssb-inner-border": "rgba(255,255,255,0.12)",
          "--ssb-shadow": "rgba(0,0,0,0.28)",
          "--ssb-purple-text": "#E9D5FF",
          "--ssb-emerald-text": "#A7F3D0",
        } as React.CSSProperties)

  const rows = [
    { kind: "SECTION", label: "5.1 Emergency Stop", accent: "#0EA5E9", tint: "rgba(14,165,233,0.14)", height: "51px" },
    { kind: "TABLE", label: "Torque spec table", accent: "#F59E0B", tint: "rgba(245,158,11,0.14)", height: "79.5px" },
    { kind: "WARNING", label: "Allow 30min cooldown", accent: "#F43F5E", tint: "rgba(244,63,94,0.14)", height: "51px" },
  ]

  return (
    <div
      className={className}
      style={
        {
          width,
          height,
          position: "relative",
          background: "transparent",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "var(--font-sans)",
          ...themeVars,
        } as React.CSSProperties
      }
      role="img"
      aria-label="Two cards showing a document broken into typed sections: heading, table, and warning"
    >
      <div
        style={{
          position: "relative",
          width: "295.297px",
          height: "212.272px",
          transform: "scale(1.2)",
        }}
      >
        {/* Left tilted card - typed nodes */}
        <div style={{ position: "absolute", left: "123.248px", top: "0px", width: 0, height: 0 }}>
          <div style={{ transform: "rotate(5deg)", transformOrigin: "center" }}>
            <div
              style={{
                width: "155.25px",
                background: "var(--ssb-surface)",
                borderRadius: "9px",
                padding: "6px",
                boxShadow: "0px 0px 0px 1px var(--ssb-border), 0px 2px 4px var(--ssb-shadow)",
              }}
            >
              {rows.map((row, i) => (
                <div
                  key={row.kind}
                  style={{
                    width: "100%",
                    height: row.height,
                    borderRadius: "4px",
                    overflow: "hidden",
                    background: row.tint,
                    marginTop: i === 0 ? 0 : "3px",
                    display: "flex",
                  }}
                >
                  <div style={{ width: "2.25px", background: row.accent }} />
                  <div style={{ padding: "4.5px", width: "100%" }}>
                    <span
                      style={{
                        fontWeight: 600,
                        fontSize: "8px",
                        letterSpacing: "0.4px",
                        color: row.accent,
                      }}
                    >
                      {row.kind}
                    </span>
                    <div style={{ fontWeight: 600, fontSize: "9px", color: "var(--ssb-text)" }}>{row.label}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right card - retrieved chunk with citation */}
        <div style={{ position: "absolute", left: "0px", top: "6.075px", width: "155.25px" }}>
          <div style={{ transform: "rotate(-5deg)", transformOrigin: "center" }}>
            <div
              style={{
                width: "155.25px",
                background: "var(--ssb-surface)",
                borderRadius: "9px",
                padding: "6px",
                boxShadow:
                  "-8px 6px 11.3px var(--ssb-shadow), 0px 0px 0px 1px var(--ssb-border), 0px 2px 4px var(--ssb-shadow)",
              }}
            >
              <div
                style={{
                  width: "100%",
                  height: "51px",
                  borderRadius: "4px",
                  overflow: "hidden",
                  background: "rgba(139,92,246,0.14)",
                  display: "flex",
                }}
              >
                <div style={{ width: "2.25px", background: "#8B5CF6" }} />
                <div style={{ padding: "4.5px", width: "100%" }}>
                  <span style={{ fontWeight: 600, fontSize: "8px", letterSpacing: "0.4px", color: "#8B5CF6" }}>
                    PARAGRAPH
                  </span>
                  <div style={{ fontWeight: 600, fontSize: "9px", color: "var(--ssb-purple-text)" }}>
                    Grease spindle every 600h
                  </div>
                </div>
              </div>

              <div
                style={{
                  width: "100%",
                  height: "51px",
                  borderRadius: "4px",
                  overflow: "hidden",
                  background: "rgba(16,185,129,0.14)",
                  display: "flex",
                  marginTop: "3px",
                }}
              >
                <div style={{ width: "2.25px", background: "#10B981" }} />
                <div style={{ padding: "4.5px", width: "100%" }}>
                  <div style={{ display: "flex", gap: "3px", alignItems: "center" }}>
                    <span style={{ fontWeight: 500, fontSize: "9px", color: "var(--ssb-emerald-text)" }}>p.42</span>
                  </div>
                  <div style={{ fontWeight: 600, fontSize: "9px", color: "var(--ssb-emerald-text)" }}>
                    ASDAVS-SP002A.pdf
                  </div>
                </div>
              </div>

              <div
                style={{
                  width: "100%",
                  height: "79.5px",
                  borderRadius: "4px",
                  overflow: "hidden",
                  background: "rgba(139,92,246,0.14)",
                  display: "flex",
                  marginTop: "3px",
                }}
              >
                <div style={{ width: "2.25px", background: "#8B5CF6" }} />
                <div style={{ padding: "4.5px", width: "100%" }}>
                  <span style={{ fontWeight: 500, fontSize: "9px", color: "var(--ssb-purple-text)" }}>
                    rerank: 0.91
                  </span>
                  <div style={{ fontWeight: 600, fontSize: "9px", color: "var(--ssb-purple-text)" }}>
                    Parent section reconstructed
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default SmartSimpleBrilliant
