# Build the eval

Copy this prompt into Claude Code from the repo root. Replace `<my name>` with your lowercase name as used in the filenames in `eval/benchmark_partition/`: `badr`, `darien`, `haotien`, `huang`, `sumo` or `binyao`.

```text
Generate a labelled Q&A benchmark of 200 questions from my subset of the SingLaw corpus. Do not use outside legal knowledge: every question must be answerable from the source text alone.

Inputs
- My document IDs: eval/benchmark_partition/<my name>.txt
- Details for those IDs: the "<my name>" entry in eval/benchmark_partition/partition.json
- Judgments: badlaldh/singapore-judgments @ 290e968, data/train-00000-of-00001.parquet; match on the doc_id column
- Acts: Kaidon-Ng/singapore-statutes @ 8b81a0c, data/sections.parquet; load each Act by its source_rows range (inclusive, 0-based), never by name

Mix
- 100 from Acts, 70 from judgments, 30 that need two or more documents
- Question types: 60 provision_lookup, 60 lay_language, 40 case_law, 40 multi_hop
- At most 12 questions from any one document, and cover at least 40 documents
- Skip boilerplate such as short titles, commencement and repeal provisions
- Questions must stand alone, with no "this section" or "the above case"
- lay_language questions use everyday words and don't name the Act or case

Output: data/export/benchmark/<my name>.csv (UTF-8 with a header row; this folder is not committed to git)

Columns
- question_id: <my name>-001 to <my name>-200
- question: the question text
- answer: a correct answer of 1-3 sentences, using only the evidence
- question_type: provision_lookup | lay_language | case_law | multi_hop
- source_type: act | judgment | mixed
- gold_doc_ids: IDs from <my name>.txt that are needed for the answer, separated by |
- gold_citations: matching citations, separated by |, e.g. "Companies Act 1967, s 157" or "[2026] SGCA 33 at [22]–[23]"
- evidence_quote: an exact quote of up to 40 words for each gold document, separated by |, in the same order

Before finishing, run a script that confirms:
- There are exactly 200 rows, with no duplicate questions and the required counts above
- Every gold_doc_id is in <my name>.txt
- Every evidence_quote appears word for word in its gold document, ignoring differences in whitespace

Fix any failures, then report the counts and any documents you skipped and why.
```
