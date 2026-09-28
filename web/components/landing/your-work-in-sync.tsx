import type React from "react"

interface YourWorkInSyncProps {
  width?: number | string
  height?: number | string
  className?: string
  theme?: "light" | "dark"
}

/**
 * "Ask, get grounded answers" - a chat mockup showing a question, a cited
 * answer, a follow-up, and a source reference.
 */
const YourWorkInSync: React.FC<YourWorkInSyncProps> = ({
  width = 482,
  height = 300,
  className = "",
  theme = "dark",
}) => {
  const themeVars =
    theme === "light"
      ? {
          "--yws-surface": "#ffffff",
          "--yws-text-primary": "#37322f",
          "--yws-text-secondary": "#6b7280",
          "--yws-bubble-light": "#e8e5e3",
          "--yws-bubble-dark": "#37322f",
          "--yws-bubble-white": "#ffffff",
          "--yws-border": "rgba(0,0,0,0.08)",
          "--yws-shadow": "rgba(0,0,0,0.08)",
        }
      : ({
          "--yws-surface": "#1f2937",
          "--yws-text-primary": "#f9fafb",
          "--yws-text-secondary": "#d1d5db",
          "--yws-bubble-light": "#374151",
          "--yws-bubble-dark": "#111827",
          "--yws-bubble-white": "#ffffff",
          "--yws-border": "rgba(255,255,255,0.12)",
          "--yws-shadow": "rgba(0,0,0,0.24)",
        } as React.CSSProperties)

  const imgArrowUp =
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='20' height='20' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='3' strokeLinecap='round' strokeLinejoin='round'%3E%3Cpath d='m5 12 7-7 7 7'/%3E%3Cpath d='M12 19V5'/%3E%3C/svg%3E"

  const avatar = (bg: string, initial: string) => (
    <div
      style={{
        width: "36px",
        height: "36px",
        borderRadius: "44px",
        background: bg,
        border: "1px solid var(--yws-border)",
        flexShrink: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "Inter, sans-serif",
        fontWeight: 600,
        fontSize: "13px",
        color: "#ffffff",
      }}
    >
      {initial}
    </div>
  )

  return (
    <div
      className={className}
      style={
        {
          width,
          height,
          position: "relative",
          background: "transparent",
          ...themeVars,
        } as React.CSSProperties
      }
      role="img"
      aria-label="Chat conversation showing a question answered with a cited source"
    >
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: "50%",
          transform: "translate(-50%, -50%)",
          width: "356px",
          height: "216px",
        }}
      >
        <div style={{ width: "356px", height: "216px", position: "relative", transform: "scale(1.1)" }}>
          {/* Message 1: question */}
          <div
            style={{
              position: "absolute",
              left: "0px",
              top: "0px",
              display: "flex",
              gap: "10px",
              alignItems: "flex-start",
              width: "356px",
              height: "36px",
            }}
          >
            {avatar("#8B5CF6", "U")}
            <div
              style={{
                background: "var(--yws-bubble-light)",
                borderRadius: "999px",
                padding: "0px 12px",
                height: "36px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <span
                style={{
                  fontFamily: "Inter, sans-serif",
                  fontWeight: 500,
                  fontSize: "13px",
                  lineHeight: "16px",
                  letterSpacing: "-0.4px",
                  color: "var(--yws-text-primary)",
                  whiteSpace: "nowrap",
                }}
              >
                When should the spindle be regreased?
              </span>
            </div>
          </div>

          {/* Message 2: grounded answer */}
          <div
            style={{
              position: "absolute",
              right: "0px",
              top: "60px",
              display: "flex",
              gap: "10px",
              alignItems: "flex-start",
              justifyContent: "flex-end",
            }}
          >
            <div
              style={{
                background: "var(--yws-bubble-dark)",
                borderRadius: "999px",
                padding: "0px 12px",
                height: "36px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <span
                style={{
                  fontFamily: "Inter, sans-serif",
                  fontWeight: 500,
                  fontSize: "13px",
                  lineHeight: "16px",
                  letterSpacing: "-0.4px",
                  color: "#ffffff",
                  whiteSpace: "nowrap",
                }}
              >
                Every 600 operating hours
              </span>
            </div>
            {avatar("#111827", "E")}
          </div>

          {/* Message 3: source reference */}
          <div
            style={{
              position: "absolute",
              left: "0px",
              top: "120px",
              display: "flex",
              gap: "10px",
              alignItems: "flex-start",
              width: "260px",
              height: "36px",
            }}
          >
            {avatar("#0EA5E9", "¶")}
            <div
              style={{
                background: "var(--yws-bubble-light)",
                borderRadius: "999px",
                padding: "0px 12px",
                height: "36px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <span
                style={{
                  fontFamily: "Inter, sans-serif",
                  fontWeight: 500,
                  fontSize: "13px",
                  lineHeight: "16px",
                  letterSpacing: "-0.4px",
                  color: "var(--yws-text-primary)",
                  whiteSpace: "nowrap",
                }}
              >
                Source: ASDAVS-SP002A.pdf, p.42
              </span>
            </div>
          </div>

          {/* Message 4: follow-up input */}
          <div
            style={{
              position: "absolute",
              left: "146px",
              top: "180px",
              display: "flex",
              gap: "10px",
              alignItems: "center",
              height: "36px",
            }}
          >
            <div
              style={{
                background: "#ffffff",
                borderRadius: "16px",
                padding: "0px 12px",
                height: "36px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                boxShadow: "0px 0px 0px 1px rgba(0,0,0,0.08), 0px 1px 2px -0.4px rgba(0,0,0,0.08)",
                overflow: "hidden",
              }}
            >
              <span
                style={{
                  fontFamily: "Inter, sans-serif",
                  fontWeight: 400,
                  fontSize: "14px",
                  lineHeight: "20px",
                  color: "#030712",
                  whiteSpace: "nowrap",
                }}
              >
                What grease type?
              </span>
            </div>
            <div
              style={{
                width: "36px",
                height: "36px",
                borderRadius: "44px",
                background: "var(--yws-bubble-dark)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                boxShadow: "0px 1px 2px 0px rgba(0,0,0,0.08)",
                cursor: "pointer",
                flexShrink: 0,
              }}
            >
              <img
                src={imgArrowUp || "/placeholder.svg"}
                alt="Send"
                style={{
                  width: "20px",
                  height: "20px",
                  filter: "brightness(0) invert(1)",
                }}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default YourWorkInSync
