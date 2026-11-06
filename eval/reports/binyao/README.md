# SingLaw evaluation — binyao benchmark (200 questions)

Run 6 Nov 2026, 01:15–05:20 SGT, on a Windows laptop (CPU only).

## Setup

| | |
|---|---|
| Index | `badlaldh/singlaw-vdb` @ `aecbff97` (43,160 chunks: 512 Acts, 10,000 passages from 214 judgments) |
| Embedding | Qwen/Qwen3-Embedding-0.6B (`full` profile, matches the index) |
| Reranker | **cross-encoder/ms-marco-MiniLM-L-6-v2 (substitute).** The `full` reranker (jina-reranker-v2) fails to load on this machine and the code falls back to Qwen3-Reranker-0.6B, which took over 30 minutes per question on CPU. |
| LLM | glm-4-flash (Zhipu, OpenAI-compatible) |
| Judge | Claude, scoring each answer against the gold answer and gold citations: 2 = correct and complete, 1 = partly correct, 0 = wrong or refused |

Retrieval is measured on the 20 sources returned with each answer.
- **exact**: the gold Act section, or the gold judgment passage, is among the sources.
- **doc**: the gold Act, or any passage of the gold judgment, is among the sources.

For judgments, "cited gold" also counts a citation of the passage just before or after the gold passage.

## Results

| | n | exact R@1 | exact R@5 | exact R@20 | doc R@20 | answer score | fully correct | wrong/refused | cited gold |
|---|---|---|---|---|---|---|---|---|---|
| **Overall** | 200 | 0.52 | 0.77 | 0.87 | 0.94 | **0.90** | 86.5% | 6.0% | 80.5% |
| provision_lookup | 60 | 0.85 | 1.00 | 1.00 | 1.00 | 0.99 | 98.3% | 0% | 100% |
| lay_language | 60 | 0.38 | 0.67 | 0.77 | 0.87 | 0.83 | 78.3% | 11.7% | 70% |
| case_law | 40 | 0.38 | 0.78 | 0.93 | 1.00 | 1.00 | 100% | 0% | 75% |
| multi_hop | 40 | 0.35 | 0.59 | 0.75 | 0.88 | 0.78 | 67.5% | 12.5% | 72.5% |
| act | 100 | 0.76 | 0.95 | 0.96 | 0.98 | 0.95 | 91% | 2% | 95% |
| judgment | 70 | 0.29 | 0.64 | 0.81 | 0.91 | 0.92 | 91.4% | 7.1% | 67.1% |
| mixed | 30 | 0.23 | 0.48 | 0.67 | 0.83 | 0.72 | 60% | 16.7% | 63.3% |

Average time per question was 74 s: 48 s for Act questions and 97–105 s for judgment and mixed questions.

## Main findings

1. **Dates in the question become a temporal filter.** A question that mentions an event date is answered "as at" the end of that year, and judgments decided later are filtered out. Examples: "the 19 April 2018 collision" is answered as at 2018-12-31, and the 2020/2021 judgments about that collision are dropped.
   - 6 questions were affected: binyao-111, 114, 135, 142, 153 and 189.
   - 5 of them failed completely, with answers saying "the sources do not include this case".
   - This is the largest single cause of failures on the mixed questions. Fix: only treat a date as a temporal anchor when it is phrased as "the law as at / in force in <year>".
2. **Some lay questions are refused as out of scope.** These are legitimate Singapore-law questions:
   - binyao-099: can a damaged passport be cancelled
   - binyao-154: may a driver assume others will take care
   - binyao-166: are the motor accident guides binding
3. **Lay-language questions about case law retrieve worst.** Exact R@20 is 0.77 and 11.7% of answers are wrong.
   - Two answers invert the burden of proof: binyao-157 (contributory negligence) and binyao-158 (bailment).
   - binyao-161 conflates the fertility-treatment holding with loss of dependency.
4. **Citation format drifts on judgment answers.** 23 answers have no `[CITE:n]` markers: some have no citations at all, and others use "[Source n]". The citation validator can't check these.
5. **Statute lookups are strong.** provision_lookup scores 98% fully correct, with the gold section in the top 5 every time. The main weakness there is that answers sometimes add loosely related exceptions from other Acts (binyao-009, 018, 035).
6. **Some wrong statements in multi-hop answers:**
   - binyao-024 says the Marine Insurance Act doesn't address notice of abandonment.
   - binyao-148 names Anns instead of Spandeck as the source of the duty test.
   - binyao-184 says there is no rule on riding PMDs on roads.
   - binyao-192 gives the wrong Computer Misuse Act penalty.

## Caveats

- The reranker substitution probably lowers the ranking metrics (R@1, MRR) compared with the intended `full` setup. R@20 and answer quality should be less affected.
- The questions and the judging were both done by Claude, from the same source passages. Judging was manual and lenient on extra detail, but strict on wrong conclusions and missing key elements.
- glm-4-flash is a small, free model. A stronger generator would probably raise answer scores, especially on multi-hop questions.

## Files

- `data/export/benchmark/binyao.csv`: the 200-question benchmark (all other files are in this folder)
- `binyao_run.jsonl`: raw run output (ranked sources and answer for each question)
- `binyao_judge.jsonl`: judge verdicts with notes
- `binyao_results.csv`: one row per question (ranks, score, note, answer)
- `binyao_summary.json`: all metrics above
- `tools/`: scripts that reproduce this run (`run_bench.py`, `summarize.py`, `show_run.py`, `build_csv.py`)

---

# MiniMax rerun and comparison with GLM

Rerun on 6 Nov 2026, 10:30–11:36 SGT: the same 200 questions, index, embedding model, reranker substitute and judging rubric. Only the LLM changed.

## What changed

| | GLM run | MiniMax run |
|---|---|---|
| LLM | glm-4-flash | MiniMax-M3, with MiniMax-M3.1-Flash as the fast model for query analysis |
| Execution | one question at a time, about 4 h | 5 questions at a time, 66 min wall clock |
| Query rewrite / HyDE | usually within the 15 s budget | **always missed the 15 s budget**, so retrieval used the raw query |
| Judge | Claude, 2/1/0 | Claude, same rubric, same cited-gold rule |

Query analysis (intent, filters, temporal anchor) is also done by the LLM. That is why the retrieval numbers differ a little between the two runs even though the retriever is the same. Per-question times for MiniMax are inflated because 5 questions share the CPU for embedding and reranking.

## Results: GLM → MiniMax

| | n | exact R@5 | exact R@20 | doc R@20 | answer score | fully correct | wrong/refused | cited gold |
|---|---|---|---|---|---|---|---|---|
| **Overall** | 200 | 0.77 → 0.79 | 0.87 → 0.89 | 0.94 → 0.97 | **0.90 → 0.92** | 86.5% → 90% | 6.0% → 6.5% | 80.5% → 86.5% |
| provision_lookup | 60 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 0.99 → 0.95 | 98.3% → 93.3% | 0% → 3.3% | 100% → 95% |
| lay_language | 60 | 0.67 → 0.68 | 0.77 → 0.80 | 0.87 → 0.90 | 0.83 → 0.89 | 78.3% → 88.3% | 11.7% → 10% | 70% → 73% |
| case_law | 40 | 0.78 → 0.78 | 0.93 → 0.93 | 1.00 → 1.00 | 1.00 → 1.00 | 100% → 100% | 0% → 0% | 75% → 95% |
| multi_hop | 40 | 0.59 → 0.64 | 0.75 → 0.81 | 0.88 → 0.98 | 0.78 → 0.83 | 67.5% → 77.5% | 12.5% → 12.5% | 72.5% → 85% |
| act | 100 | 0.95 → 0.95 | 0.96 → 0.97 | 0.98 → 0.99 | 0.95 → 0.92 | 91% → 90% | 2% → 7% | 95% → 91% |
| judgment | 70 | 0.64 → 0.66 | 0.81 → 0.83 | 0.91 → 0.93 | 0.92 → 0.99 | 91.4% → 98.6% | 7.1% → 1.4% | 67.1% → 82.9% |
| mixed | 30 | 0.48 → 0.55 | 0.67 → 0.75 | 0.83 → 0.97 | 0.72 → 0.77 | 60% → 70% | 16.7% → 16.7% | 63.3% → 80% |

| Other counts | GLM | MiniMax |
|---|---|---|
| Empty answers | 0 | **11** |
| False "out of scope" refusals | 3 | 0 |
| Answers without `[CITE:n]` markers | 23 | 0 |
| Failures caused by a date in the question becoming a temporal filter | 6 | 0 |
| Average / median / p90 seconds per question | 74 / 59 / 122 | 97 / 88 / 158 |

GLM's cited-gold figure (80.5%) also counted "[Source n]" references. Counting only `[CITE:n]` markers, as for MiniMax, GLM's figure is 76.5%.

## Main findings

1. **11 MiniMax answers are empty (5.5%), and this accounts for the whole of MiniMax's wrong/refused rate.**
   - Affected questions: binyao-004, 042, 054, 077, 088, 097, 142, 184, 187, 193 and 200.
   - MiniMax-M3 reasons inside `<think>…</think>` for 75 s or more, then emits only `\n\n`, and the stream ends about 10 ms later. `ThinkTagFilter` strips the reasoning, so the user sees a blank answer while the sources panel is full. Retrieval was fine for most of these: 8 of the 11 have the gold section or passage ranked first or second for at least one gold target.
   - Ignoring the empty answers, MiniMax scores 0.97 on the remaining 189 questions, against 0.91 for GLM on the same 189.
   - When the 11 questions were run again (`binyao_emptyretry_run_retry.jsonl`, not counted in the scores above), 8 produced an answer and 3 were empty again (142, 184, 187). So the problem is intermittent but recurs on some questions.
   - Fix: when the text after the reasoning is empty, retry once (or show an extractive fallback); log `finish_reason` to tell a token limit apart from an early stop; and leave room for reasoning tokens, since `max_tokens=8000` covers reasoning and answer together.
2. **MiniMax fixes most of the GLM answer errors.** Excluding empty answers, MiniMax scored higher on 18 questions and lower on 4. Among the fixes:
   - The temporal-anchor failures (111, 114, 135, 153, 189).
   - The false refusals (099, 154, 166).
   - The reversed burden of proof (157).
   - The dependency mix-up (161).
   - The notice-of-abandonment error (024) and Spandeck vs Anns (148).
3. **Citation discipline is much better.** Every non-empty MiniMax answer uses `[CITE:n]` markers. On judgment questions, cited gold rises from 67% to 83%.
4. **Remaining MiniMax answer errors, apart from the empty answers:**
   - binyao-158: says the owner must prove carelessness, missing that a bailee bears the burden. GLM got this wrong too.
   - binyao-087 and 088: RTA ss 73 and 84 were not retrieved, so the answer says the sources don't cover the point.
   - binyao-192: gives the Computer Misuse Act s 6 penalty instead of s 3. GLM got this wrong too.
   - binyao-056: answers via Customs Act s 108 instead of Postal Services Act s 13.
   - Partial answers on 039, 098, 119, 128 and 188.
   - One answer cites the right section under the wrong source number: binyao-079 refers to s 4 but `[CITE:4]` points to s 6.
5. **Style.**
   - Lay and low-confidence answers often open with "I could not find strong authority…" even when the answer that follows is correct and well cited.
   - Answers are longer and more heavily hedged than GLM's.
   - 10 case-law answers are anchored "As at <year>-12-31", the year in the case citation. None was harmed by it, but the anchor is still triggered by any year in the question.
6. **Rewrite/HyDE never finished within its 15 s budget.** It is effectively off for MiniMax, so MiniMax's retrieval gains come from the analysis stage, not from rewriting. Either raise the pre-stage budget or use the fast model for rewriting.

## Recommendation

On answer quality, MiniMax-M3 is clearly the better generator: 0.97 vs 0.91 on the questions both answered, no false refusals, no missing citation markers, and no temporal-anchor failures. It is about 30% slower per question. It should not be shipped until the empty-answer bug is handled, because 1 in 18 users currently gets a blank reply.

## Additional files

- `binyao_run_minimax.jsonl`, `binyao_judge_minimax.jsonl`, `binyao_results_minimax.csv`, `binyao_summary_minimax.json`: the MiniMax run, judge verdicts and metrics
- `binyao_emptyretry.csv`, `binyao_emptyretry_run_retry.jsonl`: the retry of the 11 empty answers (for information only)
- `tools/run_bench2.py`: concurrent, resumable runner (`<repo> <name> <tag> <concurrency>`)
- `tools/summarize.py`: now takes `[tag] [llm label]`
- `tools/autocite.py`: automatic cited-gold check
