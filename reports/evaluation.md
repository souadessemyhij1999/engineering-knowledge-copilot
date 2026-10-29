# Evaluation report

All numbers here come from `python scripts/evaluate.py` (raw output in `metrics.json`, per-question rows in `retrieval_results.csv` and `answers_test.csv`). The run takes about 10 seconds on a laptop CPU.

## Setup

- Corpus: 23 documents, 138 chunks (see `data/README.md`)
- Test set: 140 hand-written questions, 119 answerable and 21 that must not be answered (10 restricted for the asking role, 11 not covered by any document)
- Dev set: 48 separate questions. I used it for the abstention threshold and the sentence margin of the extractive answerer, nothing else.
- Every question is asked as a specific demo user, so the role filter is always active.

## Retrieval

Relevance is judged at section level: a chunk counts as relevant if it comes from the gold document, the gold section and the right revision.

| Setup | Hit@1 | Hit@3 | Hit@5 | MRR | nDCG@10 | p50 latency |
|---|---|---|---|---|---|---|
| Dense only (WordLlama) | 0.647 | 0.815 | 0.882 | 0.750 | 0.805 | 4.6 ms |
| BM25 only | 0.866 | 0.941 | 0.975 | 0.912 | 0.928 | 5.6 ms |
| Hybrid, RRF fusion | 0.706 | 0.966 | 0.983 | 0.831 | 0.875 | 10.6 ms |
| **Hybrid + rerank** | **0.924** | **0.992** | **1.000** | **0.957** | **0.967** | 19.9 ms |

What I take from this:

- BM25 beats the dense model by a lot. Shop-floor questions are full of exact tokens (M10, E-205, MC-504, WI-PNT-005), and a 256-dimension static embedding model doesn't separate "the torque table" from "the revision history that mentions the torque".
- Plain RRF fusion is worse than BM25 at rank 1, but it has the best recall in the top 10. Fusion is good at collecting candidates and bad at choosing between them.
- The reranker is where the ranking gets fixed. Compared with RRF alone it corrected the top hit on 27 questions and made it worse on 1.
- By question type (hybrid + rerank, Hit@1): numeric 1.00, factual 0.96, procedural 0.92, table 0.88, cross-document 0.75 (n=4), version questions 0.75 (n=4). Hit@5 is 1.0 for every type.

**Access control.** Over all 140 questions × 4 setups, retrieval returned 0 chunks that the asking role isn't allowed to see. The role filter runs inside Qdrant on every prefetch, so this is by construction, but the test suite checks it anyway.

## Answers (extractive mode, no LLM)

| Metric | Value |
|---|---|
| Answerable questions that got an answer | 88.2 % (105 / 119) |
| Key fact present, answered questions | 96.2 % |
| Key fact present, all answerable (abstaining counts as a miss) | 84.9 % |
| Citation precision (cited chunk is from a gold document) | 95.1 % |
| Answers passing the hallucination guard | 100 % |
| Superseded value given instead of the current one | 0 |
| Restricted questions correctly refused | 10 / 10 |
| Unanswerable questions correctly refused | 11 / 11 |
| Restricted documents shown as sources | 0 |
| Latency p50 / p95 (full pipeline) | 21.5 ms / 37 ms |

The guard pass rate of 100 % is expected in extractive mode, because the answer is copied from the sources. The guard matters for the LLM mode, and the tests check it against made-up LLM answers (a wrong torque value, a citation to a source that doesn't exist, an uncited sentence).

### Abstention threshold

The copilot only answers when the best chunk's *answerability* score (MaxSim + exact matches − missing codes) is above a threshold. I chose it on the dev set by maximising balanced accuracy (`calibration.csv`, `assets/calibration.png`). The best value was 0.80. At that threshold the copilot answered 93.5 % of the answerable dev questions and refused 94 % of the ones it shouldn't answer.

On the test set, 0.80 gave no false answers at all, at the price of 14 answerable questions where the copilot said it couldn't find the answer. For a shop-floor tool I think that's the right side to err on: "not found, check the document" is annoying, while a confident wrong torque value is dangerous.

### Failure cases

The 14 false refusals are questions where the wording differs from the document. Examples are "colour paint pen" against "yellow paint pen", "how much hazardous substance may be kept" against "at most the quantity needed for one shift", and "board fell on the floor" against "boards that fell on the floor are scrapped". The word vectors aren't strong enough to bridge those gaps.

The 4 wrong answers:

| Question | What went wrong |
|---|---|
| t022: what happens if an in-process measurement is out of spec? | It returned the measurement table instead of the rule sentence below it. The table rows match "measurement" and "specification" too well. |
| t086: why was the torque changed in ECN-2026-044? | It returned the change itself (40 → 45 Nm) instead of the reason in section 1. |
| t090: root cause of the oil leakage complaint | It found the right section, but picked the 2nd–4th sentences of the root cause and missed the first one, which names the main cause. |
| t095: why were the bearing seats out of tolerance? | It ranked the problem description above the root cause section. |

Three of the four are *why* questions. The extractive answerer picks the sentence that looks most like the question, but a cause rarely looks like the question. This is the main reason the LLM mode exists.

There is one more weak spot I know about. The version-trap ablation shows that with the current-revision filter switched off, the old Rev B chunk ranks first more often. That's expected; with the filter on (the default), the superseded value never appeared in an answer.

## LLM mode

The LLM mode sends the top 5 chunks to Claude through LangChain (`langchain-anthropic`). It asks for [n] citations and runs the guard on the answer; if the guard fails, it falls back to the extractive answer. I can't run it in my build environment without an API key, so it is measured separately with `notebooks/02_llm_evaluation_colab.ipynb`. That notebook runs the same 140 questions and writes `metrics_llm.json` next to this file.

## How to reproduce

```bash
python scripts/build_corpus.py          # only if you changed data/source
python scripts/evaluate.py --calibrate  # dev set -> threshold
python scripts/evaluate.py              # test set -> metrics.json
python scripts/figures.py               # charts in assets/
```
