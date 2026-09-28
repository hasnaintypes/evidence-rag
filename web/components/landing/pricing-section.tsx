"use client"

import { useState } from "react"

// Not currently rendered on the landing page (see app/page.tsx) - kept
// here, ready to re-enable once there's a real paid tier to sell.
export default function PricingSection() {
  const [billingPeriod, setBillingPeriod] = useState<"monthly" | "annually">("annually")

  const pricing = {
    starter: { monthly: 0, annually: 0 },
    team: { monthly: 49, annually: 39 },
    enterprise: { monthly: 499, annually: 399 },
  }

  return (
    <div className="w-full flex flex-col justify-center items-center gap-2">
      {/* Header Section */}
      <div className="self-stretch px-6 md:px-24 py-12 md:py-16 border-b border-border flex justify-center items-center gap-6">
        <div className="w-full max-w-[586px] px-6 py-5 overflow-hidden rounded-lg flex flex-col justify-start items-center gap-4">
          <div className="px-[14px] py-[6px] bg-card overflow-hidden rounded-[90px] flex justify-start items-center gap-[8px] border border-border">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path
                d="M6 1V11M8.5 3H4.75C4.28587 3 3.84075 3.18437 3.51256 3.51256C3.18437 3.84075 3 4.28587 3 4.75C3 5.21413 3.18437 5.65925 3.51256 5.98744C3.84075 6.31563 4.28587 6.5 4.75 6.5H7.25C7.71413 6.5 8.15925 6.68437 8.48744 7.01256C8.81563 7.34075 9 7.78587 9 8.25C9 8.71413 8.81563 9.15925 8.48744 9.48744C8.15925 9.81563 7.71413 10 7.25 10H3.5"
                stroke="currentColor"
                strokeWidth="1"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="text-foreground"
              />
            </svg>
            <div className="text-center flex justify-center flex-col text-foreground text-xs font-medium leading-3 font-sans">
              Plans & Pricing
            </div>
          </div>

          <div className="self-stretch text-center flex justify-center flex-col text-foreground text-3xl md:text-5xl font-semibold leading-tight md:leading-[60px] font-sans tracking-tight">
            Choose the plan for your document volume
          </div>
          <div className="self-stretch text-center text-muted-foreground text-base font-normal leading-7 font-sans">
            Self-host the free tier on your own hardware, or let us run
            <br />
            ingestion and generation for your team.
          </div>
        </div>
      </div>

      {/* Billing Toggle */}
      <div className="self-stretch px-6 md:px-16 py-9 relative flex justify-center items-center gap-4">
        <div className="w-full max-w-[1060px] h-0 absolute left-1/2 transform -translate-x-1/2 top-[63px] border-t border-border z-0"></div>

        <div className="p-3 relative bg-muted/40 border border-border flex justify-center items-center rounded-lg z-20">
          <div className="p-[2px] bg-muted rounded-[99px] border border-border flex justify-center items-center gap-[2px] relative">
            <div
              className={`absolute top-[2px] w-[calc(50%-1px)] h-[calc(100%-4px)] bg-background shadow-[0px_2px_4px_rgba(0,0,0,0.24)] rounded-[99px] transition-all duration-300 ease-in-out ${
                billingPeriod === "annually" ? "left-[2px]" : "right-[2px]"
              }`}
            />
            <button
              onClick={() => setBillingPeriod("annually")}
              className="px-4 py-1 rounded-[99px] flex justify-center items-center gap-2 transition-colors duration-300 relative z-10 flex-1"
            >
              <div
                className={`text-[13px] font-medium leading-5 font-sans transition-colors duration-300 ${
                  billingPeriod === "annually" ? "text-foreground" : "text-muted-foreground"
                }`}
              >
                Annually
              </div>
            </button>
            <button
              onClick={() => setBillingPeriod("monthly")}
              className="px-4 py-1 rounded-[99px] flex justify-center items-center gap-2 transition-colors duration-300 relative z-10 flex-1"
            >
              <div
                className={`text-[13px] font-medium leading-5 font-sans transition-colors duration-300 ${
                  billingPeriod === "monthly" ? "text-foreground" : "text-muted-foreground"
                }`}
              >
                Monthly
              </div>
            </button>
          </div>
        </div>
      </div>

      {/* Pricing Cards */}
      <div className="self-stretch border-b border-t border-border flex justify-center items-center">
        <div className="flex-1 flex flex-col md:flex-row justify-center items-center gap-6 py-12 max-w-[1060px]">
          {/* Starter */}
          <div className="flex-1 self-stretch px-6 py-5 border border-border overflow-hidden flex flex-col justify-start items-start gap-12">
            <div className="self-stretch flex flex-col justify-start items-center gap-9">
              <div className="self-stretch flex flex-col justify-start items-start gap-2">
                <div className="text-foreground/90 text-lg font-medium leading-7 font-sans">Starter</div>
                <div className="w-full max-w-[242px] text-muted-foreground text-sm font-normal leading-5 font-sans">
                  Self-hosted, local SQLite storage, for individuals evaluating the pipeline.
                </div>
              </div>
              <div className="self-stretch flex flex-col justify-start items-start gap-2">
                <div className="text-foreground text-5xl font-medium leading-[60px] font-display">
                  ${pricing.starter[billingPeriod]}
                </div>
                <div className="text-muted-foreground text-sm font-medium font-sans">
                  per {billingPeriod === "monthly" ? "month" : "year"}
                </div>
              </div>
              <div className="self-stretch px-4 py-[10px] bg-primary overflow-hidden rounded-[99px] flex justify-center items-center">
                <div className="text-primary-foreground text-[13px] font-medium leading-5 font-sans">Start for free</div>
              </div>
            </div>
            <div className="self-stretch flex flex-col justify-start items-start gap-2">
              {["Unlimited local documents", "Hybrid BM25 + dense retrieval", "Entity graph (opt-in)", "Faithfulness scoring", "Community support"].map(
                (feature) => (
                  <div key={feature} className="self-stretch flex justify-start items-center gap-[13px]">
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M10 3L4.5 8.5L2 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-muted-foreground" />
                    </svg>
                    <div className="flex-1 text-foreground/80 text-[12.5px] font-normal leading-5 font-sans">{feature}</div>
                  </div>
                ),
              )}
            </div>
          </div>

          {/* Team (featured) */}
          <div className="flex-1 self-stretch px-6 py-5 bg-primary/10 border border-primary/30 overflow-hidden flex flex-col justify-start items-start gap-12">
            <div className="self-stretch flex flex-col justify-start items-center gap-9">
              <div className="self-stretch flex flex-col justify-start items-start gap-2">
                <div className="text-foreground text-lg font-medium leading-7 font-sans">Team</div>
                <div className="w-full max-w-[242px] text-muted-foreground text-sm font-normal leading-5 font-sans">
                  Managed Supabase storage and hosted Gemini calls for a shared document corpus.
                </div>
              </div>
              <div className="self-stretch flex flex-col justify-start items-start gap-2">
                <div className="text-foreground text-5xl font-medium leading-[60px] font-display">
                  ${pricing.team[billingPeriod]}
                </div>
                <div className="text-muted-foreground text-sm font-medium font-sans">
                  per {billingPeriod === "monthly" ? "month" : "year"}, per seat
                </div>
              </div>
              <div className="self-stretch px-4 py-[10px] bg-foreground overflow-hidden rounded-[99px] flex justify-center items-center">
                <div className="text-background text-[13px] font-medium leading-5 font-sans">Get started</div>
              </div>
            </div>
            <div className="self-stretch flex flex-col justify-start items-start gap-2">
              {["Everything in Starter", "Managed Postgres + pgvector", "Entity graph visualization", "Team-shared document library", "Priority support"].map(
                (feature) => (
                  <div key={feature} className="self-stretch flex justify-start items-center gap-[13px]">
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M10 3L4.5 8.5L2 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-primary" />
                    </svg>
                    <div className="flex-1 text-foreground text-[12.5px] font-normal leading-5 font-sans">{feature}</div>
                  </div>
                ),
              )}
            </div>
          </div>

          {/* Enterprise */}
          <div className="flex-1 self-stretch px-6 py-5 border border-border overflow-hidden flex flex-col justify-start items-start gap-12">
            <div className="self-stretch flex flex-col justify-start items-center gap-9">
              <div className="self-stretch flex flex-col justify-start items-start gap-2">
                <div className="text-foreground/90 text-lg font-medium leading-7 font-sans">Enterprise</div>
                <div className="w-full max-w-[242px] text-muted-foreground text-sm font-normal leading-5 font-sans">
                  On-prem deployment, custom embedding/reranking models, and SSO.
                </div>
              </div>
              <div className="self-stretch flex flex-col justify-start items-start gap-2">
                <div className="text-foreground text-5xl font-medium leading-[60px] font-display">
                  ${pricing.enterprise[billingPeriod]}
                </div>
                <div className="text-muted-foreground text-sm font-medium font-sans">
                  per {billingPeriod === "monthly" ? "month" : "year"}
                </div>
              </div>
              <div className="self-stretch px-4 py-[10px] bg-primary overflow-hidden rounded-[99px] flex justify-center items-center">
                <div className="text-primary-foreground text-[13px] font-medium leading-5 font-sans">Contact sales</div>
              </div>
            </div>
            <div className="self-stretch flex flex-col justify-start items-start gap-2">
              {["Everything in Team", "On-prem / air-gapped deployment", "Custom reranker fine-tuning", "SSO + audit logs", "Dedicated support engineer"].map(
                (feature) => (
                  <div key={feature} className="self-stretch flex justify-start items-center gap-[13px]">
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M10 3L4.5 8.5L2 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-muted-foreground" />
                    </svg>
                    <div className="flex-1 text-foreground/80 text-[12.5px] font-normal leading-5 font-sans">{feature}</div>
                  </div>
                ),
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
