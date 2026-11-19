"""Offline agent: keyword router + templates. No API key needed.

Used for demos without internet/keys and as a baseline in the agent evaluation.
Same tools, same numbers; just less flexible language.
"""
import re
from datetime import timedelta

ITEM_WORDS = {"samos": "SAMOSA", "kachori": "KACHORI", "maggi": "MAGGI", "chai": "MASALA_CHAI",
              "poha": "POHA", "lassi": "LASSI", "mirchi": "MIRCHI_BADA", "pakod": "BREAD_PAKODA",
              "coffee": "HOT_COFFEE", "sandwich": "VEG_SANDWICH", "paratha": "PARATHA",
              "omelette": "BREAD_OMELETTE", "doodh": "MASALA_CHAI", "milk": "MASALA_CHAI"}


def _item(q):
    for k, v in ITEM_WORDS.items():
        if k in q:
            return v
    return None


def route(q):
    q = q.lower()
    price = re.search(r"(?:₹|rs\.?\s*|price\s*)(\d+)", q) or re.search(r"(\d+)\s*(?:rupaye|rupees|ka|kar)", q)
    if any(w in q for w in ("price", "daam", "rate", "mehenga", "sasta")) and price and _item(q):
        return "simulate_price", {"item": _item(q), "new_price": float(price.group(1))}
    if any(w in q for w in ("combo", "saath", "together", "offer")):
        return "combos", {}
    if any(w in q for w in ("kitne", "how many", "prep", "banau", "banaun", "mangwa", "stock")):
        return "prep_plan", {}
    if any(w in q for w in ("gir", "drop", "kam kyu", "kyu kam", "why", "kyun", "kyu")):
        return "detect_shifts", {}
    if any(w in q for w in ("forecast", "kal", "tomorrow", "agle", "next week", "hafte")):
        return "forecast_revenue", {"days": 7}
    if any(w in q for w in ("menu", "hatau", "remove", "push", "star")):
        return "menu_matrix", {}
    if any(w in q for w in ("customer", "regular", "grahak", "naye")):
        return "customer_insights", {}
    if any(w in q for w in ("rush", "busy", "bheed", "time", "ghante", "hour")):
        return "hourly_profile", {"days": 28}
    if any(w in q for w in ("upi", "outage", "band", "down")):
        return "detect_outages", {}
    if any(w in q for w in ("bika", "bikta", "sell", "sales", "popular")):
        return "sales_mix", {"days": 30, "top": 8}
    return "daily_brief", {}


def render(tool, r):
    if tool == "prep_plan":
        lines = [f"Kal ({r['date']}) ke liye prep:"]
        for it in r["items"]:
            lines.append(f"- {it['item']}: {it['recommended_prep']} banao "
                         f"(demand {it['demand_p10']}-{it['demand_p90']}, most likely {it['demand_most_likely']})")
        lines.append("Suggestion: in numbers se shuru karo; jis din jaldi khatam ho, time note karo.")
        return "\n".join(lines)
    if tool == "simulate_price":
        a, n = r["after_most_likely"], r["now"]
        return (f"{r['item']} ₹{r['current_price']:.0f} -> ₹{r['new_price']:.0f}: roz ~{n['units_per_day']} se "
                f"~{a['units_per_day']} units, profit ₹{n['profit_per_day']} -> ₹{a['profit_per_day']}/day "
                f"(range ₹{r['after_if_customers_more_sensitive']['profit_per_day']}-"
                f"₹{r['after_if_customers_less_sensitive']['profit_per_day']}). Elasticity source: {r['source']}.\n"
                f"Suggestion: {'try it for 2 weeks and compare' if r['profit_change_per_day'] > 0 else 'keep the current price'}.")
    if tool == "combos":
        rules = r["rules"][:4]
        s = "Log yeh saath lete hain:\n" + "\n".join(
            f"- {x['if_buys']} + {x['also_buys']} (lift {x['lift']}, {x['confidence']}% of the time)" for x in rules)
        return s + f"\nSuggestion: {rules[0]['if_buys']} + {rules[0]['also_buys']} ka combo try karo." if rules else s
    if tool == "forecast_revenue":
        d = r["days"][0]
        return (f"{d['date']} ({d['period']}): sales ₹{d['revenue_p10']}-₹{d['revenue_p90']}, most likely "
                f"₹{d['revenue_p50']} (cash share assumed). Agle 7 din: ~₹{r['total_p50']}.\n"
                "Suggestion: busy din ke liye extra doodh aur samose ready rakho.")
    if tool == "detect_shifts":
        if not r["shifts"]:
            return "Koi bada lasting change nahi mila.\nSuggestion: compare_periods se do mahine compare karo."
        s = r["shifts"][0]
        return (f"{s['slot']} ({s['hours']}) sales {s['change_pct']}% badle {s['since']} se "
                f"(₹{s['before_per_day']} -> ₹{s['after_per_day']} per day UPI).\n"
                "Suggestion: us waqt kya naya hua (competitor, timing) check karo; shaam ke liye offer socho.")
    if tool == "menu_matrix":
        by = {}
        for it in r["items"]:
            by.setdefault(it["class_"], []).append(it["item"])
        return ("\n".join(f"- {k}: {', '.join(v[:5])}" for k, v in by.items())
                + "\nSuggestion: Plowhorse items pe ₹5 badhao ya combo me daalo.")
    if tool == "customer_insights":
        return (f"{r['unique_upi_customers']} UPI customers, {r['regulars']} regulars "
                f"({r['regulars_share_of_upi_sales_pct']}% of UPI sales). {len(r['regulars_not_seen_21d'])} regulars "
                f"3 hafte se nahi aaye. Pichle 30 din me {r['new_customers_last_30d']} naye customers.\n"
                "Suggestion: jo regulars nahi aa rahe unhe agli baar free cutting chai do.")
    if tool == "hourly_profile":
        return (f"Rush: {', '.join(r['busiest_hours'])}. Slow: {', '.join(r['slowest_hours'])}.\n"
                "Suggestion: slow hours me chhota offer (chai + biscuit) chalao.")
    if tool == "detect_outages":
        o = r["suspected_outages"]
        return (f"{len(o)} baar UPI busy time pe ruka: " + ", ".join(x["date"] for x in o[:5])
                + "\nSuggestion: cash ke liye chhutta paisa ready rakho.")
    if tool == "sales_mix":
        return ("Sabse zyada bikne wale (per day): " + ", ".join(f"{x['item']} {x['per_day']}" for x in r["items"][:6])
                + "\nSuggestion: top items kabhi khatam na hon.")
    if tool == "daily_brief":
        d = r["revenue_forecast"]
        prep = ", ".join(f"{p['item']} {p['recommended_prep']}" for p in r["prep_list"])
        return (f"{r['date']}: expected ₹{d['revenue_p10']}-₹{d['revenue_p90']} (most likely ₹{d['revenue_p50']}). "
                f"Rush: {', '.join(r['rush_hours'])}. Prep: {prep}. Alerts: {'; '.join(r['alerts']) or 'none'}.\n"
                "Suggestion: prep list follow karo.")
    return str(r)[:800]


class OfflineAgent:
    def __init__(self, analytics):
        self.A = analytics

    def ask(self, question):
        tool, args = route(question)
        r = getattr(self.A, tool)(**args)
        return dict(answer=render(tool, r), tools=[dict(tool=tool, input=args, ok=True)],
                    unsupported_numbers=[], ok=True, model="offline-router")
