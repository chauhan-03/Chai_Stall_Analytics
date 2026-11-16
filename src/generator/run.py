"""Generate the synthetic dataset.

    python -m src.generator.run

Outputs
  data/raw/            what the stall owner would hand over (+ public context data)
    Paytm_UPI_Statement_16_Nov'25_-_15_Nov'26.xlsx
    menu.csv                    current menu card: item, price, cost
    menu_price_history.csv      price changes and launches the owner remembers
    campus_calendar.csv         academic calendar (public)
    weather_pilani.csv          daily weather (in production: weather API)
  data/answer_key/     ground truth, never shown to the pipeline
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from . import config as C
from .people import make_customers
from .simulate import Simulator, build_items, price_on, cost_on, ELASTICITY
from .statement import StatementWriter
from .weather import make_weather

ROOT = Path(__file__).resolve().parents[2]
RAW, KEY = ROOT / "data" / "raw", ROOT / "data" / "answer_key"


def main():
    RAW.mkdir(parents=True, exist_ok=True); KEY.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(C.SEED)
    items = build_items()
    by_id = {it["id"]: it for it in items}
    weather = make_weather(C.START, C.END, rng)
    customers = make_customers(rng, items)
    print(f"customers: {len(customers)}")
    sim = Simulator(customers, weather, rng)
    out = sim.run()
    o = out["orders"]
    print(f"orders: {len(o):,}  modes: {o['mode'].value_counts().to_dict()}")

    sw = StatementWriter(out, customers, rng)
    sw.build_sales(); sw.build_owner()
    stmt_path = RAW / "Paytm_UPI_Statement_16_Nov'25_-_15_Nov'26.xlsx"
    stmt, key = sw.write(stmt_path)
    print(f"statement rows: {len(stmt):,} -> {stmt_path.name}")

    # ---- owner-facing inputs
    end = C.END
    # owner's gut feel of daily units on a normal class day: right order of
    # magnitude, but noisy (lognormal, sigma 0.35) and rounded like people do
    dd = out["daily"]
    cls_days = dd[(dd.phase == "classes") & ~dd.closed]
    def gut(iid):
        true = cls_days[f"sold_{iid}"].mean()
        g = true * rng.lognormal(0, 0.35)
        return int(round(g / 5) * 5) if g >= 10 else max(1, int(round(g)))
    pd.DataFrame([{
        "item_id": it["id"], "item": it["name"], "category": it["category"],
        "price": price_on(it["id"], end, by_id), "cost": cost_on(it["id"], end, by_id),
        "made_in_batches": it["batch"], "owner_estimate_daily": gut(it["id"]),
    } for it in items]).to_csv(RAW / "menu.csv", index=False)
    hist = [{"item_id": i, "effective_date": d, "event": "price_change", "new_price": p,
             "old_price": by_id[i]["price0"]} for i, d, p in C.PRICE_CHANGES]
    hist += [{"item_id": i, "effective_date": d, "event": "launch",
              "new_price": by_id[i]["price0"], "old_price": None} for i, d in C.LAUNCHES.items()]
    pd.DataFrame(hist).to_csv(RAW / "menu_price_history.csv", index=False)
    pd.DataFrame([{"start": a, "end": b, "phase": p, "label": l}
                  for a, b, p, l in C.CALENDAR + C.FUTURE_CALENDAR]
                 ).to_csv(RAW / "campus_calendar.csv", index=False)
    pd.DataFrame([{"date": d, "reason": r} for d, r in C.CLOSED_DAYS.items()]
                 ).to_csv(RAW / "stall_closed_days.csv", index=False)
    weather.to_csv(RAW / "weather_pilani.csv", index=False)

    # ---- answer key
    o.to_csv(KEY / "orders.csv", index=False)
    out["order_items"].to_csv(KEY / "order_items.csv", index=False)
    out["daily"].to_csv(KEY / "daily_truth.csv", index=False)
    key.to_csv(KEY / "statement_row_labels.csv", index=False)
    customers.drop(columns=["fav"]).to_csv(KEY / "customers.csv", index=False)
    truth = {
        "elasticity": ELASTICITY,
        "combo_rules_injected": [
            "fried snack -> chai (58% normal, 35% when tmax>=36)",
            "poha / bread omelette -> chai (50%)", "paratha -> masala chai (45%)",
            "maggi -> cold drink (hot) or coffee/chai (late night)",
            "sandwich -> cold coffee (30% after launch)",
            "chai -> bun maska / kachori (morning), samosa / mirchi bada (evening) 28%",
            "masala chai + samosa -> Chai Samosa Combo (75% after 1 Feb 2026)"],
        "competitor_open": str(C.COMPETITOR_OPEN), "competitor_effect": C.COMPETITOR_EFFECT,
        "upi_outages": [[str(a), b, c] for a, b, c in C.UPI_OUTAGES],
        "cash_trend": C.CASH_TREND,
    }
    (KEY / "truth_parameters.json").write_text(json.dumps(truth, indent=2))

    d = out["daily"]
    tot = d.upi_sales.sum() + d.cash_sales.sum()
    print(f"revenue: total ₹{tot:,.0f}  UPI share {d.upi_sales.sum()/tot:.1%}")
    sem = d[d.phase == "classes"]
    print(f"classes-day orders/day ≈ {o[o.phase=='classes'].groupby('date').size().mean():.0f}, "
          f"avg bill ₹{o.amount.mean():.1f}, rev/day ₹{(sem.upi_sales+sem.cash_sales).mean():,.0f}")


if __name__ == "__main__":
    main()
