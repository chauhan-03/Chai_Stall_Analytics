"""Stall-owner agent on Groq (fast hosted open models, OpenAI-compatible API).

Same design as the Claude agent in agent.py: the model plans and explains, the
Python pipeline supplies every number through the same tools, a faithfulness
check verifies the numbers, and each reply ends with one suggestion.

    export GROQ_API_KEY=...            # from console.groq.com
    export GROQ_MODEL=...              # optional; otherwise the best available model is picked

Uses only the standard library (urllib), so no extra package is needed.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import timedelta
from pathlib import Path

from ..profiles import load_env
from .agent import SYSTEM, faithfulness
from .tools import TOOLS, run_tool

BASE = "https://api.groq.com/openai/v1"
# preferred tool-calling models, best first; the first one the account can use is chosen
PREFERRED = ["openai/gpt-oss-120b", "moonshotai/kimi-k2-instruct-0905", "moonshotai/kimi-k2-instruct",
             "llama-3.3-70b-versatile", "qwen/qwen3-32b", "openai/gpt-oss-20b", "llama-3.1-8b-instant"]
MAX_TOOL_CHARS = 5000          # keep tool results small: Groq free tier has low tokens-per-minute limits


class GroqError(RuntimeError):
    pass


class GroqAgent:
    def __init__(self, analytics, model=None, memory_path=None, log=None, api_key=None):
        load_env()                     # picks up GROQ_API_KEY from the project's .env file
        self.A = analytics
        self.key = api_key or os.environ.get("GROQ_API_KEY")
        if not self.key:
            raise GroqError("GROQ_API_KEY is not set")
        self.model = model or os.environ.get("GROQ_MODEL") or self._pick_model()
        self.memory_path = Path(memory_path) if memory_path else None
        self.memory = json.loads(self.memory_path.read_text()) if self.memory_path and self.memory_path.exists() else []
        self.log = log
        self.history = []
        self._fast = os.environ.get("GROQ_REASONING", "low") == "low" and self.model.startswith(("openai/gpt-oss", "qwen/"))
        self.tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                         "parameters": t["input_schema"]}} for t in TOOLS]

    # ------------------------------------------------------------------ http
    def _request(self, path, payload=None, retries=4):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(BASE + path, data=data, method="POST" if data else "GET", headers={
            "Authorization": f"Bearer {self.key}", "Content-Type": "application/json",
            "User-Agent": "stall-analytics/1.0"})
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                body = e.read().decode(errors="replace")[:300]
                if e.code in (429, 500, 502, 503) and attempt < retries - 1:
                    wait = float(e.headers.get("retry-after") or 2 * (attempt + 1))
                    time.sleep(min(wait, 30)); continue
                if e.code == 401:
                    raise GroqError("Groq rejected the API key (401). Check GROQ_API_KEY.") from None
                raise GroqError(f"Groq API error {e.code}: {body}") from None
            except urllib.error.URLError as e:
                if attempt < retries - 1:
                    time.sleep(2); continue
                raise GroqError(f"Cannot reach Groq: {e.reason}") from None

    def _pick_model(self):
        ids = [m["id"] for m in self._request("/models").get("data", []) if m.get("active", True)]
        for m in PREFERRED:
            if m in ids:
                return m
        chat = [i for i in ids if not any(x in i for x in ("whisper", "guard", "tts", "playai", "prompt"))]
        if not chat:
            raise GroqError("No chat model available on this Groq account")
        return chat[0]

    def _system(self):
        today = self.A.last
        s = SYSTEM.format(period=f"{self.A.first} to {self.A.last}", today=today, tomorrow=today + timedelta(days=1))
        if self.memory:
            s += "\nThe owner recently asked about: " + "; ".join(m["q"] for m in self.memory[-5:])
        return s

    def _call(self, messages, tools=True):
        payload = dict(model=self.model, messages=[{"role": "system", "content": self._system()}] + messages,
                       temperature=0.2, max_tokens=1200)
        if tools:
            payload.update(tools=self.tools, tool_choice="auto")
        if self._fast:
            payload["reasoning_effort"] = "low"     # reasoning models answer much faster at low effort
        try:
            return self._request("/chat/completions", payload)["choices"][0]["message"]
        except GroqError as e:
            if self._fast and "reasoning" in str(e).lower():
                self._fast = False                    # model doesn't take the setting: retry without it
                payload.pop("reasoning_effort", None)
                return self._request("/chat/completions", payload)["choices"][0]["message"]
            raise

    # ------------------------------------------------------------------ agent loop
    def ask(self, question: str, max_steps=6):
        t0 = time.time()
        messages = self.history + [{"role": "user", "content": question}]
        trace, sources = [], [question]
        try:
            msg = None
            for step in range(max_steps):
                msg = self._call(messages, tools=step < max_steps - 1)
                calls = msg.get("tool_calls") or []
                if not calls:
                    break
                messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
                for c in calls:
                    name = c["function"]["name"]
                    try:
                        args = json.loads(c["function"].get("arguments") or "{}")
                        out = run_tool(self.A, name, args)
                        sources.append(out)
                        trace.append(dict(tool=name, input=args, ok=True))
                        content = out if len(out) <= MAX_TOOL_CHARS else out[:MAX_TOOL_CHARS] + " …(truncated)"
                    except Exception as e:      # tool errors go back to the model, not the user
                        content = f"Error: {e}"
                        trace.append(dict(tool=name, input=c["function"].get("arguments"), ok=False, error=str(e)))
                    messages.append({"role": "tool", "tool_call_id": c["id"], "content": content})
            answer = (msg.get("content") or "").strip() if msg else ""
            unsupported = faithfulness(answer, sources)
            if unsupported:
                messages.append({"role": "assistant", "content": answer})
                messages.append({"role": "user", "content":
                                 f"[automatic check] These numbers in your reply are not in any tool result: "
                                 f"{unsupported}. Rewrite the reply using only numbers from the tool results. "
                                 f"Do not mention this check."})
                answer = (self._call(messages, tools=False).get("content") or "").strip()
                unsupported = faithfulness(answer, sources)
        except GroqError as e:
            return dict(answer=f"AI assistant abhi available nahi hai: {e}", tools=trace,
                        unsupported_numbers=[], ok=False, model=self.model)
        self.history = (self.history + [{"role": "user", "content": question},
                                        {"role": "assistant", "content": answer}])[-8:]
        if self.memory_path:
            self.memory.append({"q": question[:120], "tools": [t["tool"] for t in trace]})
            self.memory_path.write_text(json.dumps(self.memory[-50:], ensure_ascii=False, indent=1))
        res = dict(answer=answer, tools=trace, unsupported_numbers=unsupported, ok=True,
                   seconds=round(time.time() - t0, 1), model=self.model)
        if self.log:
            with open(self.log, "a") as f:
                f.write(json.dumps({"q": question, **res}, default=str, ensure_ascii=False) + "\n")
        return res
