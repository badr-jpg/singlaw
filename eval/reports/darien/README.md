# Benchmark results: Darien's 200 questions

SingLaw was evaluated on the 200 labelled questions built from Darien's partition
(`eval/benchmark_partition/darien.txt`, following `eval/build_eval.md`).

| File | Contents |
|---|---|
| `data/export/benchmark/darien.csv` | the 200-question benchmark (validated with `eval/validate_benchmark_pinned.py darien`) |
| `eval/results/darien_*` | raw run output: SingLaw's answers, the 20 sources per question (with excerpts of judgment and Act text), and the per-question judgments |
| `eval/reports/darien/` (this folder) | summaries and per-question scores, with identifiers only |

The raw results and the benchmark contain text from Singapore judgments and statutes
(© Government of Singapore). Keep this repository private.

File naming in `eval/results/`: `darien_results.original.jsonl` is the original run, which is the headline result.
`darien_results.jsonl` is the same run with the 5 blank answers retried. `darien_rerun_*` holds the 8 other
failures, rerun with the LLM cache cleared. Each run has matching `_retrieval`, `_judged` and `_judge` files.

## Setup

| Setting | Value |
|---|---|
| Index | published `badlaldh/singlaw-vdb` (`make index`), `full` model profile |
| Reranker | `Qwen/Qwen3-Reranker-0.6B`, rerank depth `FUSION_TOP=50` (default 150 was too slow on a MacBook Air) |
| Answer LLM | MiniMax (query analysis, rewrites and HyDE on) |
| Top-k | 20 sources per question |
| Runner | `eval/run_ragas_benchmark.py darien` |
| Judge | Claude (`claude-opus-5-5`) using the rubric in `eval/judge_claude.py` |

**Retrieval units.** An Act question's gold unit is the cited section; every sub-chunk of that section counts.
A judgment question's gold unit is the exact passage. `ActHit@10` is the lenient version: any chunk of the gold Act.
Context recall is the share of gold evidence quotes found word for word in the sources SingLaw answered from.

**Judge.** Answer correctness (1 / 0.5 / 0) is scored against the reference answer. Faithfulness is the share of the
answer's claims supported by its sources. Answer relevancy is scored 1 / 0.5 / 0. Context precision is the average
precision of the relevant sources, where a source counts as relevant if it contains a gold quote, or it is cited
and the judge did not mark it irrelevant. A blank answer counts as 0 on every judged metric.

## Headline results (original run, 200 questions)

**Retrieval** (`retrieval_original.json`)

| | n | R@5 | R@10 | Hit@10 | MRR | nDCG@10 | Context recall |
|---|---|---|---|---|---|---|---|
| Overall | 200 | 0.795 | 0.895 | 0.925 | 0.643 | 0.696 | 0.925 |
| Acts | 108 | 0.949 | 0.968 | 0.972 | 0.876 | 0.896 | 0.968 |
| Judgments | 82 | 0.628 | 0.811 | 0.854 | 0.366 | 0.461 | 0.878 |
| Mixed | 10 | 0.500 | 0.800 | 1.000 | 0.392 | 0.457 | 0.850 |
| provision_lookup | 60 | 0.967 | 0.967 | 0.967 | 0.914 | 0.928 | 0.967 |
| lay_language | 60 | 0.850 | 0.883 | 0.883 | 0.704 | 0.746 | 0.917 |
| case_law | 40 | 0.725 | 0.875 | 0.875 | 0.289 | 0.427 | 0.925 |
| multi_hop | 40 | 0.525 | 0.825 | 0.975 | 0.498 | 0.541 | 0.875 |

Median latency is 78.7 s per question end to end. 64.2 s of that passes before the sources are ready, which
includes up to 15 s of LLM query rewriting.

**Generation, judged by Claude** (`judge_original.json`)

| | n | Faithfulness | Correctness | Relevancy | Context precision | Refused |
|---|---|---|---|---|---|---|
| Overall | 200 | 0.967 | 0.927 | 0.845 | 0.665 | 3.0% |
| Acts | 108 | 0.956 | 0.921 | 0.847 | 0.794 | 2.8% |
| Judgments | 82 | 0.978 | 0.933 | 0.829 | 0.519 | 3.7% |
| Mixed | 10 | 1.000 | 0.950 | 0.950 | 0.479 | 0% |
| provision_lookup | 60 | 0.983 | 0.950 | 0.875 | 0.843 | 3.3% |
| lay_language | 60 | 0.967 | 0.908 | 0.800 | 0.691 | 5.0% |
| case_law | 40 | 0.980 | 0.975 | 0.875 | 0.494 | 0% |
| multi_hop | 40 | 0.931 | 0.875 | 0.838 | 0.533 | 2.5% |

Per-question scores, with a one-line reason from the judge: `per_question_original.csv`.

## Failure analysis

1. **Blank answers (5 of 200: darien-023, 058, 061, 183, 196).** Each produced its first visible text after about 60 s,
   then ended with only a blank line. The most likely cause is that the MiniMax reasoning model spends its whole
   8,000-token budget (`answer.py`, `max_tokens=8000`) inside `<think>…</think>`, and `ThinkTagFilter` then strips it all.
   On retry, 023, 058 and 196 produced answers, but 061 and 183 came back blank again, so this is a reproducible weakness
   rather than a one-off API glitch. Possible fixes: a larger token budget or capped reasoning, plus a fallback when the
   streamed answer is empty.
2. **Wrong out-of-scope refusals (darien-034, 040).** The query-analysis step labelled the Unfair Contract Terms Act 1977
   as UK law and the Patents Act 1994 as Malaysian, so nothing was retrieved. On rerun 040 passed and 034 was refused again,
   so the scope check is unstable for Singapore Acts that share their names with foreign statutes.
3. **Retrieval misses on judgment facts (darien-033, 113, 118, 132, 135, 195).** The gold passage was not retrieved, and
   SingLaw correctly said it could not find the answer. Judgment questions rank the gold passage low (case_law MRR 0.29)
   because many passages from the same case compete with each other.
4. **Wrong details (darien-069, 133).** 069 added the 6-month cap on top of the 1-month period and answered 7 months
   (fixed on rerun). 133 gave the wrong decision date.
5. **Verbosity.** About a quarter of the answers (48 of 200) scored 0.5 on relevancy for padding, and this is the main drag on relevancy.
   Some answers also carry a wrong "as at" date (for example "as at 1940-12-31"), apparently taken from a source's
   legislative history.

## Reruns (reported separately; the original run is the headline)

* **Blank answers retried in place** (`--only`): `retrieval_with_retries.json`, `judge_with_retries.json`,
  `per_question_with_retries.csv`. Overall correctness rose from 0.927 to 0.940 and faithfulness from 0.967 to 0.982;
  061 and 183 are still blank.
* **Other failures rerun with the LLM cache cleared** (`--tag rerun --no-llm-cache`): `retrieval_rerun.json`,
  `judge_rerun.json`, `per_question_rerun.csv`.

| Question | Failure | Correctness, original → rerun |
|---|---|---|
| darien-033 | retrieval miss | 0 → 1 |
| darien-034 | out-of-scope refusal | 0 → 0 |
| darien-040 | out-of-scope refusal | 0 → 1 |
| darien-069 | misread provision | 0 → 1 |
| darien-113 | retrieval miss | 0.5 → 0.5 |
| darien-118 | retrieval miss | 0 → 0 |
| darien-132 | retrieval miss | 0 → 0 |
| darien-135 | retrieval miss | 0 → 0 |

3 of the 8 were fixed on rerun and 5 failed again, so most of these failures are systematic rather than
caused by sampling noise.

## Reproduce

```bash
make index                                           # HF_TOKEN needed
cd backend
uv run --with pandas --with pyarrow --with huggingface_hub python ../eval/validate_benchmark_pinned.py darien
FUSION_TOP=50 uv run python ../eval/run_ragas_benchmark.py darien
ANTHROPIC_API_KEY=... uv run --with anthropic python ../eval/judge_claude.py darien
```

Caveat: the published scores were judged by Claude in a chat session using the same rubric, not through the API
script. Scoring is on a coarse 1 / 0.5 / 0 scale, and claims were counted by the judge.
