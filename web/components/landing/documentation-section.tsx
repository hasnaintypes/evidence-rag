"use client"

import { useState, useEffect } from "react"
import type React from "react"

function Badge({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="px-[14px] py-[6px] bg-card shadow-[0px_0px_0px_4px_rgba(255,255,255,0.04)] overflow-hidden rounded-[90px] flex justify-start items-center gap-[8px] border border-border">
      <div className="w-[14px] h-[14px] relative overflow-hidden flex items-center justify-center">{icon}</div>
      <div className="text-center flex justify-center flex-col text-foreground text-xs font-medium leading-3 font-sans">
        {text}
      </div>
    </div>
  )
}

export default function DocumentationSection() {
  const [activeCard, setActiveCard] = useState(0)
  const [animationKey, setAnimationKey] = useState(0)

  const cards = [
    {
      title: "Structure-aware parsing",
      description: "Every document becomes a hierarchical KnowledgeNode tree -\nheadings, tables, warnings, figures - not a flat wall of text.",
    },
    {
      title: "Hybrid retrieval, explained",
      description: "BM25 and dense retrieval fused, reranked, and graded,\nwith every score visible in the explainability matrix.",
    },
    {
      title: "Grounded generation, or nothing",
      description: "Answers are traced to source file and page. No answer\nbeats a fabricated one - the pipeline says so honestly.",
    },
  ]

  useEffect(() => {
    const interval = setInterval(() => {
      setActiveCard((prev) => (prev + 1) % cards.length)
      setAnimationKey((prev) => prev + 1)
    }, 5000)

    return () => clearInterval(interval)
  }, [cards.length])

  const handleCardClick = (index: number) => {
    setActiveCard(index)
    setAnimationKey((prev) => prev + 1)
  }

  return (
    <div className="w-full border-b border-border flex flex-col justify-center items-center">
      {/* Header Section */}
      <div className="self-stretch px-6 md:px-24 py-12 md:py-16 border-b border-border flex justify-center items-center gap-6">
        <div className="w-full max-w-[586px] px-6 py-5 overflow-hidden rounded-lg flex flex-col justify-start items-center gap-4">
          <Badge
            icon={<div className="w-[10.50px] h-[10.50px] outline outline-[1.17px] outline-foreground outline-offset-[-0.58px] rounded-full"></div>}
            text="How it works"
          />
          <div className="self-stretch text-center flex justify-center flex-col text-foreground text-3xl md:text-5xl font-semibold leading-tight md:leading-[60px] font-sans tracking-tight">
            From raw documents to grounded answers
          </div>
          <div className="self-stretch text-center text-muted-foreground text-base font-normal leading-7 font-sans">
            Parsing, retrieval, and generation are each explainable -
            <br />
            no black box between your documents and the answer.
          </div>
        </div>
      </div>

      {/* Content Section */}
      <div className="self-stretch px-4 md:px-9 overflow-hidden flex justify-start items-center">
        <div className="flex-1 py-8 md:py-11 flex flex-col md:flex-row justify-start items-center gap-6 md:gap-12">
          {/* Left Column - Feature Cards */}
          <div className="w-full md:w-auto md:max-w-[400px] flex flex-col justify-center items-center gap-4 order-2 md:order-1">
            {cards.map((card, index) => {
              const isActive = index === activeCard

              return (
                <div
                  key={index}
                  onClick={() => handleCardClick(index)}
                  className={`w-full overflow-hidden flex flex-col justify-start items-start transition-all duration-300 cursor-pointer ${
                    isActive ? "bg-card shadow-[0px_0px_0px_0.75px_var(--border)_inset]" : "border border-border/60"
                  }`}
                >
                  <div className={`w-full h-0.5 bg-muted overflow-hidden ${isActive ? "opacity-100" : "opacity-0"}`}>
                    <div
                      key={animationKey}
                      className="h-0.5 bg-foreground animate-[progressBar_5s_linear_forwards] will-change-transform"
                    />
                  </div>
                  <div className="px-6 py-5 w-full flex flex-col gap-2">
                    <div className="self-stretch flex justify-center flex-col text-foreground text-sm font-semibold leading-6 font-sans">
                      {card.title}
                    </div>
                    <div className="self-stretch text-muted-foreground text-[13px] font-normal leading-[22px] font-sans whitespace-pre-line">
                      {card.description}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Right Column - Visual */}
          <div className="w-full md:w-auto rounded-lg flex flex-col justify-center items-center gap-2 order-1 md:order-2">
            <div className="w-full md:w-[580px] h-[250px] md:h-[420px] bg-card border border-border overflow-hidden rounded-lg flex flex-col justify-start items-start">
              <div
                className={`w-full h-full transition-all duration-300 ${
                  activeCard === 0
                    ? "bg-gradient-to-br from-blue-950/40 to-blue-900/10"
                    : activeCard === 1
                      ? "bg-gradient-to-br from-purple-950/40 to-purple-900/10"
                      : "bg-gradient-to-br from-emerald-950/40 to-emerald-900/10"
                }`}
              />
            </div>
          </div>
        </div>
      </div>

      <style jsx>{`
        @keyframes progressBar {
          0% {
            transform: translateX(-100%);
          }
          100% {
            transform: translateX(0%);
          }
        }
      `}</style>
    </div>
  )
}
