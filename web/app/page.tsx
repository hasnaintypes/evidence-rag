"use client"

import type React from "react"

import { useEffect, useState } from "react"
import Link from "next/link"
import SmartSimpleBrilliant from "@/components/landing/smart-simple-brilliant"
import YourWorkInSync from "@/components/landing/your-work-in-sync"
import EffortlessIntegration from "@/components/landing/effortless-integration"
import NumbersThatSpeak from "@/components/landing/numbers-that-speak"
import DocumentationSection from "@/components/landing/documentation-section"
// Testimonials and pricing aren't shown yet - re-enable once there are
// real customer quotes and a real paid tier. Components are kept in
// components/landing/, just not imported/rendered below.
// import TestimonialsSection from "@/components/landing/testimonials-section"
// import PricingSection from "@/components/landing/pricing-section"
import FAQSection from "@/components/landing/faq-section"
import CTASection from "@/components/landing/cta-section"
import FooterSection from "@/components/landing/footer-section"

function Badge({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="px-[14px] py-[6px] bg-card overflow-hidden rounded-[90px] flex justify-start items-center gap-[8px] border border-border">
      <div className="w-[14px] h-[14px] relative overflow-hidden flex items-center justify-center">{icon}</div>
      <div className="text-center flex justify-center flex-col text-foreground text-xs font-medium leading-3 font-sans">
        {text}
      </div>
    </div>
  )
}

function FeatureCard({
  title,
  description,
  isActive,
  progress,
  onClick,
}: {
  title: string
  description: string
  isActive: boolean
  progress: number
  onClick: () => void
}) {
  return (
    <div
      className={`w-full md:flex-1 self-stretch px-6 py-5 overflow-hidden flex flex-col justify-start items-start gap-2 cursor-pointer relative border-b md:border-b-0 last:border-b-0 ${
        isActive ? "bg-card shadow-[0px_0px_0px_0.75px_var(--border)_inset]" : "border-l-0 border-r-0 md:border border-border/60"
      }`}
      onClick={onClick}
    >
      {isActive && (
        <div className="absolute top-0 left-0 w-full h-0.5 bg-muted">
          <div className="h-full bg-foreground transition-all duration-100 ease-linear" style={{ width: `${progress}%` }} />
        </div>
      )}
      <div className="self-stretch flex justify-center flex-col text-foreground text-sm font-semibold leading-6 font-sans">
        {title}
      </div>
      <div className="self-stretch text-muted-foreground text-[13px] font-normal leading-[22px] font-sans">
        {description}
      </div>
    </div>
  )
}

export default function LandingPage() {
  const [activeCard, setActiveCard] = useState(0)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const progressInterval = setInterval(() => {
      setProgress((prev) => {
        if (prev >= 100) {
          setActiveCard((current) => (current + 1) % 3)
          return 0
        }
        return prev + 2
      })
    }, 100)

    return () => clearInterval(progressInterval)
  }, [])

  const handleCardClick = (index: number) => {
    setActiveCard(index)
    setProgress(0)
  }

  return (
    <div className="w-full min-h-screen relative bg-background overflow-x-hidden flex flex-col justify-start items-center">
      <div className="relative flex flex-col justify-start items-center w-full">
        <div className="w-full max-w-none px-4 sm:px-6 md:px-8 lg:px-0 lg:max-w-[1060px] lg:w-[1060px] relative flex flex-col justify-start items-start min-h-screen">
          {/* Left/right vertical lines */}
          <div className="w-[1px] h-full absolute left-4 sm:left-6 md:left-8 lg:left-0 top-0 bg-border z-0"></div>
          <div className="w-[1px] h-full absolute right-4 sm:right-6 md:right-8 lg:right-0 top-0 bg-border z-0"></div>

          <div className="self-stretch pt-[9px] overflow-hidden border-b border-border flex flex-col justify-center items-center gap-4 sm:gap-6 md:gap-8 lg:gap-[66px] relative z-10">
            {/* Navigation */}
            <div className="w-full h-12 sm:h-14 md:h-16 lg:h-[84px] absolute left-0 top-0 flex justify-center items-center z-20 px-6 sm:px-8 md:px-12 lg:px-0">
              <div className="w-full h-0 absolute left-0 top-6 sm:top-7 md:top-8 lg:top-[42px] border-t border-border"></div>

              <div className="w-full max-w-[calc(100%-32px)] sm:max-w-[calc(100%-48px)] md:max-w-[calc(100%-64px)] lg:max-w-[700px] lg:w-[700px] h-10 sm:h-11 md:h-12 py-1.5 sm:py-2 px-3 sm:px-4 md:px-4 pr-2 sm:pr-3 bg-background/90 backdrop-blur-sm overflow-hidden rounded-full flex justify-between items-center relative z-30 border border-border">
                <div className="flex justify-center items-center">
                  <Link href="/" className="flex justify-start items-center">
                    <div className="flex flex-col justify-center text-foreground text-sm sm:text-base md:text-lg lg:text-xl font-semibold leading-5 font-sans tracking-tight">
                      EvidenceRAG
                    </div>
                  </Link>
                  <div className="pl-3 sm:pl-4 md:pl-5 lg:pl-5 flex justify-start items-start hidden sm:flex flex-row gap-2 sm:gap-3 md:gap-4 lg:gap-4">
                    <a
                      href="https://github.com/hasnaintypes/evidence-rag#readme"
                      target="_blank"
                      rel="noreferrer"
                      className="flex justify-start items-center"
                    >
                      <div className="flex flex-col justify-center text-foreground/80 text-xs md:text-[13px] font-medium leading-[14px] font-sans hover:text-foreground transition-colors">
                        Docs
                      </div>
                    </a>
                  </div>
                </div>
                <div className="h-6 sm:h-7 md:h-8 flex justify-start items-center gap-3 sm:gap-4">
                  <Link
                    href="/sign-in"
                    className="text-foreground/80 text-xs md:text-[13px] font-medium leading-5 font-sans hover:text-foreground transition-colors"
                  >
                    Sign in
                  </Link>
                  <Link
                    href="/sign-up"
                    className="px-2 sm:px-3 md:px-[14px] py-1 sm:py-[6px] bg-card overflow-hidden rounded-full flex justify-center items-center border border-border"
                  >
                    <div className="flex flex-col justify-center text-foreground text-xs md:text-[13px] font-medium leading-5 font-sans">
                      Sign up
                    </div>
                  </Link>
                </div>
              </div>
            </div>

            {/* Hero Section */}
            <div className="pt-16 sm:pt-20 md:pt-24 lg:pt-[216px] pb-8 sm:pb-12 md:pb-16 flex flex-col justify-start items-center px-2 sm:px-4 md:px-8 lg:px-0 w-full">
              <div className="w-full max-w-[937px] lg:w-[937px] flex flex-col justify-center items-center gap-3 sm:gap-4 md:gap-5 lg:gap-6">
                <div className="self-stretch rounded-[3px] flex flex-col justify-center items-center gap-4 sm:gap-5 md:gap-6 lg:gap-8">
                  <div className="w-full max-w-[748.71px] lg:w-[748.71px] text-center flex justify-center flex-col text-foreground text-[24px] xs:text-[28px] sm:text-[36px] md:text-[52px] lg:text-[72px] font-medium leading-[1.1] sm:leading-[1.15] md:leading-[1.2] lg:leading-[1.05] font-display tracking-tight px-2 sm:px-4 md:px-0">
                    Ask your technical documents
                    <br />
                    a question. Get an honest answer.
                  </div>
                  <div className="w-full max-w-[560px] text-center flex justify-center flex-col text-muted-foreground sm:text-lg md:text-xl leading-[1.4] sm:leading-[1.45] md:leading-[1.5] lg:leading-7 font-sans px-2 sm:px-4 md:px-0 lg:text-lg font-medium text-sm">
                    Hybrid retrieval, cross-encoder reranking, and source citations
                    <br className="hidden sm:block" />
                    on every answer - refuses to answer rather than fabricate one.
                  </div>
                </div>
              </div>

              <div className="w-full max-w-[497px] flex flex-col justify-center items-center gap-6 sm:gap-8 md:gap-10 lg:gap-12 relative z-10 mt-6 sm:mt-8 md:mt-10 lg:mt-12">
                <div className="backdrop-blur-[8.25px] flex justify-start items-center gap-4">
                  <Link
                    href="/sign-in"
                    className="h-10 sm:h-11 md:h-12 px-6 sm:px-8 md:px-10 lg:px-12 py-2 sm:py-[6px] relative bg-primary shadow-[0px_0px_0px_2.5px_rgba(255,255,255,0.08)_inset] overflow-hidden rounded-full flex justify-center items-center"
                  >
                    <div className="w-20 sm:w-24 md:w-28 lg:w-44 h-[41px] absolute left-0 top-[-0.5px] bg-gradient-to-b from-[rgba(255,255,255,0)] to-[rgba(0,0,0,0.10)] mix-blend-multiply"></div>
                    <div className="flex flex-col justify-center text-primary-foreground text-sm sm:text-base md:text-[15px] font-medium leading-5 font-sans">
                      Ask a question
                    </div>
                  </Link>
                </div>
              </div>

              <div className="absolute top-[232px] sm:top-[248px] md:top-[264px] lg:top-[320px] left-1/2 transform -translate-x-1/2 z-0 pointer-events-none">
                <img
                  src="/mask-group-pattern.svg"
                  alt=""
                  className="w-[936px] sm:w-[1404px] md:w-[2106px] lg:w-[2808px] h-auto opacity-10 sm:opacity-15 md:opacity-20 mix-blend-screen invert"
                />
              </div>

              {/* Feature highlight row */}
              <div className="self-stretch border-t border-border border-b flex justify-center items-start mt-8 sm:mt-12 md:mt-16">
                <div className="w-4 sm:w-6 md:w-8 lg:w-12 self-stretch relative overflow-hidden">
                  <div className="w-[120px] sm:w-[140px] md:w-[162px] left-[-40px] sm:left-[-50px] md:left-[-58px] top-[-120px] absolute flex flex-col justify-start items-start">
                    {Array.from({ length: 50 }).map((_, i) => (
                      <div key={i} className="self-stretch h-3 sm:h-4 rotate-[-45deg] origin-top-left outline outline-[0.5px] outline-border outline-offset-[-0.25px]"></div>
                    ))}
                  </div>
                </div>

                <div className="flex-1 px-0 sm:px-2 md:px-0 flex flex-col md:flex-row justify-center items-stretch gap-0">
                  <FeatureCard
                    title="Explainable retrieval"
                    description="BM25, dense similarity, fusion rank, and rerank score for every candidate - not a black box."
                    isActive={activeCard === 0}
                    progress={activeCard === 0 ? progress : 0}
                    onClick={() => handleCardClick(0)}
                  />
                  <FeatureCard
                    title="Never fabricates"
                    description="Below-threshold confidence returns an explicit failure state, not a confident-sounding guess."
                    isActive={activeCard === 1}
                    progress={activeCard === 1 ? progress : 0}
                    onClick={() => handleCardClick(1)}
                  />
                  <FeatureCard
                    title="Entity graph"
                    description="Co-occurring technical terms extracted per section, browsable as an interactive graph."
                    isActive={activeCard === 2}
                    progress={activeCard === 2 ? progress : 0}
                    onClick={() => handleCardClick(2)}
                  />
                </div>

                <div className="w-4 sm:w-6 md:w-8 lg:w-12 self-stretch relative overflow-hidden">
                  <div className="w-[120px] sm:w-[140px] md:w-[162px] left-[-40px] sm:left-[-50px] md:left-[-58px] top-[-120px] absolute flex flex-col justify-start items-start">
                    {Array.from({ length: 50 }).map((_, i) => (
                      <div key={i} className="self-stretch h-3 sm:h-4 rotate-[-45deg] origin-top-left outline outline-[0.5px] outline-border outline-offset-[-0.25px]"></div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Bento Grid Section */}
              <div className="w-full border-b border-border flex flex-col justify-center items-center">
                <div className="self-stretch px-4 sm:px-6 md:px-8 lg:px-0 lg:max-w-[1060px] lg:w-[1060px] py-8 sm:py-12 md:py-16 border-b border-border flex justify-center items-center gap-6">
                  <div className="w-full max-w-[616px] lg:w-[616px] px-4 sm:px-6 py-4 sm:py-5 overflow-hidden rounded-lg flex flex-col justify-start items-center gap-3 sm:gap-4">
                    <Badge
                      icon={
                        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                          <rect x="1" y="1" width="4" height="4" stroke="currentColor" strokeWidth="1" fill="none" className="text-foreground" />
                          <rect x="7" y="1" width="4" height="4" stroke="currentColor" strokeWidth="1" fill="none" className="text-foreground" />
                          <rect x="1" y="7" width="4" height="4" stroke="currentColor" strokeWidth="1" fill="none" className="text-foreground" />
                          <rect x="7" y="7" width="4" height="4" stroke="currentColor" strokeWidth="1" fill="none" className="text-foreground" />
                        </svg>
                      }
                      text="Under the hood"
                    />
                    <div className="w-full max-w-[598.06px] lg:w-[598.06px] text-center flex justify-center flex-col text-foreground text-xl sm:text-2xl md:text-3xl lg:text-5xl font-semibold leading-tight md:leading-[60px] font-sans tracking-tight">
                      Built for evidence, not vibes
                    </div>
                    <div className="self-stretch text-center text-muted-foreground text-sm sm:text-base font-normal leading-6 sm:leading-7 font-sans">
                      A node tree, a hybrid retrieval pipeline, and a judge model
                      <br />
                      that checks the answer against what it was actually given.
                    </div>
                  </div>
                </div>

                <div className="self-stretch flex justify-center items-start">
                  <div className="w-4 sm:w-6 md:w-8 lg:w-12 self-stretch relative overflow-hidden">
                    <div className="w-[120px] sm:w-[140px] md:w-[162px] left-[-40px] sm:left-[-50px] md:left-[-58px] top-[-120px] absolute flex flex-col justify-start items-start">
                      {Array.from({ length: 200 }).map((_, i) => (
                        <div key={i} className="self-stretch h-3 sm:h-4 rotate-[-45deg] origin-top-left outline outline-[0.5px] outline-border outline-offset-[-0.25px]" />
                      ))}
                    </div>
                  </div>

                  <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-0 border-l border-r border-border">
                    <div className="border-b border-r-0 md:border-r border-border p-4 sm:p-6 md:p-8 lg:p-12 flex flex-col justify-start items-start gap-4 sm:gap-6">
                      <div className="flex flex-col gap-2">
                        <h3 className="text-foreground text-lg sm:text-xl font-semibold leading-tight font-sans">
                          Structure-aware, not chunk-first
                        </h3>
                        <p className="text-muted-foreground text-sm md:text-base font-normal leading-relaxed font-sans">
                          Every document becomes a KnowledgeNode tree - headings, tables, warnings kept intact, not flattened.
                        </p>
                      </div>
                      <div className="w-full h-[200px] sm:h-[250px] md:h-[300px] rounded-lg flex items-center justify-center overflow-hidden">
                        <SmartSimpleBrilliant width="100%" height="100%" theme="dark" className="scale-50 sm:scale-65 md:scale-75 lg:scale-90" />
                      </div>
                    </div>

                    <div className="border-b border-border p-4 sm:p-6 md:p-8 lg:p-12 flex flex-col justify-start items-start gap-4 sm:gap-6">
                      <div className="flex flex-col gap-2">
                        <h3 className="text-foreground font-semibold leading-tight font-sans text-lg sm:text-xl">
                          Grounded Q&amp;A
                        </h3>
                        <p className="text-muted-foreground text-sm md:text-base font-normal leading-relaxed font-sans">
                          Every reply is traceable to a source file and page - ask a follow-up, get the same rigor.
                        </p>
                      </div>
                      <div className="w-full h-[200px] sm:h-[250px] md:h-[300px] rounded-lg flex overflow-hidden text-right items-center justify-center">
                        <YourWorkInSync width="400" height="250" theme="dark" className="scale-60 sm:scale-75 md:scale-90" />
                      </div>
                    </div>

                    <div className="border-r-0 md:border-r border-border p-4 sm:p-6 md:p-8 lg:p-12 flex flex-col justify-start items-start gap-4 sm:gap-6">
                      <div className="flex flex-col gap-2">
                        <h3 className="text-foreground text-lg sm:text-xl font-semibold leading-tight font-sans">
                          Every format, one pipeline
                        </h3>
                        <p className="text-muted-foreground text-sm md:text-base font-normal leading-relaxed font-sans">
                          Markdown, PDF, DOCX, XLSX, and CSV all normalize into the same tree - no format-specific retrieval logic.
                        </p>
                      </div>
                      <div className="w-full h-[200px] sm:h-[250px] md:h-[300px] rounded-lg flex overflow-hidden justify-center items-center relative">
                        <div className="w-full h-full flex items-center justify-center">
                          <EffortlessIntegration width={400} height={250} theme="dark" className="max-w-full max-h-full" />
                        </div>
                        <div className="absolute bottom-0 left-0 right-0 h-8 bg-gradient-to-t from-background to-transparent pointer-events-none"></div>
                      </div>
                    </div>

                    <div className="p-4 sm:p-6 md:p-8 lg:p-12 flex flex-col justify-start items-start gap-4 sm:gap-6">
                      <div className="flex flex-col gap-2">
                        <h3 className="text-foreground text-lg sm:text-xl font-semibold leading-tight font-sans">
                          Retrieval quality, measured
                        </h3>
                        <p className="text-muted-foreground text-sm md:text-base font-normal leading-relaxed font-sans">
                          Evaluated against a naive baseline on a labeled set - Precision@5, Recall@5, and MRR, not vibes.
                        </p>
                      </div>
                      <div className="w-full h-[200px] sm:h-[250px] md:h-[300px] rounded-lg flex overflow-hidden items-center justify-center relative">
                        <div className="absolute inset-0 flex items-center justify-center">
                          <NumbersThatSpeak width="100%" height="100%" className="w-full h-full object-contain" />
                        </div>
                        <div className="absolute bottom-0 left-0 right-0 h-8 bg-gradient-to-t from-background to-transparent pointer-events-none"></div>
                      </div>
                    </div>
                  </div>

                  <div className="w-4 sm:w-6 md:w-8 lg:w-12 self-stretch relative overflow-hidden">
                    <div className="w-[120px] sm:w-[140px] md:w-[162px] left-[-40px] sm:left-[-50px] md:left-[-58px] top-[-120px] absolute flex flex-col justify-start items-start">
                      {Array.from({ length: 200 }).map((_, i) => (
                        <div key={i} className="self-stretch h-3 sm:h-4 rotate-[-45deg] origin-top-left outline outline-[0.5px] outline-border outline-offset-[-0.25px]" />
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <DocumentationSection />
              {/* <TestimonialsSection /> */}
              {/* <PricingSection /> */}
              <FAQSection />
              <CTASection />
              <FooterSection />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
