"""Run the Kasafi benchmark and score every answer automatically.

  python bench/run_benchmark.py                 rules + retrieval only (no models; runs anywhere, ~10 s)
  python bench/run_benchmark.py --llm           full engine with N-ATLaS (on Colab / the laptop GPU)
  python bench/run_benchmark.py --only lga,robust --limit 40
  python bench/run_benchmark.py --llm --sample 60           quick N-ATLaS run, spread across all categories
  python bench/run_benchmark.py --set holdout2              held-out questions (never used for tuning)

Writes bench/results_<mode>.jsonl and bench/report_<mode>.md. Interactions go to a separate log
(bench/bench_log.sqlite, channel "benchmark"), so they never count as real user interactions.

A question passes when every check that applies to it passes:
  route    the engine chose one of the accepted intents
  entity   it recognised the expected ministry/agency, LGA or cross-cutting function
  figure   the expected amount or percentage appears in the answer
  text     an expected project name appears (LGA questions)
  items    project questions return a list of projects
  scope    out-of-scope questions get no budget figures
"""
import argparse
import json
import os
import re
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="use N-ATLaS (needs the GPU models)")
    ap.add_argument("--only", default="", help="comma-separated categories")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--set", default="questions", help="questions (main), holdout or holdout2")
    ap.add_argument("--sample", type=int, default=0, help="N questions spread evenly across categories (quick N-ATLaS runs)")
    a = ap.parse_args()
    mode = ("llm" if a.llm else "rules") + ("" if a.set == "questions" else f"_{a.set}")
    os.environ.setdefault("LOG_DB", str(ROOT / "bench" / "bench_log.sqlite"))
    if not a.llm:
        os.environ["LLM_BACKEND"] = "none"
    os.environ["ASR_ENABLED"] = "0"
    os.environ["TTS_ENABLED"] = "0"
    os.environ["REQUIRE_REGISTRATION"] = "0"

    from app.answer import NOT_FOUND_EN, NOT_FOUND_HA
    from app.engine import Engine

    qs = [json.loads(l) for l in (ROOT / "bench" / f"{a.set}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if a.only:
        keep = set(a.only.split(","))
        qs = [q for q in qs if q["category"] in keep]
    if a.sample and a.sample < len(qs):
        by_cat = defaultdict(list)
        for q in qs:
            by_cat[q["category"]].append(q)
        picked, i = [], 0
        while len(picked) < a.sample:
            for cat in sorted(by_cat):
                if i < len(by_cat[cat]) and len(picked) < a.sample:
                    picked.append(by_cat[cat][i])
            i += 1
        qs = picked
    if a.limit:
        qs = qs[:a.limit]

    eng = Engine(load_models=a.llm)
    results = []
    t_all = time.time()
    for i, q in enumerate(qs, 1):
        t0 = time.time()
        rep = eng.handle_text("benchmark", "bench", q["question"])
        ms = int((time.time() - t0) * 1000)
        rec = eng.logs.admin_get(rep.interaction_id) or {}
        try:
            ent = json.loads(rec.get("entities") or "{}") if isinstance(rec.get("entities"), str) else (rec.get("entities") or {})
        except ValueError:
            ent = {}
        intent = rec.get("intent") or "none"
        ans = rep.text or ""
        checks = {}
        if q.get("scope") == "out":
            checks["scope"] = ("₦" not in ans) or ans.startswith((NOT_FOUND_HA[:20], NOT_FOUND_EN[:20]))
        else:
            checks["route"] = intent in q["intents"]
        if q.get("mda"):
            got = ent.get("mda") or []
            checks["entity"] = bool(got) and (got[0] == q["mda"] or q["mda"] in got[:1]
                                             or (q["mda"].endswith("00000000") and got[0][:4] == q["mda"][:4] and intent == "mda"))
        if q.get("lga"):
            checks["entity"] = q["lga"] in (ent.get("lga") or [])
        if q.get("func"):
            checks["entity"] = q["func"] in (ent.get("function") or [])
        if q.get("figures"):
            checks["figure"] = any(f in ans for f in q["figures"]) or any(
                re.search(r"(?<![\d.])" + re.escape(re.sub(r"[^\d.]", "", f).strip(".")) + r"(?![\d.])", ans)
                for f in q["figures"] if ("%" in f or "cikin 100" in f))
        if q.get("texts"):
            checks["text"] = any(t.lower()[:30] in ans.lower() for t in q["texts"])
        if q.get("wants_items"):
            checks["items"] = ans.count("₦") >= 2
        ok = all(checks.values()) if checks else True
        results.append({**q, "got_intent": intent, "got_entities": ent, "answer_source": rec.get("answer_source"),
                        "grounding_fail": rec.get("grounding_fail"), "checks": checks, "pass": ok, "ms": ms,
                        "answer": ans[:1200]})
        if i % 25 == 0 or i == len(qs):
            print(f"  {i}/{len(qs)}  pass so far {sum(r['pass'] for r in results)}/{len(results)}", flush=True)

    out = ROOT / "bench" / f"results_{mode}.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in results) + "\n", encoding="utf-8")
    write_report(results, mode, time.time() - t_all)


def write_report(results, mode, secs):
    by = lambda key: _group(results, key)
    n, p = len(results), sum(r["pass"] for r in results)
    lines = [f"# Kasafi benchmark: {mode.replace('_', ', ')} ({'with N-ATLaS' if mode.startswith('llm') else 'rules + retrieval, N-ATLaS off'})", "",
             f"**{p}/{n} passed ({100 * p / n:.0f}%)** in {secs:.0f} s", ""]
    if mode.startswith("llm"):
        nat = sum(r["answer_source"] == "natlas" for r in results)
        lat = [r["ms"] for r in results]
        lines += [f"- Answers written by N-ATLaS: {nat}/{n} ({100 * nat / n:.0f}%); the rest fell back to verified figures",
                  f"- Median time per question: {statistics.median(lat) / 1000:.1f} s", ""]
        reasons = defaultdict(int)
        for r in results:
            if r["grounding_fail"]:
                reasons[r["grounding_fail"].split(":")[0].split("₦")[0].strip()[:60]] += 1
        if reasons:
            lines += ["**Why checks replaced N-ATLaS drafts**", "", "| Reason | Count |", "|---|---|"]
            lines += [f"| {k} | {v} |" for k, v in sorted(reasons.items(), key=lambda x: -x[1])] + [""]
    for title, key in (("By category", "category"), ("By difficulty (1 easy - 4 hard)", "difficulty"), ("By language", "lang")):
        lines += [f"## {title}", "", "| Group | Passed | Rate |", "|---|---|---|"]
        for g, rs in sorted(by(key).items(), key=lambda x: str(x[0])):
            k = sum(r["pass"] for r in rs)
            lines.append(f"| {g} | {k}/{len(rs)} | {100 * k / len(rs):.0f}% |")
        lines.append("")
    fails = defaultdict(int)
    for r in results:
        for c, v in r["checks"].items():
            if not v:
                fails[c] += 1
    lines += ["## Failed checks", "", "| Check | Failures |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(fails.items(), key=lambda x: -x[1])]
    lines += ["", "## Failures", ""]
    for r in results:
        if not r["pass"]:
            bad = ", ".join(k for k, v in r["checks"].items() if not v)
            exp = r.get("mda") or r.get("lga") or r.get("func") or ""
            lines.append(f"- `{r['id']}` **{r['question']}** → intent `{r['got_intent']}`, entities {r['got_entities'].get('mda') or r['got_entities'].get('lga') or r['got_entities'].get('function') or '-'}; "
                         f"failed: {bad}{f' (expected {exp})' if exp else ''}")
    path = ROOT / "bench" / f"report_{mode}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:4]))
    print(f"report: {path}")


def _group(results, key):
    g = defaultdict(list)
    for r in results:
        g[r[key]].append(r)
    return g


if __name__ == "__main__":
    main()
