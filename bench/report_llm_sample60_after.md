# Kasafi benchmark: llm (with N-ATLaS)

**59/60 passed (98%)** in 322 s

- Answers written by N-ATLaS: 46/60 (77%); the rest fell back to verified figures
- Median time per question: 4.9 s

**Why checks replaced N-ATLaS drafts**

| Reason | Count |
|---|---|
| ungrounded number | 4 |

## By category

| Group | Passed | Rate |
|---|---|---|
| agency | 4/4 | 100% |
| alloc | 4/4 | 100% |
| analysis | 4/4 | 100% |
| function | 4/4 | 100% |
| greeting | 4/4 | 100% |
| history | 4/4 | 100% |
| lga | 2/3 | 67% |
| lga_untagged | 3/3 | 100% |
| measure | 3/3 | 100% |
| multi | 3/3 | 100% |
| out_of_scope | 3/3 | 100% |
| overview | 3/3 | 100% |
| project | 3/3 | 100% |
| rate2025 | 3/3 | 100% |
| revenue | 3/3 | 100% |
| robust | 3/3 | 100% |
| spent2025 | 3/3 | 100% |
| spent2026 | 3/3 | 100% |

## By difficulty (1 easy - 4 hard)

| Group | Passed | Rate |
|---|---|---|
| 1 | 13/14 | 93% |
| 2 | 22/22 | 100% |
| 3 | 17/17 | 100% |
| 4 | 7/7 | 100% |

## By language

| Group | Passed | Rate |
|---|---|---|
| en | 24/24 | 100% |
| ha | 35/36 | 97% |

## Failed checks

| Check | Failures |
|---|---|
| route | 1 |

## Failures

- `lga-001` **Wadanne ayyuka ne za a yi a Wamakko?** → intent `project_status`, entities ['33312100']; failed: route (expected 33312100)
