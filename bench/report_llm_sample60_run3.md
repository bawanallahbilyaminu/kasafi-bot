# Kasafi benchmark: llm (with N-ATLaS)

**59/60 passed (98%)** in 324 s

- Answers written by N-ATLaS: 45/60 (75%); the rest fell back to verified figures
- Median time per question: 4.8 s

**Why checks replaced N-ATLaS drafts**

| Reason | Count |
|---|---|
| ungrounded number | 5 |

## By category

| Group | Passed | Rate |
|---|---|---|
| agency | 4/4 | 100% |
| alloc | 4/4 | 100% |
| analysis | 4/4 | 100% |
| function | 4/4 | 100% |
| greeting | 4/4 | 100% |
| history | 4/4 | 100% |
| lga | 3/3 | 100% |
| lga_untagged | 3/3 | 100% |
| measure | 3/3 | 100% |
| multi | 3/3 | 100% |
| out_of_scope | 3/3 | 100% |
| overview | 3/3 | 100% |
| project | 3/3 | 100% |
| rate2025 | 2/3 | 67% |
| revenue | 3/3 | 100% |
| robust | 3/3 | 100% |
| spent2025 | 3/3 | 100% |
| spent2026 | 3/3 | 100% |

## By difficulty (1 easy - 4 hard)

| Group | Passed | Rate |
|---|---|---|
| 1 | 14/14 | 100% |
| 2 | 22/22 | 100% |
| 3 | 16/17 | 94% |
| 4 | 7/7 | 100% |

## By language

| Group | Passed | Rate |
|---|---|---|
| en | 24/24 | 100% |
| ha | 35/36 | 97% |

## Failed checks

| Check | Failures |
|---|---|
| figure | 1 |

## Failures

- `rate2025-001` **Kashi nawa aka aiwatar na kasafin lafiya a 2025?** → intent `mda`, entities ['052100000000']; failed: figure (expected 052100000000)
