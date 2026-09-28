"use client"

import { useState, useEffect } from "react"

// Not currently rendered on the landing page (see app/page.tsx) - kept
// here, ready to re-enable once there are real customer quotes to show.
export default function TestimonialsSection() {
  const [activeTestimonial, setActiveTestimonial] = useState(0)
  const [isTransitioning, setIsTransitioning] = useState(false)

  const testimonials = [
    {
      quote:
        "We stopped trusting our old chatbot's answers on torque specs after one near-miss. EvidenceRAG shows the page number - now we actually check it, and it's always right.",
      name: "Priya Nair",
      company: "Maintenance Lead, Orbital Robotics",
    },
    {
      quote:
        "The bounded follow-up hop is the detail that sold me. It's adaptive without turning into an unpredictable agent loop that takes 30 seconds to answer a simple question.",
      name: "Dan Whitfield",
      company: "ML Platform Engineer",
    },
    {
      quote:
        "Every other RAG demo I've seen fabricates an answer when it can't find one. This is the first one that just says 'insufficient evidence' - and means it.",
      name: "Ines Okafor",
      company: "Reliability Engineer, Heavy Industrial",
    },
  ]

  useEffect(() => {
    const interval = setInterval(() => {
      setIsTransitioning(true)
      setTimeout(() => {
        setActiveTestimonial((prev) => (prev + 1) % testimonials.length)
        setTimeout(() => setIsTransitioning(false), 100)
      }, 300)
    }, 12000)

    return () => clearInterval(interval)
  }, [testimonials.length])

  const handleNavigationClick = (index: number) => {
    setIsTransitioning(true)
    setTimeout(() => {
      setActiveTestimonial(index)
      setTimeout(() => setIsTransitioning(false), 100)
    }, 300)
  }

  const current = testimonials[activeTestimonial]

  return (
    <div className="w-full border-b border-border flex flex-col justify-center items-center">
      <div className="self-stretch px-2 overflow-hidden flex justify-start items-center bg-background">
        <div className="flex-1 py-16 md:py-17 flex flex-col md:flex-row justify-center items-end gap-6">
          <div className="self-stretch px-3 md:px-12 justify-center items-start gap-4 flex flex-col md:flex-row">
            <div
              className="w-48 h-48 md:w-48 md:h-48 rounded-lg bg-muted flex items-center justify-center text-4xl font-semibold text-muted-foreground transition-all duration-700 ease-in-out"
              style={{
                opacity: isTransitioning ? 0.6 : 1,
                transform: isTransitioning ? "scale(0.95)" : "scale(1)",
              }}
            >
              {current.name.charAt(0)}
            </div>
            <div className="flex-1 px-6 py-6 overflow-hidden flex flex-col justify-start items-start gap-6 pb-0 pt-0">
              <div
                className="self-stretch justify-start flex flex-col text-foreground text-2xl md:text-[32px] font-medium leading-10 md:leading-[42px] font-sans h-[200px] md:h-[210px] overflow-hidden line-clamp-5 transition-all duration-700 ease-in-out tracking-tight"
                style={{ filter: isTransitioning ? "blur(4px)" : "blur(0px)" }}
              >
                &ldquo;{current.quote}&rdquo;
              </div>
              <div
                className="self-stretch flex flex-col justify-start items-start gap-1 transition-all duration-700 ease-in-out"
                style={{ filter: isTransitioning ? "blur(4px)" : "blur(0px)" }}
              >
                <div className="self-stretch justify-center flex flex-col text-foreground/90 text-lg font-medium leading-[26px] font-sans">
                  {current.name}
                </div>
                <div className="self-stretch justify-center flex flex-col text-muted-foreground text-lg font-medium leading-[26px] font-sans">
                  {current.company}
                </div>
              </div>
            </div>
          </div>

          {/* Navigation Arrows */}
          <div className="pr-6 justify-start items-start gap-[14px] flex">
            <button
              onClick={() => handleNavigationClick((activeTestimonial - 1 + testimonials.length) % testimonials.length)}
              className="w-9 h-9 overflow-hidden rounded-full border border-border justify-center items-center gap-2 flex hover:bg-muted transition-colors"
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M15 18L9 12L15 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-foreground" />
              </svg>
            </button>
            <button
              onClick={() => handleNavigationClick((activeTestimonial + 1) % testimonials.length)}
              className="w-9 h-9 overflow-hidden rounded-full border border-border justify-center items-center gap-2 flex hover:bg-muted transition-colors"
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M9 18L15 12L9 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-foreground" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
