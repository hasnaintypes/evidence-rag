import type React from "react"

interface NumbersThatSpeakProps {
  width?: number | string
  height?: number | string
  className?: string
  theme?: "light" | "dark"
}

/**
 * "Numbers that speak" - a floating card showing retrieval Precision@5,
 * pulled from the real eval numbers in docs/eval_report.md (advanced
 * pipeline vs. naive dense-retrieval baseline).
 */
const NumbersThatSpeak: React.FC<NumbersThatSpeakProps> = ({ width = 482, height = 300, className = "" }) => {
  const bars = [
    { label: "q1", height: "62px" },
    { label: "q2", height: "70px" },
    { label: "q3", height: "58px" },
    { label: "q4", height: "83px" },
    { label: "q5", height: "89px" },
    { label: "q6", height: "95px" },
    { label: "q7", height: "108px" },
    { label: "q8", height: "120px" },
    { label: "q9", height: "132px" },
  ]

  return (
    <div
      className={className}
      style={{
        width,
        height,
        position: "relative",
        background: "transparent",
      }}
      role="img"
      aria-label="Retrieval precision at 5 shown as a bar chart, 89.3 percent for the advanced pipeline"
      data-name="Numbers that speak"
    >
      <div
        style={{
          position: "absolute",
          left: "50%",
          transform: "translateX(-50%)",
          top: "calc(50% + 23.703px)",
        }}
      >
        <div
          style={{
            position: "absolute",
            left: "50%",
            transform: "translate(-50%, -50%)",
            top: "calc(50% - 19.427px)",
            width: "270px",
            height: "199.565px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            className="border border-[rgba(0,0,0,0.08)]"
            style={{
              width: "270px",
              height: "199.565px",
              background: "#ffffff",
              borderRadius: "4.696px",
              boxShadow:
                "0px 0px 0px 0.587px rgba(47,48,55,0.12), 0px 1.174px 2.348px -0.587px rgba(47,48,55,0.06), 0px 1.761px 3.522px -0.88px rgba(47,48,55,0.06)",
            }}
          />
        </div>

        <div
          style={{
            position: "absolute",
            left: "50%",
            transform: "translate(-50%, -50%)",
            top: "calc(50% + 12.573px)",
            width: "330px",
            height: "243.913px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            className="border border-[rgba(0,0,0,0.08)]"
            style={{
              width: "330px",
              height: "243.913px",
              background: "#ffffff",
              borderRadius: "5.739px",
              boxShadow:
                "0px 0px 0px 0.717px rgba(47,48,55,0.12), 0px 1.435px 2.87px -0.717px rgba(47,48,55,0.06), 0px 2.152px 4.304px -1.076px rgba(47,48,55,0.06)",
            }}
          />
        </div>

        <div
          style={{
            position: "absolute",
            left: "50%",
            transform: "translate(-50%, -50%)",
            top: "calc(50% + 33.573px)",
            width: "360px",
            height: "266.087px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            className="border border-[rgba(0,0,0,0.08)]"
            style={{
              width: "360px",
              height: "266.087px",
              background: "#ffffff",
              borderRadius: "6.261px",
              boxShadow:
                "0px 0px 0px 0.783px rgba(47,48,55,0.12), 0px 1.565px 3.13px -0.783px rgba(47,48,55,0.06), 0px 2.348px 4.696px -1.174px rgba(47,48,55,0.06)",
              overflow: "hidden",
              display: "flex",
              flexDirection: "column",
              padding: "18.783px",
              boxSizing: "border-box",
              gap: "18.783px",
            }}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: "6.261px" }}>
              <div
                style={{
                  fontFamily: "Inter, sans-serif",
                  fontWeight: 600,
                  fontSize: "10.174px",
                  lineHeight: "18.783px",
                  color: "rgba(47,48,55,0.8)",
                }}
              >
                Retrieval Precision@5
              </div>
              <div
                className="tracking-widest"
                style={{
                  fontFamily: "Inter, sans-serif",
                  fontWeight: 500,
                  fontSize: "18.783px",
                  lineHeight: "20.348px",
                  letterSpacing: "-0.587px",
                  color: "#2f3037",
                }}
              >
                89.3%
              </div>
            </div>

            <div style={{ height: "156.522px", position: "relative", width: "100%" }}>
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                }}
              >
                {[0, 1, 2, 3, 4, 5].map((i) => (
                  <div key={i} style={{ width: "100%", height: "1px", backgroundColor: "rgba(0,0,0,0.05)" }} />
                ))}
              </div>

              <div
                style={{
                  position: "absolute",
                  bottom: "23.48px",
                  right: 0,
                  top: "12.52px",
                  width: "100%",
                  display: "flex",
                  alignItems: "flex-end",
                  justifyContent: "space-between",
                  paddingLeft: "9.391px",
                  paddingRight: "9.391px",
                }}
              >
                {bars.map((bar) => (
                  <div
                    key={bar.label}
                    style={{
                      width: "12.522px",
                      height: bar.height,
                      backgroundColor: "#5D4E37",
                      borderRadius: "2px",
                    }}
                  />
                ))}
              </div>

              <div
                style={{
                  position: "absolute",
                  bottom: 0,
                  left: 0,
                  right: 0,
                  display: "flex",
                  justifyContent: "space-between",
                  fontFamily: "'Inter', sans-serif",
                  fontWeight: 500,
                  fontSize: "7.826px",
                  color: "rgba(55,50,47,0.7)",
                }}
              >
                <div>Naive</div>
                <div>Advanced</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default NumbersThatSpeak
