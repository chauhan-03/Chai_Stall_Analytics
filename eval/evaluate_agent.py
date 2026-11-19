"""Evaluate the agent on owner questions.

    python -m eval.evaluate_agent --offline        # keyword router baseline, no key needed
    python -m eval.evaluate_agent                  # Claude agent (needs ANTHROPIC_API_KEY); costs money

Scores
  tool accuracy   : at least one expected tool was called
  faithfulness    : every number in the reply appears in a tool output
  actionable      : reply ends with a concrete 'Suggestion:'
"""
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.pipeline.analytics import default_analytics  # noqa: E402


def main():
    offline = "--offline" in sys.argv
    A = default_analytics()
    if offline:
        from src.agent.offline import OfflineAgent
        agent = OfflineAgent(A)
    else:
        from src.agent.agent import StallAgent
        agent = StallAgent(A, log=ROOT / "eval" / "agent_log.jsonl")
    qs = json.loads((ROOT / "eval" / "agent_questions.json").read_text())
    rows = []
    for item in qs:
        if not offline:
            agent.history = []            # each question independent
        r = agent.ask(item["q"])
        used = [t["tool"] for t in r["tools"]]
        rows.append(dict(q=item["q"], expected=item["expect"], used=used,
                         tool_ok=any(u in item["expect"] for u in used),
                         faithful=not r.get("unsupported_numbers"),
                         actionable="suggestion:" in r["answer"].lower(),
                         answer=r["answer"]))
        print(f"[{'ok' if rows[-1]['tool_ok'] else 'XX'}] {item['q']} -> {used}")
    n = len(rows)
    summary = {k: sum(r[k] for r in rows) / n for k in ("tool_ok", "faithful", "actionable")}
    name = "offline" if offline else "claude"
    from src.profiles import EVAL_OUT
    EVAL_OUT.mkdir(parents=True, exist_ok=True)
    out = EVAL_OUT / f"agent_results_{name}.json"
    out.write_text(json.dumps(dict(summary=summary, rows=rows), indent=1, ensure_ascii=False))
    print(f"\n{name}: tool accuracy {summary['tool_ok']:.0%}, faithfulness {summary['faithful']:.0%}, "
          f"actionable {summary['actionable']:.0%}  ({n} questions) -> {out.name}")


if __name__ == "__main__":
    main()
