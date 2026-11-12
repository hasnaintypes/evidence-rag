# Evaluation Report

Eval set: `docs/eval/eval_set.json` (9 questions)

**Ground truth is source-file-level** (did the correct document surface in the
top-K retrieved chunks), not chunk-level - a coarser but honest signal given
this eval set doesn't have per-chunk relevance annotations yet. Includes
multi-part, lexical-overlap, and negative-control questions specifically
designed to differentiate naive from advanced retrieval.

## Summary

Faithfulness is an LLM-as-judge score (0-1) of whether the generated answer's
claims are actually supported by the chunks it was given - a retrieval hit
doesn't guarantee the answer didn't hallucinate or misstate what those chunks say.

| Config | Precision@5 | Recall@5 | MRR | Faithfulness |
|---|---|---|---|---|
| Naive (single-pass, no rerank/grade/compress) | 0.125 | 0.125 | 0.125 | 1.0 (9/9 scored) |
| Advanced (full pipeline) | 0.125 | 0.125 | 0.125 | 1.0 (3/9 scored) |

**Hallucination check:** 1/1 negative-control question(s) answered honestly (naive), 0/1 (advanced).

## Per-question detail

### q1: What type of grease is recommended for the spindle of Horizontal SCARA robots, and after how many hours of movement should the customer apply it?
- Expected source: `ASDAVS-SP002A_Robot_Periodic_Maintenance_Specification_July_2023.pdf`
- Naive retrieved: ['A16B-2200-0900.pdf', 'A16B-2200-0900.pdf'] (MRR: 0.0)
- Advanced retrieved: [] (MRR: 0.0)
- Naive keyword coverage: 67%
- Advanced keyword coverage: 0%
- Naive faithfulness: 1.0 (no unsupported claims)
- Advanced faithfulness: n/a (judge skipped or unavailable)

### q2: Which FANUC CNC series is this Operation and Maintenance Handbook designed for?
- Expected source: `A16B-2200-0900.pdf`
- Naive retrieved: ['A16B-2200-0900.pdf', 'A16B-2200-0900.pdf'] (MRR: 1.0)
- Advanced retrieved: ['A16B-2200-0900.pdf', 'A16B-2200-0900.pdf'] (MRR: 1.0)
- Naive keyword coverage: 100%
- Advanced keyword coverage: 100%
- Naive faithfulness: 1.0 (no unsupported claims)
- Advanced faithfulness: 1.0 (no unsupported claims)

### q3: What happens when the smartPAD is disconnected or removed from the system layout?
- Expected source: `KUKA_Sunrise_Cabinet_Med_en.pdf`
- Naive retrieved: ['A16B-2200-0900.pdf', 'A16B-2200-0900.pdf'] (MRR: 0.0)
- Advanced retrieved: ['A16B-2200-0900.pdf', 'A16B-2200-0900.pdf', 'A16B-2200-0900.pdf'] (MRR: 0.0)
- Naive keyword coverage: 50%
- Advanced keyword coverage: 50%
- Naive faithfulness: 1.0 (no unsupported claims)
- Advanced faithfulness: 1.0 (no unsupported claims)

### q4: What safety stop is triggered by fully pressing the enabling switch to the panic position?
- Expected source: `KUKA_Sunrise_Cabinet_Med_en.pdf`
- Naive retrieved: ['A16B-2200-0900.pdf', 'A16B-2200-0900.pdf'] (MRR: 0.0)
- Advanced retrieved: [] (MRR: 0.0)
- Naive keyword coverage: 50%
- Advanced keyword coverage: 0%
- Naive faithfulness: 1.0 (no unsupported claims)
- Advanced faithfulness: n/a (judge skipped or unavailable)

### q5_multipart: What grease specification applies to Horizontal SCARA robots, and separately, what safety stop is triggered by the enabling switch in panic position?
- Expected source: `ASDAVS-SP002A_Robot_Periodic_Maintenance_Specification_July_2023.pdf`
- Naive retrieved: ['A16B-2200-0900.pdf', 'A16B-2200-0900.pdf'] (MRR: 0.0)
- Advanced retrieved: [] (MRR: 0.0)
- Naive keyword coverage: 33%
- Advanced keyword coverage: 0%
- Naive faithfulness: 1.0 (no unsupported claims)
- Advanced faithfulness: n/a (judge skipped or unavailable)

### q6_lexical_overlap: What operating modes are supported by the robot controller, and what do T1 and T2 mean?
- Expected source: `KUKA_Sunrise_Cabinet_Med_en.pdf`
- Naive retrieved: ['A16B-2200-0900.pdf', 'A16B-2200-0900.pdf'] (MRR: 0.0)
- Advanced retrieved: [] (MRR: 0.0)
- Naive keyword coverage: 50%
- Advanced keyword coverage: 0%
- Naive faithfulness: 1.0 (no unsupported claims)
- Advanced faithfulness: n/a (judge skipped or unavailable)

### q7_narrow_detail: What is the workspace, danger zone, and safety zone of a robot, as defined in the safety documentation?
- Expected source: `KUKA_Sunrise_Cabinet_Med_en.pdf`
- Naive retrieved: ['A16B-2200-0900.pdf', 'A16B-2200-0900.pdf'] (MRR: 0.0)
- Advanced retrieved: ['A16B-2200-0900.pdf', 'A16B-2200-0900.pdf'] (MRR: 0.0)
- Naive keyword coverage: 75%
- Advanced keyword coverage: 75%
- Naive faithfulness: 1.0 (no unsupported claims)
- Advanced faithfulness: 1.0 (no unsupported claims)

### q8_negative_control: What is the maximum flight altitude certified for this robot's drone attachment?
- Type: negative control (no correct source in corpus)
- Naive honest decline: True
- Advanced honest decline: False
- Naive reply preview: 'The provided document chunks do not contain information regarding a drone attachment or its certified flight altitude.\n\nReference:\n- A16B-2200-0900.pdf'
- Advanced reply preview: 'Relevant chunks were found but none passed the relevance grading step.'
- Naive faithfulness: 1.0 (no unsupported claims)
- Advanced faithfulness: n/a (judge skipped or unavailable)

### q9_scanned_page: How long should the coolant system be allowed to cool before servicing the coolant filter, and what is the filter's part number?
- Expected source: `scanned_coolant_filter.pdf`
- Naive retrieved: ['A16B-2200-0900.pdf', 'A16B-2200-0900.pdf'] (MRR: 0.0)
- Advanced retrieved: [] (MRR: 0.0)
- Naive keyword coverage: 0%
- Advanced keyword coverage: 0%
- Naive faithfulness: 1.0 (no unsupported claims)
- Advanced faithfulness: n/a (judge skipped or unavailable)
