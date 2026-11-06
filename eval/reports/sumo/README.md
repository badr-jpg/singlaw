# SingLaw evaluation — sumo benchmark (200 questions)

The 200 questions were built by sumo (`data/export/benchmark/sumo.csv`). sumo's laptop ran out of memory after one or two questions, so binyao ran the evaluation, with the same pipeline and the same judge as the binyao MiniMax run (`eval/reports/binyao/`).

Run on 6 Nov 2026, 15:07–16:02 SGT (55 minutes, 5 questions at a time), on a Windows laptop (CPU only). The retry of empty answers ran 16:02–16:07.

## Setup

| | |
|---|---|
| Index | `badlaldh/singlaw-vdb` @ `aecbff97` (43,160 chunks) |
| Embedding | Qwen/Qwen3-Embedding-0.6B (`full` profile, matches the index) |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2. This is a substitute: the `full` rerankers are too slow or too large on CPU. It is the same reranker as the binyao runs. |
| LLM | MiniMax-M3 (fast model MiniMax-M3.1-Flash) |
| Judge | Claude, scoring each answer against the gold answer and gold citations: 2 = correct and complete, 1 = partly correct, 0 = wrong, refused or empty |
| Runner | `tools/run_bench2.py` (concurrency 5, resumable) |

Retrieval is measured on the 20 sources returned with each answer.
- **exact**: the gold Act section (any sub-chunk), or the gold judgment passage, is among the sources.
- **doc**: the gold Act, or any passage of the gold judgment, is among the sources.

sumo's Act citations include subsections, for example `s 3(1)`, `ss 3(2) and 4` and `s 7 (Rule 2)`. The original runner did not parse these, so exact ranks were recomputed afterwards with `tools/fix_exact.py`, which keeps only the section number. "Cited gold" means the answer's `[CITE:n]` markers point to a gold section, or to the gold judgment passage or the passage next to it (`tools/autocite.py`).

## Results

| | n | exact R@1 | exact R@5 | exact R@20 | doc R@20 | answer score | fully correct | partly | wrong/refused/empty | cited gold |
|---|---|---|---|---|---|---|---|---|---|---|
| **Overall** | 200 | 0.43 | 0.72 | 0.84 | 0.97 | **0.895** | 85.5% | 8.0% | 6.5% | 85.0% |
| provision_lookup | 60 | 0.83 | 1.00 | 1.00 | 1.00 | 0.98 | 98.3% | 0% | 1.7% | 98.3% |
| lay_language | 60 | 0.33 | 0.53 | 0.70 | 0.95 | 0.85 | 81.7% | 6.7% | 11.7% | 71.7% |
| case_law | 40 | 0.03 | 0.68 | 0.88 | 1.00 | 0.95 | 92.5% | 5.0% | 2.5% | 85.0% |
| multi_hop | 40 | 0.36 | 0.63 | 0.76 | 0.93 | 0.78 | 65.0% | 25.0% | 10.0% | 85.0% |
| act | 100 | 0.74 | 0.91 | 0.94 | 0.99 | 0.93 | 92.0% | 1.0% | 7.0% | 91.0% |
| judgment | 70 | 0.09 | 0.54 | 0.76 | 0.97 | 0.92 | 88.6% | 7.1% | 4.3% | 77.1% |
| mixed | 30 | 0.18 | 0.50 | 0.68 | 0.90 | 0.73 | 56.7% | 33.3% | 10.0% | 83.3% |

- **Headline:** 0.895, with the 9 empty or truncated answers scored 0.
- **Excluding them:** 0.937 on the other 191 answers.
- **With the retried answers swapped in:** 0.908.

Median time per question was 77 s. Act questions averaged 71 s; mixed questions averaged 102 s.

## Main findings

1. **Empty or truncated answers (9 of 200).**
   - Affected: sumo-006, 018, 071, 077, 121, 167, 171, 172 and 179.
   - Seven came back with no text at all. Two stopped after a few words: 018 after "As at", and 006 after one clause.
   - **This is the same MiniMax problem seen in the binyao run (11 of 200) and in Darien's run (5 of 200).** Generation runs for 60–100 s and then ends with only whitespace, most likely because the reasoning uses up the 8,000-token budget inside `<think>`, which `ThinkTagFilter` strips.
   - Mixed questions are hit hardest: 3 of 30 (171, 172, 179).
   - On retry, 7 of 9 produced an answer; 071 and 171 were empty again (`sumo_emptyretry_judge_retry.jsonl`).
2. **Two-part questions are often answered by halves (mixed 0.73, multi_hop 0.78).** 16 answers scored "partly correct". Most of them answer one part well and then say the other part "is not in the supplied sources", because the second document was not retrieved. Examples:
   - 174: the 2021 SGCA 92 appeal was not retrieved.
   - 183: CGH's systemic failing was not found.
   - 188: Adoption of Children Act s 46 was not retrieved.
   - 192: Infectious Diseases Act s 6 was not retrieved.
   - 184 and 185: the second case's outcome was not found.

   With 20 sources, the first document usually takes most of the slots.
3. **Retrieval misses on lay questions.** A few lay questions were judged 0 because the gold provision never reached the sources, and the answer correctly said it could not find it:
   - 034: Termination of Pregnancy Act s 6, conscientious objection.
   - 055: Probate and Administration Act s 66, executor's commission.
   - 107: Bolam-Bolitho for diagnosis.

   lay_language has the lowest exact R@20 (0.70).
4. **Judgment passages rank low.** Judgment exact R@1 is 0.09 (case_law 0.03), but doc R@20 is 0.97. The right case is almost always found, but the specific gold passage is usually not ranked first, because many passages from the same case compete with each other. The answers are still good: case_law scores 0.95.
5. **One false refusal (sumo-010).** A question about appointing a guardian by will was classified as a request to draft court documents, so nothing was retrieved. sumo's own partial run shows the same refusal, so this is reproducible.
6. **Wrong "as at" date (6 answers).** Answers about older judgments open with "As at <year>-12-31", the year of the judgment: 108, 115, 128, 130, 156 and 160. The answers themselves are correct, so this does not change the score, but the date is misleading.
7. **Act lookups are strong.** provision_lookup scores 0.98, with exact R@5 of 1.00.

## Comparison with the other MiniMax runs

All three runs below use MiniMax. Each runs on a different set of 200 questions.

| | sumo | binyao | Darien |
|---|---|---|---|
| Reranker | MiniLM-L-6 | MiniLM-L-6 | Qwen3-Reranker-0.6B, FUSION_TOP=50 |
| exact R@5 | 0.72 | 0.79 | 0.80 |
| Answer score / correctness | 0.895 | 0.917 | 0.927 |
| Empty answers | 9 (4.5%) | 11 (5.5%) | 5 (2.5%) |
| Score excluding empty | 0.937 | 0.971 | ≈0.95 |
| Question mix (act / judgment / mixed) | 100 / 70 / 30 | 100 / 70 / 30 | 108 / 82 / 10 |

- **The three runs agree within a few points.** The empty-answer bug shows up in all three.
- **sumo's exact R@5 is lower mainly because of judgment passages.** Judgment exact R@5 is 0.54 here, against 0.66 for binyao. Many of sumo's judgment questions cite concluding paragraphs (for example [2009] SGHC 168 at [246]–[247] and [2016] SGHC 168 at [193]–[197]). These likely rank below the summary passages of the same case.

## Caveats

- **Partial scores were judged against the gold answer.** A "1" usually means one part was missing, not that something was wrong.
- **The headline counts empty answers as 0.** The retry is reported separately, as in the binyao report.
- **Exact retrieval keeps only the section number of sumo's Act citations.** A citation such as `s 3(1)` counts as a hit for any chunk of s 3.

## Files

All files are in this folder (`eval/reports/sumo/`), except the benchmark CSV.

| File | Contents |
|---|---|
| `data/export/benchmark/sumo.csv` | the 200-question benchmark (built by sumo) |
| `sumo_run_minimax.jsonl` | SingLaw answers, 20 ranked sources and timings per question (exact ranks recomputed with `fix_exact.py`) |
| `sumo_judge_minimax.jsonl` | Claude's verdict per question: correct (0/1/2), cited_gold, note |
| `sumo_summary_minimax.json` | metrics, overall and by question and source type |
| `sumo_results_minimax.csv` | one row per question with ranks, verdict and answer |
| `sumo_emptyretry.csv`, `sumo_emptyretry_run_retry.jsonl`, `sumo_emptyretry_judge_retry.jsonl` | the 9 empty or truncated questions rerun, and their verdicts |
| `tools/fix_exact.py` | recomputes gold targets and exact ranks for subsection-style citations |
