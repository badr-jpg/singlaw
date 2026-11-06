> Earlier team summary, using each person's original judge and scale. The headline numbers for the report are in REPORT_PACK.md.

# SingLaw evaluation: combined results

Five of the six benchmark partitions have been evaluated, giving 1,000 labelled questions. Haotien's partition has no results yet.

## Summary

- **Answer quality is high when SingLaw gives an answer.** Mean correctness is 0.931 across 1,000 questions (95% CI 0.917–0.946), and 90.4% of answers are fully correct.
- **Blank answers are the largest single failure.** 27 answers were blank and 2 were cut off, which accounts for 29 of the 44 answers that scored 0. Excluding blanks, correctness rises to 0.957.
- **Questions that need two or more documents are the weakest type.** `multi_hop` scores 0.850, and 14 of the 27 blank answers are `multi_hop`.
- **Questions in everyday language are the hardest to retrieve for.** `lay_language` Hit@10 is 0.771, against 0.979 for `provision_lookup`.
- **The right case is found, but not the right passage.** `case_law` finds the gold case every time, but MRR is only 0.347. Answers are still good (0.980).
- **Differences between people should not be read as system differences.** Each run differs in its questions, and most differ in judge or setup too (see [Comparability](#comparability)).

## What was combined

| Person | Source | Questions | Reranker | Index and embedding | Judge and rubric | Run on |
|---|---|---|---|---|---|---|
| badr | Local run, not pushed | Written by Claude Haiku | Qwen3-Reranker-0.6B, top 50 | Published index, Qwen3 | Claude Haiku 5.5, `judge_claude.py` | M4 Max, 8 at once |
| binyao | [PR #8](https://github.com/badr-jpg/singlaw/pull/8) @ `530edfd`, MiniMax run | Authoring model not recorded | ms-marco-MiniLM-L-6-v2, depth not stated | Published index, Qwen3 | Claude (model not recorded), 2/1/0 | Windows CPU, 5 at once |
| darien | [PR #7](https://github.com/badr-jpg/singlaw/pull/7) @ `3a14fc3`, original run | Authoring model not recorded | Qwen3-Reranker-0.6B, top 50 | Published index, Qwen3 | Claude Opus 5.5, `judge_claude.py` | MacBook Air, 1 at a time |
| huang | [PR #9](https://github.com/badr-jpg/singlaw/pull/9) @ `c2e0431` | Authoring model not recorded | ms-marco-MiniLM-L-6-v2, depth not stated | **Rebuilt index, MiniLM**, no citation graph | Claude Sonnet 5.5, 0–4 per dimension | Dev profile |
| sumo | Branch `worktree-eval-sumo-benchmark` @ `fd2d898` | Authoring model not recorded | ms-marco-MiniLM-L-6-v2, depth not stated | Published index, Qwen3 | Claude (model not recorded), 2/1/0; run by binyao | Windows CPU, 5 at once |

All five used MiniMax-M3 to generate answers. Each person's first run is used, with no retries. Sumo's results were merged in PR #10 and reverted in PR #11, so they exist only on that branch.

## Results by person

| Person | Correctness (95% CI) | Excl. blanks | Fully correct | Scored 0 | Blank | Hit@10 | MRR | Context recall | Median s |
|---|---|---|---|---|---|---|---|---|---|
| badr | 0.968 (0.945–0.985) | 0.972 | 94.5% | 1.0% | 1 | 0.950 | 0.688 | 0.955 | 42 |
| huang | 0.949 (0.922–0.971) | 0.963 | 90.5% | 2.0% | 3 | n/a | n/a | n/a | n/a |
| darien | 0.928 (0.890–0.963) | 0.951 | 91.5% | 6.0% | 5 | 0.925 | 0.643 | 0.925 | 79 |
| binyao | 0.918 (0.880–0.953) | 0.971 | 90.0% | 6.5% | 11 | 0.865 | 0.666 | 0.888 | 88 |
| sumo | 0.895 (0.858–0.930) | 0.928 | 85.5% | 6.5% | 7 + 2 cut off | 0.810 | 0.567 | 0.835 | 77 |
| **All** | **0.931 (0.917–0.946)** | **0.957** | **90.4%** | **4.4%** | **27 + 2 cut off** | **0.888** | **0.641** | **0.901** | 74 |

Correctness is the judge's score scaled to 0–1. Retrieval covers the 800 questions on the published index, because Huang's sources were not saved.

Faithfulness and relevancy were scored in only three runs, so they don't appear above:

| Person | Faithfulness | Relevancy |
|---|---|---|
| badr | 0.947 | 0.960 |
| darien | 0.967 | 0.845 |
| huang | 0.964 | 0.891 |

## Results by question type

| Type | n | Correctness | Excl. blanks | Fully correct | Blank | Hit@1 | Hit@10 | MRR | Recall@10 | Context recall |
|---|---|---|---|---|---|---|---|---|---|---|
| `provision_lookup` | 300 | 0.973 | 0.990 | 97.0% | 5 | 0.850 | 0.979 | 0.907 | 0.979 | 0.988 |
| `case_law` | 200 | 0.980 | 0.985 | 96.0% | 1 | 0.144 | 0.888 | 0.347 | 0.888 | 0.931 |
| `lay_language` | 300 | 0.911 | 0.933 | 88.7% | 7 | 0.454 | 0.771 | 0.563 | 0.767 | 0.833 |
| `multi_hop` | 200 | 0.850 | 0.914 | 77.5% | 14 | 0.538 | 0.925 | 0.653 | 0.758 | 0.841 |

Correctness by person and type:

| Person | `provision_lookup` | `case_law` | `lay_language` | `multi_hop` |
|---|---|---|---|---|
| badr | 0.983 | 0.988 | 0.967 | 0.925 |
| binyao | 0.950 | 1.000 | 0.892 | 0.825 |
| darien | 0.950 | 0.975 | 0.908 | 0.875 |
| huang | 1.000 | 0.988 | 0.938 | 0.850 |
| sumo | 0.983 | 0.950 | 0.850 | 0.775 |

On the published index, questions with one gold document score 0.944, and those with two or more score 0.829.

## Why answers lost marks

96 of the 1,000 answers were not fully correct. They are grouped below by what the saved run data shows.

| Likely cause | Scored 0 | Partly correct |
|---|---|---|
| Blank answer | 27 | 0 |
| Gold document not among the sources | 9 | 2 |
| Right document, but the gold section or passage was missed | 5 | 11 |
| More than one gold source needed, and some evidence was missing | 1 | 16 |
| All gold evidence retrieved, but the answer was incomplete or wrong | 1 | 8 |
| Can't tell (Huang's sources were not saved) | 1 | 15 |
| **Total** | **44** | **52** |

The two cut-off answers are counted under the retrieval causes because they had some text: `sumo-018` as a missed passage and `sumo-006` as missing evidence. Some "document not among the sources" cases began as wrong refusals rather than search misses, such as `darien-034`, `darien-040` and `sumo-010`.

### 1. Blank answers
- MiniMax reasons for around a minute, then returns only whitespace, while the sources panel is full. Binyao and Darien both suspect the reasoning uses up the shared `max_tokens=8000` budget; this has not been confirmed.
- The rate varies from 1 to 11 per 200 across runs, and the cause of that variation is unknown.
- Retrying recovered 18 of the 25 blank or cut-off answers that were retried (Binyao 8 of 11, Darien 3 of 5, Sumo 7 of 9). Some questions came back blank again, so it isn't purely random.

### 2. Multi-document questions
Answers often cover one part well and say the other isn't in the sources, because the first document takes most of the 20 source slots. Recall@10 is 0.758, even though Hit@10 is 0.925.

### 3. Everyday-language questions
The right document usually arrives (0.938 at 20 sources), but the specific provision or passage often doesn't. Hit@10 varies widely by run, from 0.583 for Sumo to 0.900 for badr. Those runs differ in reranker as well as question style, so the cause can't be separated.

### 4. Judgment passage ranking
The gold case was among the sources for all 160 `case_law` questions on the published index, yet the gold passage ranked first only 14% of the time. Many passages from the same case compete with each other. Answers are rarely harmed, but citations may point to a neighbouring passage.

### 5. Wrong refusals and scope errors
- **Foreign-law mistake:** Singapore Acts were labelled as foreign law (`darien-034`, `darien-040`).
- **Drafting mistake:** a question about appointing a guardian by will was treated as a drafting request (`sumo-010`).

Binyao's earlier GLM run also treated dates in questions as "law as at" filters, which caused 6 failures. That didn't recur with MiniMax in that run, but "As at <year>" openings still appear on older judgments.

### 6. Time budget for query rewriting
Rewriting usually misses its 15 s budget: 156 of 200 questions in badr's run, and every question in Binyao's MiniMax run. Retrieval is mostly running without it.

## Comparability

**Comparable across the four published-index runs:** the retrieval metrics. They were recomputed from the saved chunk IDs with one parser, and they reproduce the published MRR for all four runs to within 0.002. These runs still answered different questions.

**Not directly comparable:**

- **Judges:** four different judge setups were used, and judges disagree. Huang's answers scored 93.1 from Claude and 90.4 from Codex, using the same answers. Badr's Haiku judge appears lenient on relevancy (0.960 against Darien's 0.845 under the same rubric).
- **Scales:** a 0–4 score divided by 4 isn't the same as a 2/1/0 score divided by 2. "Fully correct" is an especially rough match across them.
- **Question sets:** each person's questions come from a different subject area and were written separately. Badr's were written by Haiku.
- **Reranker and depth:** Qwen3 runs (Hit@10 0.938, MRR 0.665) look better than ms-marco runs (0.838, 0.617). The question sets and possibly the rerank depth differ too, so this isn't a controlled test.
- **Timing:** hardware and concurrency vary too much to compare.

**The one controlled comparison:** Binyao ran the same questions and judge with two answer models. On the 189 questions both answered, MiniMax-M3 scored 0.97 and glm-4-flash 0.91.

**Not covered:**
- Haotien's partition: crime, courts, legal profession and the state.
- No run tested Qwen3 at top 150, so the effect of the depth change is unmeasured.
- No two teammates scored the same answers, so judge agreement can't be calculated beyond Huang's Claude and Codex comparison.

## Benchmark validation

All five benchmarks were rerun through `validate_benchmark_pinned.py`:

- All have 200 rows and the required type and source mix.
- All gold IDs belong to the right person.
- Every evidence quote matches its source word for word.

Two kinds of flag remain, and neither affects scoring:

- **`source_type` labels:** Binyao, Huang and Sumo label every multi-document question `mixed`, which the validator flags (25, 30 and 25 rows). The CSV adds `source_kind`, derived from the gold IDs, and that derived value is what should be compared.
- **Possible naming in lay questions:** the validator flags `binyao-154` and `sumo-167` as possibly naming an Act, section or case.

## Recommendations

1. **Fix blank answers first.** Retry or fall back when the text after reasoning is empty, log `finish_reason`, and give the answer its own token allowance. This is the clearest gain available: closing the gap would move correctness towards 0.957.
2. **Stop one document taking all the sources.** Reserve slots across distinct documents, for `multi_hop` questions in particular.
3. **Improve retrieval for everyday-language questions.** Start by making rewriting finish in time: raise the budget or use a faster model, then measure Hit@10 again.
4. **Tighten the scope check.** Don't treat a Singapore Act as foreign because it shares a name with a foreign statute.
5. **Standardise the next round.** Use one runner, one judge and one rubric, save sources in every run, and re-judge all saved answers with a single model. Complete Haotien's partition, and test Qwen3 at top 50 against top 150 on the same questions.

## Files

| File | Contents |
|---|---|
| `data/export/benchmark/combined_results.csv` | One row per question, 1,000 rows. Gitignored because it contains legal text |
| [summary.json](summary.json) | All aggregates and failure question IDs |
| [build_combined.py](build_combined.py) | Rebuilds the CSV and summary |

Main CSV columns:

| Column | Meaning |
|---|---|
| `person`, `question_id`, `question_type` | Identify the question |
| `source_type`, `source_kind`, `multi_document` | Label as written, kind derived from gold IDs, and whether it has 2+ gold documents |
| `correctness_norm`, `correctness_raw`, `correctness_scale` | Score on 0–1, the original score, and its scale |
| `faithfulness_norm`, `relevancy_norm` | Blank where a run didn't score them |
| `blank`, `truncated`, `answer_chars`, `refused_by_judge` | Answer status. `refused_by_judge` is only available for badr and darien |
| `hit_at_1` to `hit_at_20`, `mrr`, `recall_at_10`, `doc_hit_at_20`, `context_recall` | Recomputed retrieval. Blank for Huang |
| `judge`, `reranker`, `judge_reason`, `latency_answer_s` | Run details and the judge's reason |
| `question`, `reference_answer`, `system_answer`, `gold_doc_ids`, `gold_citations` | Full text |
