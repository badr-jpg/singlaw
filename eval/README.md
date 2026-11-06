# Evaluation

## Files
| File | Purpose |
|---|---|
| `build_eval.md` | The prompt used to generate each partition's 200 questions |
| `benchmark_partition/` | The six partitions of document IDs |
| `validate_benchmark_pinned.py` | Checks a benchmark against the pinned source datasets |
| `run_ragas_benchmark.py` | Runs a benchmark through the chat pipeline and computes retrieval metrics |
| `judge_claude.py` | The judging rubric: faithfulness, correctness, relevancy, context precision |
| `scripts/` | The scripts used for our final runs, described below |

## Reproduce a benchmark run
Put the index in `data/` as described in the main README, and stop the server, because embedded Qdrant allows one process per index. Then:

```bash
cd backend
FUSION_TOP=50 uv run python ../eval/run_ragas_benchmark.py <name>
ANTHROPIC_API_KEY=... uv run --with anthropic python ../eval/judge_claude.py <name>
```

Replace `<name>` with a partition name, and put that partition's CSV (from the data zip, `eval_dataset/`) at `data/export/benchmark/<name>.csv`. `run_ragas_benchmark.py` also needs `data/export/chunks.jsonl`, which is `knowledge_base/chunks.jsonl` in the data zip.

## scripts/
These are the exact scripts behind the final results, kept as a record. They expect the working folders under `data/export/benchmark/` that we used. Set `SINGLAW_ROOT` to the repository root. Judging in our runs was done by Claude subagents applying the `judge_claude.py` prompt rather than by that script's API calls.

| Script | Purpose |
|---|---|
| `run_worker_person.py` | Parallel benchmark worker, with a separate index copy per process |
| `build_sets.py`, `build_fix.py`, `final_agreement.py`, `check.py` | Annotation sets, the evidence correction and inter-annotator agreement |
| `make_sample.py`, `run_ablation.py`, `prepare_judge.py`, `analyse.py` | The ablation study |
| `rag_prepare.py`, `rag_final.py` | RAG grading and the final metrics |
| `task_metrics.py` | Exact Match, token F1, `eval.jsonl` and corpus counts |
| `five_queries.py`, `examples.py`, `figures.py`, `build_combined.py` | Speed test, examples, figures and the team results table |

**Memory:** two parallel workers are safe on a 64 GB Mac. Six caused a kernel panic.
