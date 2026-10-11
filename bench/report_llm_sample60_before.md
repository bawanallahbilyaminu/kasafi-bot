# Kasafi benchmark: llm (with N-ATLaS)

**56/60 passed (93%)** in 315 s

- Answers written by N-ATLaS: 46/60 (77%); the rest fell back to verified figures
- Median time per question: 4.8 s

**Why checks replaced N-ATLaS drafts**

| Reason | Count |
|---|---|
| ungrounded number | 4 |

## By category

| Group | Passed | Rate |
|---|---|---|
| agency | 3/4 | 75% |
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
| rate2025 | 2/3 | 67% |
| revenue | 2/3 | 67% |
| robust | 3/3 | 100% |
| spent2025 | 3/3 | 100% |
| spent2026 | 3/3 | 100% |

## By difficulty (1 easy - 4 hard)

| Group | Passed | Rate |
|---|---|---|
| 1 | 13/14 | 93% |
| 2 | 20/22 | 91% |
| 3 | 16/17 | 94% |
| 4 | 7/7 | 100% |

## By language

| Group | Passed | Rate |
|---|---|---|
| en | 23/24 | 96% |
| ha | 33/36 | 92% |

## Failed checks

| Check | Failures |
|---|---|
| route | 2 |
| figure | 2 |

## Failures

- `lga-001` **Wadanne ayyuka ne za a yi a Wamakko?** → intent `project_status`, entities ['33312100']; failed: route (expected 33312100)
- `rate2025-001` **Kashi nawa aka aiwatar na kasafin lafiya a 2025?** → intent `mda`, entities ['052100000000']; failed: figure (expected 052100000000)
- `agency-002` **How much did Fadama get in 2026?** → intent `mda`, entities ['021510200300']; failed: figure (expected 021510200300)
- `revenue-002` **Nawa ne kudaden shiga na cikin gida (IGR) a 2026?** → intent `mda`, entities ['022000800100']; failed: route
