import type React from "react"

interface EffortlessIntegrationProps {
  width?: number | string
  height?: number | string
  className?: string
  theme?: "light" | "dark"
}

/**
 * "Every format, one tree" - source file formats orbiting a central hub,
 * all normalized into the same KnowledgeNode structure.
 */
const EffortlessIntegration: React.FC<EffortlessIntegrationProps> = ({
  width = 482,
  height = 300,
  className = "",
  theme = "dark",
}) => {
  const ringColor = theme === "light" ? "rgba(55, 50, 47, 0.2)" : "rgba(255, 255, 255, 0.18)"
  const ringColorMid = theme === "light" ? "rgba(55, 50, 47, 0.25)" : "rgba(255, 255, 255, 0.22)"
  const ringColorInner = theme === "light" ? "rgba(55, 50, 47, 0.3)" : "rgba(255, 255, 255, 0.26)"
  const lineColor = theme === "light" ? "rgba(55, 50, 47, 0.1)" : "rgba(255, 255, 255, 0.16)"
  const hubBg = theme === "light" ? "#37322f" : "#f7f5f3"
  const hubText = theme === "light" ? "#ffffff" : "#111827"

  const centerX = 250
  const centerY = 179

  const getPositionOnRing = (ringRadius: number, angle: number) => ({
    x: centerX + ringRadius * Math.cos(angle),
    y: centerY + ringRadius * Math.sin(angle),
  })

  // Document formats EvidenceRAG ingests + the stack pieces they flow through.
  const nodes = [
    { name: "PDF", icon: "adobeacrobatreader", bg: "#EE3F24", invert: true, radius: 80, angle: Math.PI },
    { name: "Markdown", icon: "markdown", bg: "#ffffff", invert: false, radius: 80, angle: 0 },
    { name: "Word", icon: "microsoftword", bg: "#2B579A", invert: true, radius: 120, angle: -Math.PI / 4 },
    { name: "Gemini", icon: "googlegemini", bg: "#ffffff", invert: false, radius: 120, angle: (3 * Math.PI) / 4 },
    { name: "Excel/CSV", icon: "microsoftexcel", bg: "#217346", invert: true, radius: 120, angle: (5 * Math.PI) / 4 },
    { name: "SQLite", icon: "sqlite", bg: "#003B57", invert: true, radius: 160, angle: Math.PI },
    { name: "FastAPI", icon: "fastapi", bg: "#009688", invert: true, radius: 160, angle: 0 },
  ]

  return (
    <div
      className={className}
      style={{
        width,
        height,
        position: "relative",
        overflow: "hidden",
        maskImage: "linear-gradient(to bottom, transparent 0%, black 15%, black 85%, transparent 100%)",
        WebkitMaskImage: "linear-gradient(to bottom, transparent 0%, black 15%, black 85%, transparent 100%)",
      }}
      role="img"
      aria-label="Document formats and stack pieces orbiting a central hub"
    >
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background:
            "linear-gradient(to bottom, rgba(255,255,255,0.1) 0%, transparent 20%, transparent 80%, rgba(255,255,255,0.1) 100%)",
          pointerEvents: "none",
          zIndex: 10,
        }}
      />

      <div
        style={{
          position: "absolute",
          left: "50%",
          top: "50%",
          transform: "translate(-50%, -50%)",
          width: "320px",
          height: "320px",
          borderRadius: "50%",
          border: `1px solid ${ringColor}`,
          opacity: 0.8,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: "50%",
          transform: "translate(-50%, -50%)",
          width: "240px",
          height: "240px",
          borderRadius: "50%",
          border: `1px solid ${ringColorMid}`,
          opacity: 0.7,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: "50%",
          transform: "translate(-50%, -50%)",
          width: "160px",
          height: "160px",
          borderRadius: "50%",
          border: `1px solid ${ringColorInner}`,
          opacity: 0.6,
        }}
      />

      <div
        style={{
          width: "500px",
          height: "358px",
          left: "50%",
          top: "50%",
          transform: "translate(-50%, -50%)",
          position: "absolute",
        }}
      >
        <div
          style={{
            width: "72px",
            height: "72px",
            left: `${centerX - 36}px`,
            top: `${centerY - 36}px`,
            position: "absolute",
            background: hubBg,
            boxShadow: "0px 4px 12px rgba(0, 0, 0, 0.15)",
            borderRadius: "99px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: "'Inter', sans-serif",
            fontWeight: 700,
            fontSize: "32px",
            color: hubText,
          }}
        >
          E
        </div>

        {nodes.map((node) => {
          const pos = getPositionOnRing(node.radius, node.angle)
          return (
            <div
              key={node.name}
              style={{
                width: "32px",
                height: "32px",
                left: `${pos.x - 16}px`,
                top: `${pos.y - 16}px`,
                position: "absolute",
                background: node.bg,
                boxShadow: "0px 4px 12px rgba(0, 0, 0, 0.15)",
                borderRadius: "50%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <img
                src={`https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/${node.icon}.svg`}
                alt={node.name}
                style={{
                  width: "18px",
                  height: "18px",
                  filter: node.invert ? "brightness(0) invert(1)" : undefined,
                }}
              />
            </div>
          )
        })}

        <svg
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            pointerEvents: "none",
          }}
        >
          <defs>
            <linearGradient id="connectionGradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor={lineColor} />
              <stop offset="50%" stopColor={lineColor} stopOpacity={0.5} />
              <stop offset="100%" stopColor={lineColor} />
            </linearGradient>
          </defs>
          {nodes.map((node) => {
            const pos = getPositionOnRing(node.radius, node.angle)
            return (
              <line
                key={node.name}
                x1={centerX}
                y1={centerY}
                x2={pos.x}
                y2={pos.y}
                stroke="url(#connectionGradient)"
                strokeWidth="1"
                opacity="0.3"
              />
            )
          })}
        </svg>
      </div>
    </div>
  )
}

export default EffortlessIntegration
