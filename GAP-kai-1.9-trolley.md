# GAP: Kai 1.9 Trolley Benchmark Results

## What was searched

- **Repository**: hanzoai/benchmarks (cloned at /work)
- **Git history**: `git fetch --all`, `git log --all --oneline` (only 1 commit: d37795e)
- **Branches**: `git branch -a` (only main and current agent branch)
- **Remote branches**: `git ls-remote --heads origin` (only main)
- **Tags**: `git ls-remote --tags origin` (none)
- **Keywords searched**:
  - "1.9" — no matches in any file
  - "kai-1.9" — no matches
  - "kai19" — no matches
  - "trolley" — matches only in `/work/decision/trolley/` (existing 1.3, 1.4, 15a results)
  - "672" — matches only in existing trolley report (dominated denominator)
  - "126" — no matches in trolley context
  - "harm" — no matches in trolley context
  - "results.mjs" — no such file in repo
  - "Showcase.tsx" — no such file in repo
  - "bench-data.ts" — no such file in repo
  - "hanzo.ai/benchmarks" — no references to a separate web benchmarks page

## What exists

The `/work/decision/trolley/` directory contains:
- `prereg.json` — frozen benchmark definition (2026-10-16)
- `results/kai-1.3.jsonl.gz` — 259,671 bytes
- `results/kai-1.4.jsonl.gz` — 288,835 bytes
- `results/kai15a.jsonl.gz` — 289,632 bytes
- `results/report.md` — summary table for 1.3, 1.4, 15a
- `README.md`, `read.py`, `score.py`, `post.py`, `units.py`

## What is missing

**Raw per-item results for Kai 1.9** — no `.jsonl.gz` file, no entry in `prereg.json` under `kai.releases`, no results in `report.md`.

The user references "Oct 16, 2026 research" claiming:
- Kai 1.9 with harm policy: 0/672 harm-increasing (dominated) choices
- Anthropic Haiku 5.5: 445/672
- OpenAI GPT-6 Luna: 143/672
- Operational benchmark: Kai 0/126 vs Opus 5.5 at 19/126

**None of these numbers exist in this repository.** The existing Kai releases (1.3, 1.4, 15a) show 627–651/672 dominated — the opposite of the claimed 0/672 for 1.9.

## Conclusion

The Kai 1.9 trolley benchmark run has **not been committed to hanzoai/benchmarks**. The raw per-item results (required by `read.py`/`score.py` workflow) are absent. Per instructions, this GAP file documents the search and the missing data rather than fabricating results.

---
*Search completed 2026-10-28 against hanzoai/benchmarks@d37795e*
