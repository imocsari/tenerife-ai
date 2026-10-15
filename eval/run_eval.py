# eval/run_eval.py
# Measures how good Tenerife AI is, on a fixed set of test questions.
#
# Run from the project folder:
#   python -m eval.run_eval                  # retrieval only (fast, no LLM)
#   python -m eval.run_eval --answers        # also generate answers and check them
#   python -m eval.run_eval --answers --judge   # also let an LLM judge faithfulness
#
# Each run is saved in eval/results/, and compared with the previous run.

import argparse
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from app import llm, rag
from app.prompts import SYSTEM_PROMPT, build_message

EVAL_DIR = Path(__file__).resolve().parent
QUESTIONS_FILE = EVAL_DIR / "questions.jsonl"
RESULTS_DIR = EVAL_DIR / "results"

REFUSAL_PHRASES = [
    "don't know", "do not know", "don't have", "do not have", "no information",
    "not in the sources", "couldn't find", "could not find", "not able to find",
    "can't help", "cannot help", "only help with tenerife", "no sé", "no tengo",
]

JUDGE_PROMPT = (
    "You are a strict grader. You get SOURCES and an ANSWER. "
    "Reply with exactly one word: PASS if every factual claim in the ANSWER is "
    "supported by the SOURCES (or the ANSWER says it doesn't know), "
    "otherwise FAIL."
)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_questions():
    with open(QUESTIONS_FILE, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------------------------------------------------------------------------
# Scoring one question
# ---------------------------------------------------------------------------
def first_relevant_rank(sources, expected):
    """1-based position of the first retrieved source whose title matches an expected name."""
    for rank, s in enumerate(sources, start=1):
        title = s["title"].lower()
        if any(e.lower() in title for e in expected):
            return rank
    return None


def is_refusal(answer):
    a = answer.lower()
    return any(p in a for p in REFUSAL_PHRASES)


def score_question(q, use_answers, use_judge):
    result = {"id": q["id"], "tags": q.get("tags", []), "question": q["question"]}

    start = time.perf_counter()
    sources = rag.retrieve(q["question"])
    result["retrieved"] = [s["title"] for s in sources]

    # --- Retrieval metrics (only for questions that have an answer) ---
    if q.get("expected_sources"):
        rank = first_relevant_rank(sources, q["expected_sources"])
        result["hit"] = rank is not None                       # right source in top-k?
        result["reciprocal_rank"] = 1 / rank if rank else 0.0  # 1.0 = ranked first

    # --- Answer checks ---
    if use_answers:
        message = build_message(q["question"], sources)
        answer = llm.generate(SYSTEM_PROMPT, message)
        result["answer"] = answer

        if q.get("should_refuse"):
            result["refused_correctly"] = is_refusal(answer)
        else:
            result["wrongly_refused"] = is_refusal(answer)
            if q.get("must_contain"):
                a = answer.lower()
                result["contains_expected"] = any(w.lower() in a for w in q["must_contain"])

        if use_judge:
            verdict = llm.generate(JUDGE_PROMPT, f"SOURCES:\n{message}\n\nANSWER:\n{answer}")
            result["faithful"] = verdict.strip().upper().startswith("PASS")

    result["seconds"] = round(time.perf_counter() - start, 2)
    return result


# ---------------------------------------------------------------------------
# Summaries
# ---------------------------------------------------------------------------
METRICS = {
    # name: (field in result, how to aggregate)
    "hit_rate":          ("hit", "mean"),
    "mrr":               ("reciprocal_rank", "mean"),
    "refusal_accuracy":  ("refused_correctly", "mean"),
    "wrong_refusals":    ("wrongly_refused", "mean"),
    "contains_expected": ("contains_expected", "mean"),
    "faithfulness":      ("faithful", "mean"),
    "avg_seconds":       ("seconds", "mean"),
}


def summarise(results):
    """Overall metrics plus the same metrics per tag."""
    groups = defaultdict(list)
    for r in results:
        groups["ALL"].append(r)
        for t in r["tags"]:
            groups[t].append(r)

    summary = {}
    for group, rows in groups.items():
        summary[group] = {"questions": len(rows)}
        for name, (field, _) in METRICS.items():
            values = [float(r[field]) for r in rows if field in r]
            if values:
                summary[group][name] = round(sum(values) / len(values), 3)
    return summary


def print_report(summary, previous=None):
    metric_names = [m for m in METRICS if any(m in s for s in summary.values())]
    print()
    for name in metric_names:
        lower_is_better = name in ("wrong_refusals", "avg_seconds")
        print(f"{name}{'  (lower is better)' if lower_is_better else ''}")
        print(f"  {'group':<12} {'n':>3}   {'before':>7}  {'now':>7}  {'change':>7}")
        for group in sorted(summary, key=lambda g: (g != "ALL", g)):
            if name not in summary[group]:
                continue
            now = summary[group][name]
            before = (previous or {}).get(group, {}).get(name)
            before_s = f"{before:.3f}" if before is not None else "-"
            change_s = f"{now - before:+.3f}" if before is not None else ""
            print(f"  {group:<12} {summary[group]['questions']:>3}   {before_s:>7}  {now:>7.3f}  {change_s:>7}")
        print()


def print_failures(results):
    failures = [r for r in results if r.get("hit") is False
                or r.get("refused_correctly") is False
                or r.get("wrongly_refused") is True
                or r.get("contains_expected") is False
                or r.get("faithful") is False]
    if not failures:
        print("No failures. Time to add harder questions!")
        return
    print(f"FAILURES ({len(failures)}) – these teach you the most:")
    for r in failures:
        print(f"\n  [{r['id']}] {r['question']}")
        print(f"    retrieved: {r['retrieved'][:3]}")
        if "answer" in r:
            print(f"    answer:    {r['answer'][:200].replace(chr(10), ' ')}")


# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Evaluate Tenerife AI")
    parser.add_argument("--answers", action="store_true", help="also generate and check answers (uses the LLM)")
    parser.add_argument("--judge", action="store_true", help="also ask an LLM to grade faithfulness")
    parser.add_argument("--note", default="", help="describe what you changed, e.g. 'bge-m3 embeddings'")
    args = parser.parse_args()

    questions = load_questions()
    print(f"Evaluating {len(questions)} questions...")
    results = []
    for i, q in enumerate(questions, start=1):
        results.append(score_question(q, args.answers, args.answers and args.judge))
        print(f"  {i}/{len(questions)} {q['id']}", end="\r")

    summary = summarise(results)

    RESULTS_DIR.mkdir(exist_ok=True)
    latest = RESULTS_DIR / "latest.json"
    previous = json.loads(latest.read_text())["summary"] if latest.exists() else None

    print_report(summary, previous)
    print_failures(results)

    run = {"timestamp": datetime.now().isoformat(timespec="seconds"),
           "note": args.note, "summary": summary, "results": results}
    stamped = RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    for path in (stamped, latest):
        path.write_text(json.dumps(run, ensure_ascii=False, indent=2))
    print(f"\nSaved to {stamped.relative_to(EVAL_DIR.parent)}")


if __name__ == "__main__":
    main()
