"use client"

import { Asterisk } from "lucide-react"

const steps = [
  {
    title: "Structure-aware parsing",
    description:
      "Every document becomes a hierarchical KnowledgeNode tree - headings, tables, warnings, and figures kept intact instead of flattened into a wall of text.",
  },
  {
    title: "Hybrid retrieval",
    description:
      "BM25 keyword search and dense embeddings run in parallel and get fused by reciprocal rank, so exact terminology and paraphrased questions both surface the right passages.",
  },
  {
    title: "Rerank & grade",
    description:
      "A cross-encoder reranks the fused candidates, then a grading pass drops weak or duplicate matches - every score stays visible in the explainability matrix.",
  },
  {
    title: "Grounded generation",
    description:
      "The answer is generated only from what survived grading, traced back to a source file and page. If the evidence is too weak, the pipeline says so instead of guessing.",
  },
]

export default function DocumentationSection() {
  return (
    <section className="w-full border-b border-border">
      <div className="self-stretch px-4 sm:px-6 md:px-8 lg:px-0 lg:max-w-[1060px] lg:w-[1060px] mx-auto py-16 md:py-24">
        <div className="grid grid-cols-1 gap-10 lg:grid-cols-6 lg:gap-16">
          <div className="col-span-2 h-fit space-y-6 pl-4 md:pl-6 lg:sticky lg:top-10">
            <div className="relative w-fit">
              <h2 className="text-3xl md:text-5xl font-semibold tracking-tight text-foreground">Our pipeline</h2>
              <Asterisk className="absolute -top-1 -right-6 size-5 text-muted-foreground md:size-8 md:-right-9" />
            </div>
            <p className="text-sm md:text-base text-muted-foreground leading-relaxed">
              Four stages, each explainable end to end - no black box between your documents and the answer.
            </p>
          </div>

          <ul className="col-span-4 w-full lg:pl-8">
            {steps.map((step, index) => (
              <li
                key={step.title}
                className="flex flex-col gap-4 border-t border-border py-10 md:flex-row md:gap-10 md:py-12"
              >
                <div className="flex size-10 shrink-0 items-center justify-center bg-muted text-sm text-muted-foreground tracking-tight">
                  0{index + 1}
                </div>
                <div className="pr-4 md:pr-8">
                  <h3 className="mb-3 text-xl md:text-2xl font-semibold tracking-tight text-foreground">
                    {step.title}
                  </h3>
                  <p className="text-sm md:text-base text-muted-foreground leading-relaxed">{step.description}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}
