"use client"

import { useState } from "react"

interface FAQItem {
  question: string
  answer: string
}

const faqData: FAQItem[] = [
  {
    question: "What is EvidenceRAG and who is it for?",
    answer:
      "EvidenceRAG is a document question-answering system built for technical, industrial, and engineering documents - the kind where a sentence taken out of context is worse than no answer at all. It's for teams who need to trust the answer, not just get one.",
  },
  {
    question: "What file formats can I ask questions about?",
    answer:
      "Markdown, PDF (including scanned/image-only pages via Gemini vision), Word, Excel, and CSV. Every parser produces the same hierarchical KnowledgeNode tree, so retrieval logic doesn't depend on the source format.",
  },
  {
    question: "How is this different from a typical RAG chatbot?",
    answer:
      "Hybrid BM25 + dense retrieval with reciprocal rank fusion, cross-encoder reranking, relevance grading, full parent-section reconstruction, and one bounded follow-up retrieval hop when confidence is low - all before generation even starts.",
  },
  {
    question: "What happens when the answer isn't in the documents?",
    answer:
      "It says so. There are no hardcoded fallback answers - when retrieval confidence is too low or the evidence doesn't support a claim, the pipeline returns an explicit failure state and shows you the retrieved references instead of guessing.",
  },
  {
    question: "Can I verify where an answer came from?",
    answer:
      "Every answer ships with source file, page number, and section heading path. An explainability matrix also exposes BM25 score, dense score, fusion rank, and rerank score for every candidate chunk that was considered.",
  },
  {
    question: "How do you know the answers are actually faithful to the source?",
    answer:
      "A second, cheap LLM call acts as a judge: given the generated answer and the exact chunks it was allowed to use, it returns a 0-1 support score and flags any unsupported claims. This catches hallucination that retrieval metrics alone can't.",
  },
]

function ChevronDownIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export default function FAQSection() {
  const [openItems, setOpenItems] = useState<number[]>([])

  const toggleItem = (index: number) => {
    setOpenItems((prev) => (prev.includes(index) ? prev.filter((i) => i !== index) : [...prev, index]))
  }

  return (
    <div className="w-full flex justify-center items-start">
      <div className="flex-1 px-4 md:px-12 py-16 md:py-20 flex flex-col lg:flex-row justify-start items-start gap-6 lg:gap-12">
        {/* Left Column - Header */}
        <div className="w-full lg:flex-1 flex flex-col justify-center items-start gap-4 lg:py-5">
          <div className="w-full flex flex-col justify-center text-foreground font-semibold leading-tight md:leading-[44px] font-sans text-4xl tracking-tight">
            Frequently Asked Questions
          </div>
          <div className="w-full text-muted-foreground text-base font-normal leading-7 font-sans">
            Explainable retrieval, honest failure, and citations
            <br className="hidden md:block" />
            you can actually check.
          </div>
        </div>

        {/* Right Column - FAQ Items */}
        <div className="w-full lg:flex-1 flex flex-col justify-center items-center">
          <div className="w-full flex flex-col">
            {faqData.map((item, index) => {
              const isOpen = openItems.includes(index)

              return (
                <div key={index} className="w-full border-b border-border overflow-hidden">
                  <button
                    onClick={() => toggleItem(index)}
                    className="w-full px-5 py-[18px] flex justify-between items-center gap-5 text-left hover:bg-muted/40 transition-colors duration-200"
                    aria-expanded={isOpen}
                  >
                    <div className="flex-1 text-foreground text-base font-medium leading-6 font-sans">
                      {item.question}
                    </div>
                    <div className="flex justify-center items-center">
                      <ChevronDownIcon
                        className={`w-6 h-6 text-muted-foreground transition-transform duration-300 ease-in-out ${
                          isOpen ? "rotate-180" : "rotate-0"
                        }`}
                      />
                    </div>
                  </button>

                  <div
                    className={`overflow-hidden transition-all duration-300 ease-in-out ${
                      isOpen ? "max-h-96 opacity-100" : "max-h-0 opacity-0"
                    }`}
                  >
                    <div className="px-5 pb-[18px] text-muted-foreground text-sm font-normal leading-6 font-sans">
                      {item.answer}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
