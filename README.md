# Chai Stall Analytics

Turn a small food stall's **Paytm UPI statement + menu card** into sales insights, forecasts, a daily prep
plan and pricing advice, with a Hinglish chat assistant on top.

The statement has no item names, only amounts ("₹40 received from Rahul"). The pipeline infers what was
sold, adds back cash, forecasts demand and recommends actions. A realistic synthetic stall (a campus chai
stall at BITS Pilani, Nov 2025 – Nov 2026) with a hidden **answer key** scores every stage.

```
Paytm statement (.xlsx) + menu.csv
        │
        ▼
 1. ingest        classify rows: sale / refund / duplicate / supplier / self-transfer / personal …
 2. decompose     EM basket model: which items add up to each payment (time, weather, remarks)
 3. combos        association rules from customer-typed remarks
 4. forecast      gradient-boosted model + conformal P10–P90 (calendar, weather, recent level)
 5. prep plan     newsvendor quantities for batch items (samosa, kachori, poha …)
 6. menu matrix   Stars / Plowhorses / Puzzles / Dogs
 7. what-if       price elasticity (difference-in-differences) → price simulator
 8. diagnostics   lasting shifts (competitor), UPI outages, period comparison
 9. customers     regulars, churn, new customers
        │
        ▼
 Agent (Claude + tools)  "Kal kitne samose banau?" → prep_plan → answer + range + one suggestion
```

## Quick start

```bash
cd ~/Desktop/Chai_Stall_Analytics
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

.venv/bin/python -m src.generator.run          # 1. build the synthetic stall (~40 s)
.venv/bin/python -m eval.evaluate_pipeline     # 2. score the pipeline -> eval/report.md (~5 min first run)
.venv/bin/streamlit run app.py                 # 3. open the app
```

The first load decomposes ~50k payments (~80 s); later runs use the cache in `data/processed/`.

**Chat:** without a key the app uses an offline keyword router. For the Claude agent:
`export ANTHROPIC_API_KEY=...` before `streamlit run`. Model: `claude-opus-5-5`; override with `STALL_AGENT_MODEL`.

**Real data:** in the app choose *Upload my files*. Upload a Paytm statement and a `menu.csv` with columns
`item_id,item,category,price,cost,made_in_batches`. Optional extras: `owner_estimate_daily` (rough units per
day) and a price-history file. The same pipeline runs unchanged.

## Results against the answer key

Train up to 4 Oct 2026; test 5 Oct – 15 Nov 2026 (mid-sems, Oasis, Diwali, competitor effect).
Full details are in [eval/report.md](eval/report.md).

| Stage | Result |
|---|---|
| Statement row classification | **100%** accuracy |
| UPI sales recovered | 0.07% error |
| Total revenue incl. cash (25% assumed vs 22.9% true) | +2.9% for the year; 5.8% daily WAPE |
| Item mix (which items sold) | 28.7% WAPE on totals; popularity rank ρ = 0.76 |
| Exact basket per payment | 24% overall, **79%** when the model is ≥60% confident |
| Combos | **90%** of reported rules are real; finds 8 of the 10 strongest true pairs |
| Revenue forecast (6 weeks out) | **14.1% WAPE** vs 20.1% for "same day last week"; P10–P90 covers 95% (conservative) |
| Prep plan vs owner's habit | +₹1,035 profit on batch items in 6 weeks; waste 2,088 → 1,266 units, but more stockouts |
| Competitor detection | **missed**: flags an evening rise from 9 Sep instead of the night drop from 21 Sep |
| UPI outages | 3 of 3 found, 3 false alarms |
| Agent, offline router baseline | 58% right tool, 100% faithful numbers, 100% end with an action |

Results depend on the random seed: an earlier draw of the same simulation gave item-mix error 24.8%,
forecast 13.0%, prep gain +₹3,790 and caught the competitor. Report results over several seeds before
drawing firm conclusions.

### Honest limits (what the answer key shows)

- **Same-price items are hard to separate.** A ₹20 payment could be a cold drink, water, shikanji or
  mirchi bada. Chai is under-counted (masala chai −40%, cutting chai −35%) and some items over-counted
  (aloo paratha +172%). The owner's rough daily estimates (a menu column) used as a Bayesian prior cut the
  error by about 4–5 points versus remarks alone.
- **Prep plan under-prepares fried snacks** because of that bias and because sell-out days hide true
  demand. Fix: a one-tap "sold out at hh:mm" log.
- **Elasticity is not recoverable here.** Maggi estimated −0.13 (true 1.4). When the new price equals a
  very common amount (₹50, ₹30), the tool flags the estimate as unreliable and falls back to a default
  instead of using it.
- **Cash is invisible.** Revenue is a range driven by the cash-share assumption.

## Project layout

```
src/generator/   synthetic stall: config (research-backed), weather, people, simulate, statement
src/pipeline/    ingest, menu, decompose (EM), forecast, analytics (all tools)
src/agent/       tools (JSON schemas), agent (Claude tool loop + faithfulness check), offline router
eval/            evaluate_pipeline.py, evaluate_agent.py, agent_questions.json, report.md
data/raw/        what the owner provides + public context (calendar, weather)
data/answer_key/ ground truth (never read by the pipeline)
docs/            RESEARCH_AND_ASSUMPTIONS.md (sources)
app.py           Streamlit app
```

## Agent design

- **Every number comes from a tool.** After each reply a checker extracts all numbers and verifies each
  appears in a tool output, allowing for rounding. On failure the model gets one automatic repair pass,
  and any numbers still unsupported are logged.
- **Uncertainty is shown** ("70–90, most likely 80") and cash-share dependence is flagged.
- **Advice only.** No ordering, payments or price changes.
- Hand-written tool-use loop (no framework), so every call is logged and easy to explain.
  Server-side refusal fallback is enabled.
- Evaluate: `python -m eval.evaluate_agent --offline` (free) or `python -m eval.evaluate_agent`
  (Claude; 36 questions, costs API credits).

## Re-running with different assumptions

Edit `src/generator/config.py` (calendar, prices, cash trend, competitor date, outages…) and rerun
steps 1–2. Everything downstream, including the answer key, updates.
