# Huang SingLaw evaluation

This report covers the 200 questions assigned to Huang. Join the answer and score files on `question_id` (`huang-001` through `huang-200`).

- [Benchmark](../../../data/export/benchmark/huang.csv) contains the 200 questions, reference answers, and evidence.
- [SingLaw responses](huang_minimax_answers.csv) contains the saved user-facing answer for each question, including empty responses and refusals.
- [Claude scores](huang_claude_scores.csv) contains per-question scores and judging reasons.
- [Summary](huang_claude_summary.json) contains aggregate scores and coverage.

## Run configuration

SingLaw ran locally with the development profile. The index was rebuilt from the supplied export of 43,160 chunks across 726 documents, using `sentence-transformers/all-MiniLM-L6-v2` for embeddings and `cross-encoder/ms-marco-MiniLM-L-6-v2` for reranking. MiniMax-M3 generated answers. Query rewriting and HyDE were enabled subject to the per-query time budget. The export did not include the citation graph.

Claude Sonnet 5.5 judged the saved answers against the reference answers and supplied evidence. The first five questions were scored in a pilot and the other 195 in batches of five. All 200 question IDs were checked for coverage and duplicates.

## Results

Claude's mean answer score was **93.08/100** across 200 questions. The per-question score is 100 times the sum of correctness, completeness, and answer relevance divided by 12. Each of those dimensions uses a 0–4 scale. The refusal and three empty answers scored zero and are included in the mean. Faithfulness is reported separately and averaged **3.86/4** across the 196 questions with scorable claims. This run measures model-judged performance. Human annotator agreement was not measured.
