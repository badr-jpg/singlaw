# Haotien benchmark — SingLaw results

200 questions (`data/export/benchmark/haotien.csv`) run through SingLaw's retrieval and answer
pipeline, then graded against the gold answers.

## Files

| File | Contents |
|---|---|
| `haotien.results.jsonl` | Per question: generated answer, retrieved sources, recall@1/5/10/20, timing (from `eval/run_benchmark.py`) |
| `haotien.judged.jsonl` | Per question: `correctness` (correct/partial/incorrect), `faithful`, `cites_right_source`, rationale |
| `haotien.gold_index_keys.json` | How each gold source is matched in the index (see "Recall scoring") |
| `haotien_agreement.json`, `haotien_annotation_labels.csv`, `annotation/` | Three-annotator cross-check of the benchmark (see "Annotator cross-check") |

## Results

**Answer quality** (score: correct = 1, partial = 0.5, incorrect = 0)

| Group | n | Score | Correct | Partial | Faithful | Cites gold | R@20 |
|---|---|---|---|---|---|---|---|
| **All** | 200 | **0.948** | 0.925 | 0.045 | 0.980 | 0.950 | 0.907 |
| provision_lookup | 60 | 0.983 | 0.983 | 0.000 | 0.983 | 0.983 | 1.000 |
| case_law | 40 | 0.950 | 0.925 | 0.050 | 0.950 | 1.000 | 0.925 |
| lay_language | 60 | 0.925 | 0.900 | 0.050 | 0.983 | 0.850 | 0.833 |
| multi_hop | 40 | 0.925 | 0.875 | 0.100 | 1.000 | 1.000 | 0.863 |
| Acts | 100 | 0.980 | 0.980 | 0.000 | 0.990 | 0.970 | 1.000 |
| Judgments | 70 | 0.921 | 0.886 | 0.071 | 0.957 | 0.900 | 0.814 |
| Mixed | 30 | 0.900 | 0.833 | 0.133 | 1.000 | 1.000 | 0.817 |

**Retrieval recall**

| Group | n | R@1 | R@5 | R@10 | R@20 |
|---|---|---|---|---|---|
| **All** | 200 | 0.545 | 0.775 | 0.860 | 0.907 |
| Acts | 100 | 0.980 | 0.990 | 1.000 | 1.000 |
| Judgments (exact passage) | 70 | 0.071 | 0.543 | 0.700 | 0.814 |
| Judgments (same case, any passage) | 70 | 0.700 | 0.829 | 0.871 | 0.914 |
| Mixed (exact passage) | 30 | 0.200 | 0.600 | 0.767 | 0.817 |
| Mixed (same case, any passage) | 30 | 0.617 | 0.967 | 0.983 | 0.983 |

The headline recall uses the strict exact-passage match. SingLaw usually finds the right case
but often ranks a neighbouring passage first, which is why judgment recall@1 is low on the
strict measure.

15 questions have recall@20 = 0 (105, 106, 109, 124, 133, 139, 145, 150, 153, 160, 162, 163,
166, 177, 179), all judgment, mixed or lay-language questions.

## Failures worth noting

- **Incorrect (6):** 070, 072, 106, 158, 161, 179
  - 070: SingLaw refused, wrongly calling the Official Secrets Act 1935 Malaysian law (the Act is
    in the index and was retrieved).
  - 072: MiniMax returned an empty answer on all three attempts.
  - 161: the generated answer was truncated after its first line.
  - 106, 158: answer contradicts the gold answer (wrong judgment sum; wrong rule on contributory
    negligence at the damages stage).
  - 179: the answer said its sources did not contain the orders asked about (recall@20 = 0).
- **Partial (9):** 105, 116, 133, 139, 169, 176, 178, 181, 199
- **Unfaithful (4):** 070, 106, 158, 169

## How it was run

- Index: `badlaldh/singlaw-vdb` at the revision pinned in the Makefile (43,160 chunks).
- Embedding model: `Qwen/Qwen3-Embedding-0.6B`.
- **Reranker: `Qwen/Qwen3-Reranker-0.6B`.** The configured `jina-reranker-v2` fails to load with
  the installed `transformers`, so SingLaw falls back to Qwen automatically.
- **`FUSION_TOP=50`** (default 150), matching the setting used in other team runs.
- Answers: MiniMax via SingLaw's `/api/chat` pipeline.
- **Query rewriting/HyDE timed out on roughly half the questions** (about 100 log warnings), so
  those were retrieved with the original question only. This is SingLaw's built-in fallback and
  depends on MiniMax latency.
- Blank answers (029, 072, 133, 145, 179, 185, 188) were retried once or twice; all but 072
  produced a real answer on retry.
- Hardware: WSL2 Ubuntu on Windows, NVIDIA RTX 2050 (4 GB). The Windows GPU driver reset twice
  mid-run; the affected questions were rerun from scratch.

## Code changes in this branch

`backend/app/ml.py` (speed and memory only; scores are unchanged, checked to 0.0 difference):

1. `QwenReranker` uses CUDA when available (it previously chose only `mps` or `cpu`), in fp16.
2. On GPUs with less than 8 GB, the embedder stays on CPU to leave VRAM for the reranker.
3. The reranker passes `logits_to_keep=1`, so it computes only the last position it scores
   instead of full-vocabulary logits for every token (about 1.7 GB less GPU memory per batch).

`eval/run_benchmark.py` and `eval/judge_benchmark.py` are new: the runner and an API-based judge
with the rubric below.

## Recall scoring

The index stores Acts under the same `doc_id` as the benchmark, but stores judgments per case.
The benchmark's judgment gold IDs are passage IDs (e.g. `2004_SGHC_95-0005`), so
`haotien.gold_index_keys.json` maps each one to the chunk citation the index uses
(e.g. `[2004] SGHC 95 at [11]–[14]`). Comparing retrieved `doc_id`s with `gold_doc_ids` directly
would score every judgment question as 0.

## Annotator cross-check of the benchmark

The benchmark itself was checked the same way as the other five partitions
(`eval/scripts/annotation_instructions.md`, `build_sets.py` and `final_agreement.py` in the report
pack): three independent annotators (A, B, C; separate Claude agents) each labelled all 200
questions blind, from their own shuffled batches of 80 (seeds 101/202/303). Each item showed the
question, reference answer, and evidence (quote plus up to 3,000 characters of the index chunk
holding it); no SingLaw answers or judge scores. Labels: is the reference answer correct, is the
question answerable from the evidence, is it standalone. Majority vote decides each label.

**Correction pass.** For 4 items (018, 039, 071, 098) the first batches showed text from the
wrong section, because a generic penalty phrase in the quote also appears in another section.
Annotators B and C flagged this. Those 4 were rebuilt with the cited section and re-labelled by
three fresh annotators; their labels replace the first pass (as the team did for its 135 items).

| Label | Mean pairwise agreement | All three agree | Fleiss' kappa |
|---|---|---|---|
| Reference answer correct | 0.970 | 0.955 | 0.651 |
| Answerable | 0.993 | 0.990 | 0.797 |
| Standalone | 1.000 | 1.000 | 1.000 |

(First pass, before the correction: 0.973 / 0.960 / 0.779 for the reference label. Kappa was
higher only because all three agreed on the 4 wrong-section items as "incorrect".)

**Majority labels:** 192 correct, 8 partial, 0 incorrect; 196 answerable; 200 standalone;
none disputed. **192 questions are clean** (correct, answerable and standalone).
`provision_lookup` questions were all clean.

**SingLaw on clean questions: 0.945**, against 0.948 on all 200, so the flagged questions do not
distort the results (SingLaw scored 1.0 on the 8 partial ones).

Flagged questions (notes in `haotien_annotation_labels.csv`):

| Question | Votes (ref; answerable) | Issue |
|---|---|---|
| 030 | 3 partial; 3 no | Evidence doesn't show that following someone is a contravention of ss 3–7 |
| 164 | 3 partial; 3 no | Reference gives only the defendants' arguments, not what the court held |
| 166 | 3 partial | Leaves out the stated ground (claim legally and factually unsustainable) |
| 175 | 3 partial | 100% judgment and 65/35 split are not in this item's evidence |
| 085 | 3 partial | One condition comes from s 4, but only s 3 is in the evidence |
| 109 | 2 partial; 2 no | Evidence doesn't show the will was invalid because of the signing |
| 162 | 2 partial | Doesn't say what legal consequences follow |
| 100 | 2 partial; 2 no | Evidence covers the s 378 definition, not the s 379 penalty |
| 098 | 1 partial (fix pass) | Omits the up-to-6-strokes caning for a first offence (majority: correct) |

Files: `haotien_agreement.json` (all statistics), `haotien_annotation_labels.csv` (majority
label, votes and notes per question), and `annotation/` (raw labels, correction pass, manifests,
the batch builders, checker, and `haotien_agreement.py`, which reproduces the numbers:
`cd annotation && python haotien_agreement.py ../haotien.judged.jsonl ..`).

## Judging

Graded by **Claude Opus 5.5 inside Claude Code**, not through the API script, using the same rubric
as `eval/judge_benchmark.py`:

- correctness: "correct" if the answer states the key facts of the gold answer without
  contradicting it; "partial" if right but missing or blurring a key element; "incorrect" if wrong,
  contradicting the gold answer, or not answering (refusals count as incorrect).
- faithful: false if the answer asserts something material that the gold answer or evidence
  contradicts.
- cites_right_source: true if the answer's citations include the gold source (Act and section, or
  case; any passage of the gold case counts).

The same model also helped build the benchmark questions, so this is not an independent judge.
Grades can be reproduced with the API judge:
`cd backend && uv run --with anthropic python ../eval/judge_benchmark.py haotien`.
