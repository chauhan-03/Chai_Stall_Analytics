"""Stall-owner agent: Claude plans and explains, the Python pipeline supplies every number.

Design rules
  1. Every number comes from a tool. A faithfulness check verifies that each
     number in the reply appears in some tool output (or the question).
  2. Every recommendation shows its range and ends with one concrete action.
  3. It only suggests; it never acts (no ordering, no payments).
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import timedelta
from pathlib import Path

from .tools import TOOLS, run_tool

MODEL = os.environ.get("STALL_AGENT_MODEL", "claude-opus-5-5")

SYSTEM = """You are "Chai Saathi", a business assistant for a small campus chai and snacks stall in India.
You talk to the stall owner. Reply in the language they use: Hinglish (Roman Hindi mixed with English) if
they write that way, otherwise English. Keep it short and practical: 3-6 lines, no tables unless asked.

Rules you must follow:
- Every number you state must come from a tool result in this conversation. Never estimate, add up or
  invent figures yourself; if you need a number, call a tool. Copy numbers as the tool gave them (you may
  round to a whole number).
- Item-level numbers are estimates reconstructed from UPI payment amounts; cash sales are added back with an
  assumed cash share. When a range is available (the tools call it p10/p90 or low/high), give it in plain words, e.g. "70-90, most likely 80".
- If the answer depends on the cash-share assumption, say so in a few words.
- End with exactly one recommended action, starting with "Suggestion:".
- Use simple, everyday words a stall owner uses. Never use technical terms such as elasticity, P10/P50/P90,
  quantile, lift, confidence, support, newsvendor, WAPE, t-stat, contribution margin, Star/Plowhorse/Puzzle/Dog.
  Say instead: "range" or "between X and Y", "most likely", "bought together", "profit per piece",
  "how much people cut back when the price goes up".
- When the owner asks about one item, don't pass "top" (it can cut that item out). If a result doesn't include
  the item, call the tool again without limits before saying anything is missing. For "should I keep / remove X"
  use menu_matrix.
- You only advise. You cannot order stock, change prices or pay anyone; the owner decides.
- If a tool says an estimate is unreliable, tell the owner plainly.
Data covers {period}. "Today" is {today}; "tomorrow" means {tomorrow}."""

NUM = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?")


def numbers_in(text):
    out = []
    for m in NUM.findall(text):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def faithfulness(reply: str, sources: list[str]):
    """Return numbers in the reply that do not appear (within rounding) in any source."""
    pool = []
    for s in sources:
        pool.extend(numbers_in(s))
    bad = []
    for x in numbers_in(reply):
        if abs(x) <= 31 and float(x).is_integer():
            continue          # days, hours, counts like '3 items' - too ambiguous to check
        ok = any(abs(x - y) <= max(1.0, 0.012 * abs(y)) for y in pool)
        if not ok:
            # allow rounding to tens/hundreds (e.g. 12,296 -> 12,300)
            ok = any(abs(x - y) <= 0.05 * abs(y) and x % 10 == 0 for y in pool if y)
        if not ok:
            bad.append(x)
    return bad


class StallAgent:
    def __init__(self, analytics, model=MODEL, memory_path=None, effort="medium", log=None):
        self.A = analytics
        self.model, self.effort = model, effort
        self.memory_path = Path(memory_path) if memory_path else None
        self.memory = json.loads(self.memory_path.read_text()) if self.memory_path and self.memory_path.exists() else []
        self.log = log
        self.history = []
        import anthropic
        self.anthropic = anthropic
        self.client = anthropic.Anthropic()

    def _system(self):
        today = self.A.last
        s = SYSTEM.format(period=f"{self.A.first} to {self.A.last}", today=today,
                          tomorrow=today + timedelta(days=1))
        if self.memory:
            recent = "; ".join(m["q"] for m in self.memory[-5:])
            s += f"\nThe owner recently asked about: {recent}"
        return s

    def _call(self, messages):
        kw = dict(model=self.model, max_tokens=16000, system=self._system(), tools=TOOLS, messages=messages,
                  output_config={"effort": self.effort})
        if self.model.startswith(("claude-opus-5", "claude-fable", "claude-sonnet-5-5")):
            # server-side fallback if a safety classifier declines (enabled by default)
            return self.client.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                                    fallbacks="default", **kw)
        return self.client.messages.create(**kw)

    def ask(self, question: str, max_steps=8):
        t0 = time.time()
        messages = self.history + [{"role": "user", "content": question}]
        trace, sources = [], [question]
        response = None
        for _ in range(max_steps):
            try:
                response = self._call(messages)
            except self.anthropic.RateLimitError:
                time.sleep(20); continue
            except self.anthropic.APIConnectionError as e:
                return dict(answer=f"Network problem talking to the model: {e}", tools=trace, ok=False)
            if response.stop_reason == "refusal":
                return dict(answer="Sorry, I can't help with that request.", tools=trace, ok=False)
            if response.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": response.content}); continue
            if response.stop_reason != "tool_use":
                break
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for b in response.content:
                if b.type != "tool_use":
                    continue
                try:
                    out = run_tool(self.A, b.name, b.input)
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
                    sources.append(out)
                    trace.append(dict(tool=b.name, input=b.input, ok=True))
                except Exception as e:      # tool errors go back to the model, not the user
                    results.append({"type": "tool_result", "tool_use_id": b.id,
                                    "content": f"Error: {e}", "is_error": True})
                    trace.append(dict(tool=b.name, input=b.input, ok=False, error=str(e)))
            messages.append({"role": "user", "content": results})
        answer = "".join(b.text for b in response.content if b.type == "text").strip() if response else ""
        unsupported = faithfulness(answer, sources)
        if unsupported:
            # one repair pass: ask the model to fix or drop unsupported numbers
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content":
                             f"[automatic check] These numbers in your reply are not in any tool result: "
                             f"{unsupported}. Rewrite the reply using only numbers from the tool results "
                             f"(call a tool if needed). Do not mention this check."})
            response = self._call(messages)
            answer = "".join(b.text for b in response.content if b.type == "text").strip()
            unsupported = faithfulness(answer, sources)
        self.history = (self.history + [{"role": "user", "content": question},
                                        {"role": "assistant", "content": answer}])[-8:]
        if self.memory_path:
            self.memory.append({"q": question[:120], "tools": [t["tool"] for t in trace]})
            self.memory_path.write_text(json.dumps(self.memory[-50:], ensure_ascii=False, indent=1))
        res = dict(answer=answer, tools=trace, unsupported_numbers=unsupported, ok=True,
                   seconds=round(time.time() - t0, 1), model=getattr(response, "model", self.model))
        if self.log:
            with open(self.log, "a") as f:
                f.write(json.dumps({"q": question, **res}, default=str, ensure_ascii=False) + "\n")
        return res
