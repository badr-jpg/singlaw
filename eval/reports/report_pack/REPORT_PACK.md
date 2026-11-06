> **GitHub copy.** Files containing legal text are left out of the repository: `q2_queries/five_queries.json`, `q3_retrieval/before_after_examples.json`, `q4_eval/eval.jsonl`, `q4_eval/final_results_1000.csv`, `q4_eval/annotation_labels.csv`, `q5_ablation/ablation_per_question.csv`, `q5_ablation/sample.csv` and `figures/ui_05_citation_panel.png`. They are in `report_pack.zip`.

# SingLaw: evidence pack for the report team

This maps every assignment requirement to its numbers, files and figures. Paths are relative to this folder unless stated. The system is **SingLaw**, a question-answering assistant for Singapore law.

## Things you must fill in or do

| Item | Who | Status |
|---|---|---|
| Group number, for the filename `<group number>.pdf` | Report team | Needed |
| All members' names and matriculation numbers, on page 1 | Report team | Needed |
| Upload `singlaw_data.zip` and `singlaw_code.zip`, then put both links in the report | Report team | Zips are ready, in the folder above this one |
| Written answers, and motivation against the state of the art | Report team | Facts below; the Q4 references need checking before citing |
| Slides for the week 13 presentation | Team | 12-slide draft at https://claude.ai/artifact/UT7WjyzE3EUMMSG2UNMxho, with speaker notes. Add the group number and names, and the owner must share the link |

## What the report must disclose

Leaving these out would misdescribe the work.

1. **The labels are AI-generated, not manual.** The brief asks for "manually labeling at least 1,000 records". Our questions and reference answers were written by Claude models, and agreement was measured between three Claude Haiku annotators. Do not call this manual labelling, because that is a known deviation from the brief and could cost marks.
2. **The annotators share one model.** They tend to think alike, so 94.8% agreement probably overstates what independent people would reach. Report it next to Fleiss' kappa (0.58).
3. **135 items were re-annotated.** A bug in our annotation set showed the wrong or incomplete section. All three annotators redid those items blind. Show both results: 94.6% on the first pass, 94.8% after the fix.
4. **Runs differ.** Partitions were run on different machines, and binyao and sumo used a substitute reranker. Differences between people are not system differences.
5. **Judges differ.** Haiku graded badr, binyao, huang and sumo; Opus graded darien.
6. **Coverage.** Haotien's partition has no benchmark, so crime, courts, the legal profession and the state are not tested. The 1,000 questions come from the other five partitions. Judgments cover negligence only.
7. **Ablation limits.** It used 100 questions, each run once. See Q5.

## Q1: Knowledge base

| Measure | Value |
|---|---|
| Documents | 726 (512 Acts, 214 judgments) |
| Chunks | 43,160 (33,160 Act, 10,000 judgment) |
| Words | 11,530,009 (8,536,101 Act, 2,993,908 judgment) |
| Types (unique words) | 56,803 |
| Chunk length, words at p10 / p50 / p90 | 49 / 257 / 586 |

Requirement: at least 10,000 documents or passages and 100,000 words. **Met.** Details: `q1_corpus/corpus_stats.json`. Counts use a lowercase regex tokeniser, stated in that file.

**Gathering**
- Acts: the Hugging Face dataset `Kaidon-Ng/singapore-statutes` @ `8b81a0c`, a copy of Singapore Statutes Online.
- Judgments: our own `badlaldh/singapore-judgments` @ `290e968`, 10,000 passages of about 300 words from 214 Supreme Court negligence judgments, sourced from eLitigation.
- A direct crawl of Singapore Statutes Online returned HTTP 403, so legislation comes from the published copy. See `docs/CORPUS.md` in the code zip.

**Cleaning, chunking and storing**
- Acts are chunked by section, splitting long sections only at subsection boundaries (maximum 4,000 characters), never mid-provision.
- Each judgment passage is one chunk.
- Every chunk also carries a structural context line, such as its Act and Part or its case and paragraphs, and is embedded with that context.
- Storage: embedded Qdrant with named dense and sparse vectors, 611 MB, plus SQLite for documents and the citation graph.

**Task:** cited question answering for the public and for businesses. Sample queries are in Q2.

## Q2: UI and five queries

| Screenshot in `figures/` | Shows |
|---|---|
| `ui_01_home.png` | Home screen |
| `ui_02_answer.png` | Answer with citation chips |
| `ui_03_retrieval_details.png` | Time spent per stage |
| `ui_04_sources.png` | Source library |
| `ui_05_citation_panel.png` | Citation opened |

Run one at a time on an M4 Max with 64 GB. Full results are in `q2_queries/five_queries.json`, and the chart is `figures/fig_q2_five_query_timings.png`.

| Type | Query | Total | First token | Search + rerank only | Top source |
|---|---|---|---|---|---|
| Provision | What duty does the Companies Act 1967 place on a director to act honestly? | 30.7 s | 29.0 s | 5.4 s | Companies Act 1967, s 157 |
| Lay | Can my bank tell someone else about my account details? | 65.3 s | 55.1 s | 5.4 s | Banking Act 1970, s 47 |
| Case law | What must a claimant show to establish a duty of care in negligence under Singapore case law? | 41.0 s | 38.6 s | 5.2 s | [2024] SGHC 249 at [96]–[99] |
| Multi-hop | Under the Moneylenders Act 2008, when can the Registrar forfeit a licensee's security deposit, and how can the licensee challenge it? | 51.1 s | 44.3 s | 5.3 s | Moneylenders Act 2008, s 12 |
| Out of scope | What is the minimum wage in Malaysia? | 0.9 s | 0.9 s | 5.1 s | Refused, no sources used |

Most waiting is on the language model, not on search. "First token" includes all retrieval and the model's reasoning.

## Q3: Retrieval innovations and metrics

### Metrics on all 1,000 questions

`q4_eval/final_metrics.json`, per question in `q4_eval/final_results_1000.csv`.

| | P@1 | P@5 | P@10 | R@5 | R@10 | R@20 | Hit@10 | MRR | nDCG@10 |
|---|---|---|---|---|---|---|---|---|---|
| All 1,000 | 0.560 | 0.184 | 0.102 | 0.804 | 0.871 | 0.916 | 0.902 | 0.667 | 0.699 |
| Clean 908 | 0.572 | 0.186 | 0.102 | 0.816 | 0.883 | 0.922 | 0.910 | 0.676 | 0.710 |

| Type | Hit@10 | MRR | nDCG@10 |
|---|---|---|---|
| `provision_lookup` | 0.983 | 0.925 | 0.940 |
| `lay_language` | 0.803 | 0.601 | 0.644 |
| `case_law` | 0.900 | 0.350 | 0.480 |
| `multi_hop` | 0.930 | 0.694 | 0.641 |

The gold unit is the cited Act section or the exact judgment passage. Recomputing reproduced the published MRR for the earlier runs to within 0.002.

### Ablation on the same 100 questions

`q5_ablation/ablation_summary.json`, chart `figures/fig_q3_retrieval_ablation.png`.

| Run | MRR | nDCG@10 | Hit@10 | R@20 |
|---|---|---|---|---|
| BM25 only | 0.516 | 0.571 | 0.83 | 0.84 |
| Dense only | 0.613 | 0.640 | 0.82 | 0.87 |
| Hybrid | 0.597 | 0.638 | 0.89 | 0.95 |
| Hybrid + reranker | 0.689 | 0.739 | 0.94 | 0.975 |
| Hybrid + rewriting | 0.618 | 0.659 | 0.90 | 0.97 |
| Hybrid + both | 0.686 | 0.728 | 0.92 | 0.965 |

Paired differences, with 95% bootstrap intervals:

| Comparison | MRR | Reading |
|---|---|---|
| Reranker on hybrid | +0.093 (0.039 to 0.147) | Clear gain. nDCG +0.100 (0.053 to 0.151) |
| Hybrid over BM25 | +0.081 (0.046 to 0.119) | Clear gain |
| Hybrid over dense | −0.016 (−0.065 to 0.030) | No ranking gain, but Hit@10 +0.07 and R@20 0.95 against 0.87 |
| Rewriting on hybrid | +0.021 (−0.005 to 0.052) | Not proven |
| Rewriting on reranker | −0.004 (−0.025 to 0.017) | No gain |

### Queries that failed earlier and now work

`q3_retrieval/before_after_examples.json` has the question text, gold citation, rank before and after, and judged correctness where available.

| Improvement | Question | Gold rank before → after |
|---|---|---|
| BM25 → hybrid | `darien-019` A shop's unfair practice: can I go to court? | Not in top 20 → 6 |
| BM25 → hybrid | `sumo-107` Missed X-ray: judged only by other doctors? | Not in top 20 → 6 |
| Dense → hybrid | `huang-125` Humidity measurement, [2014] SGHC 109 | Not in top 20 → 8 |
| Hybrid → reranker | `binyao-164` What must I prove to win a negligence claim? | Not in top 20 → 2 |
| Hybrid → reranker | `sumo-002` Insurer requiring a living will | 17 → 1 |
| Hybrid → rewriting | `binyao-156` Partly careless when hurt: can I get compensation? | Not in top 20 → 20 |

The same file lists 4 questions the reranker made worse. Include these for balance.

### Innovations in the system

| Innovation | Measured here? |
|---|---|
| Hybrid fusion (RRF, k = 60, top 75 per list) | Yes |
| Cross-encoder reranking (Qwen3-Reranker-0.6B, top 50 candidates) | Yes |
| Query rewriting and HyDE | Yes |
| Contextual chunks | No |
| Authority and recency blend (0.60 rerank, 0.25 authority, 0.15 recency) | No |
| In-force filters, date anchoring and citation short-circuit | No; only qualitative examples |

Only claim gains for the measured rows.

## Q4: Generation and evaluation

**Approach to motivate:** generative RAG with MiniMax-M3 (fast helper model MiniMax-M3.1-Flash), where every claim must carry a `[CITE:n]` citation, followed by a check that flags uncited sentences.

**References to verify before citing:** Cormack et al. 2009 (RRF), Gao et al. 2022 (HyDE), Es et al. 2023 (RAGAS), and Lewis et al. 2020 (RAG). The state-of-the-art comparison itself is yours to write.

**Preprocessing:** no microtext normalisation, because legal text is formal. What we did is under Q1. Query analysis extracts citations, dates and scope.

### Evaluation dataset

`q4_eval/eval.jsonl`, 1,000 rows, with no duplicate questions.

| Field | Meaning |
|---|---|
| `question_id`, `partition` | Identifier and owner |
| `question`, `reference_answer` | The item |
| `question_type` | 300 `provision_lookup`, 300 `lay_language`, 200 `case_law`, 200 `multi_hop` |
| `gold_doc_ids`, `gold_citations`, `evidence_quotes` | Gold evidence. All quotes verified word for word against the pinned sources |
| `reference_label`, `answerable`, `standalone` | Majority of three annotators |
| `annotator_votes`, `annotator_notes` | Raw votes and reasons |
| `reannotated_with_full_section` | True for the 135 corrected items |

### Inter-annotator agreement

`q4_eval/agreement.json`. Instructions: `q4_eval/annotation_instructions.md`.

| Label | Mean pairwise agreement | All three agree | Fleiss' kappa | First pass agreement |
|---|---|---|---|---|
| Reference answer right? | **94.8%** | 92.2% | 0.58 | 94.6% |
| Answerable from evidence? | 99.2% | 98.8% | 0.45 | 98.5% |
| Understandable alone? | 97.5% | 96.2% | 0.59 | 97.5% |

Kappa is only moderate because about 94% of labels are "correct", so chance agreement is high.

Majority verdicts: 940 correct, 60 partly correct, 0 incorrect, 6 not answerable, 32 unclear without the source (24 of them Huang's). 908 questions passed all three checks. All 1,000 are kept, and results are shown for both sets.

### Task metrics

`q4_eval/exact_match_f1.json`.

| Set | Exact Match | Token precision | Token recall | Token F1 |
|---|---|---|---|---|
| All 1,000 | 0.001 | 0.198 | 0.779 | 0.282 |

These look low for a structural reason, so explain that in the report: answers are long explanations with a median around 1,030 characters, while references are 1–3 sentences with a median around 180 characters. Recall is the informative number. Judged correctness below is the better measure for generative answers.

### RAG metrics

`q4_eval/final_metrics.json`. Scored with `eval/judge_claude.py`, Darien's rubric from PR #7, with blank answers as 0. This is a RAGAS-style rubric applied by Claude, not the RAGAS library.

| Partition | n | Correctness | Excl. blanks | Faithfulness | Relevancy | Context precision | Blank |
|---|---|---|---|---|---|---|---|
| badr | 200 | 0.968 | 0.972 | 0.947 | 0.960 | 0.685 | 1 |
| huang (rerun) | 200 | 0.940 | 0.964 | 0.949 | 0.943 | 0.742 | 5 |
| darien | 200 | 0.928 | 0.951 | 0.967 | 0.845 | 0.666 | 5 |
| binyao | 200 | 0.878 | 0.929 | 0.920 | 0.918 | 0.634 | 11 |
| sumo | 200 | 0.863 | 0.894 | 0.928 | 0.915 | 0.602 | 7 |
| **All** | **1,000** | **0.915** (0.900–0.930) | **0.942** | **0.942** | **0.916** | **0.666** | **29** |

| Type | Correctness | Faithfulness | Relevancy | Context precision |
|---|---|---|---|---|
| `provision_lookup` | 0.962 | 0.964 | 0.943 | 0.870 |
| `case_law` | 0.965 | 0.971 | 0.960 | 0.448 |
| `lay_language` | 0.875 | 0.921 | 0.877 | 0.638 |
| `multi_hop` | 0.855 | 0.912 | 0.890 | 0.618 |

The clean 908 score 0.923 for correctness. Answers with a partly correct reference score 0.775, against 0.924 for correct references.

**Use 0.915 as the headline.** The earlier team summary gave 0.931, using each person's original judge and scale, and `q4_eval/team_runs_report.md` explains that version. The differences for each person are in `final_results_1000.csv`.

**Haiku against Opus, same 40 of Darien's answers:**

| Metric | Opus | Haiku | Agreement |
|---|---|---|---|
| Correctness | 0.925 | 0.913 | 97.5% |
| Relevancy | 0.825 | 0.925 | 75% |
| Faithfulness | 0.991 | 0.946 | Not compared |
| Context precision | 0.636 | 0.624 | Not compared |

So correctness compares well across these judges, Haiku is lenient on relevancy, and Haiku is stricter on faithfulness. Forty answers is a small sample.

**Reranker groups:** Qwen3 runs (badr, darien, huang) score 0.945 for correctness and 0.700 for MRR. ms-marco runs (binyao, sumo) score 0.870 and 0.617. This is not a controlled test, because the question sets and machines differ too.

### Why answers lost marks

`q4_eval/failure_causes.json` has the question IDs, chart `figures/fig_q4_failure_causes.png`. 121 of 1,000 were not fully correct.

| Cause | Scored 0 | Partly correct |
|---|---|---|
| Blank answer | 29 | 0 |
| Declined or said not found | 15 | 1 |
| Gold section or passage not in sources | 1 | 19 |
| Some gold evidence missing | 1 | 21 |
| All gold evidence retrieved, answer short or wrong | 3 | 31 |

- **Blank answers** are the largest cause of zeros. MiniMax reasons, then returns only whitespace. The team suspects the shared `max_tokens=8000` budget, but this is unconfirmed. Retrying recovered 18 of 25 in earlier runs.
- **Multi-hop:** one document tends to crowd out the others among the 20 sources.
- **Wrong refusals:** some Singapore Acts were labelled as foreign law, such as `darien-034`.

### Performance, cost and scalability

`q4_eval/performance_and_cost.json`.

| Measure | Value |
|---|---|
| End-to-end latency, 2 workers, M4 Max | p50 41.9 s, p90 71.4 s, max 138.4 s |
| Throughput, 8 questions in flight | 200 questions in about 21 minutes, 0.16 per second |
| Model loading | 21.3 s |
| Index size | 611 MB |
| Tokens per answered query, mean of 4 | M3: 10,592 in, 2,994 out. Flash: 1,008 in, 2,494 out |
| Estimated LLM cost | **$0.010–$0.020 per query**, $10–$20 per 1,000 queries |

Local models cost nothing per query. The cost is an estimate, because published prices conflict and no M3.1-Flash output price was found. Prices and sources are in the JSON file. Check MiniMax's pricing page before quoting it.

**Scalability limits we measured**
- Each worker loads its own models and index, about 3.5 GB resident plus GPU memory.
- Embedded Qdrant allows one process per index, so parallel processes need index copies.
- Six workers exhausted memory and caused a kernel panic on a 64 GB Mac that already had about 50 GB in use. Two workers never went below 41% free memory.
- The next step would be a Qdrant server and a shared model service.

## Q5: Answer-level ablation

`q5_ablation/ablation_summary.json`, per question `q5_ablation/ablation_per_question.csv`, chart `figures/fig_q5_answer_ablation.png`. Examples are in `answer_changes` in `q3_retrieval/before_after_examples.json`.

| Run | Correctness | Excl. blanks | Faithfulness | Relevancy | Blank | Median time |
|---|---|---|---|---|---|---|
| A: hybrid | 0.935 | 0.954 | 0.955 | 0.930 | 2 | 13 s |
| B: + reranker | 0.955 | 0.955 | 0.976 | 0.960 | 0 | 35 s |
| C: + rewriting | 0.960 | 0.960 | 0.969 | 0.955 | 0 | 39 s |
| D: + both | 0.895 | 0.942 | 0.925 | 0.915 | 5 | 46 s |
| E: both, no citation rules | 0.915 | 0.963 | 0.891 | 0.850 | 5 | 44 s |

| Effect | Correctness (95% CI) | Reading |
|---|---|---|
| Reranker alone (B − A) | +0.020 (−0.015 to 0.060) | Not proven |
| Rewriting alone (C − A) | +0.025 (−0.005 to 0.060) | Not proven |
| Both (D − A) | −0.040 (−0.095 to 0.010) | Not proven; D has 5 blank answers |
| Citation rules (D − E) | −0.020 (−0.080 to 0.045) | Not proven |

**Citation rules:**
- The grounding check flagged 91 of 95 answers without the rules and 10 of 95 with them, so the rules make answers cite their sources.
- On the 90 questions both runs answered, faithfulness is 0.973 with the rules and 0.942 without. I didn't test that difference for significance.
- On all 100 questions, faithfulness rises 0.034 (−0.029 to 0.097), which is within noise.

**Honest conclusion:** no feature reliably changed answer correctness on 100 questions. The reranker's clear benefit is at the retrieval level (Q3), and the model usually answers correctly once the source is anywhere in the top 20. Rewriting adds time without a proven gain.

**How the runs differ from the live app**
- Sample: 100 questions that passed all annotator checks, 20 per partition, each run once.
- Rewriting budget raised from 15 s to 60 s in all runs, so rewriting could finish. At 15 s it missed the budget on 156 of 200 questions in badr's run.
- Reranker off keeps the fusion order, and the authority and recency blend stays on.
- Citation rules off removes rules 1 and 2 of the system prompt. The grounding check after the answer only flags problems, so turning it off alone would change nothing.
- Rerank depth is `FUSION_TOP=50` throughout. The code default is 150, and no run tested 150 on these questions.
- A comparison where two runs differ by blank answers is not evidence that features conflict. Don't report D as a harmful interaction.

**Other evidence:** Binyao ran the same questions with two answer models. On the 189 both answered, MiniMax-M3 scored 0.97 and glm-4-flash 0.91 (`q4_eval/team_runs_report.md`).

## All figures

| File | Use |
|---|---|
| `fig_pipeline.png` | System overview |
| `fig_q2_five_query_timings.png` | Q2 |
| `fig_q3_retrieval_ablation.png` | Q3 |
| `fig_q4_by_question_type.png` | Q4 |
| `fig_q4_rag_by_partition.png` | Q4 |
| `fig_q4_failure_causes.png` | Q4 |
| `fig_q5_answer_ablation.png` | Q5 |
| `ui_01` to `ui_05` | Q2 |

## Contents of the zips

- **`singlaw_data.zip`:** knowledge base and index, evaluation dataset and labels, five queries, every generated answer, and all Q3 and Q5 data. See its `README.txt`.
- **`singlaw_code.zip`:** source code with locked dependency versions, a `README.md` with run steps, and `eval/README.md`. No API keys, and the personal chat history has been removed.
