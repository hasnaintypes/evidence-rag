"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Shimmer } from "@/components/ai-elements/shimmer";

// Cycles through short status phrases instead of a single static
// "Thinking…" the whole wait - these aren't literally synced to the
// backend's own stage completions (query_pipeline.py runs as one blocking
// call with no incremental progress today), but they're the real stage
// order for this request (query rewriting -> hybrid retrieval -> [advanced
// mode only: reranking + the confidence gate] -> generation -> the
// faithfulness check), so the sequence stays honest about what's actually
// happening even though the timing is a heuristic.
const ADVANCED_STEPS = [
  "Thinking…",
  "Searching your documents…",
  "Reading the most relevant passages…",
  "Double-checking the answer…",
];

const NAIVE_STEPS = ["Thinking…", "Searching your documents…", "Writing a response…"];

const STEP_INTERVAL_MS = 1800;

export function ThinkingIndicator({ advancedMode = true }: { advancedMode?: boolean }) {
  const steps = advancedMode ? ADVANCED_STEPS : NAIVE_STEPS;
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    // This component mounts fresh for each pending message (its parent
    // keys the message list by message.id), so stepIndex already starts
    // at 0 with no reset needed here - advancedMode flipping mid-wait
    // isn't a real scenario this has to handle.
    if (steps.length <= 1) return;
    const id = setInterval(() => {
      setStepIndex((i) => Math.min(i + 1, steps.length - 1));
    }, STEP_INTERVAL_MS);
    return () => clearInterval(id);
  }, [steps.length]);

  return (
    <AnimatePresence mode="wait">
      <motion.span
        key={stepIndex}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={{ duration: 0.2 }}
        className="inline-block"
      >
        <Shimmer duration={1.2}>{steps[stepIndex]}</Shimmer>
      </motion.span>
    </AnimatePresence>
  );
}
