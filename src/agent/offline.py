"""Offline agent: rule-based question understanding + data-driven answers. No API key needed.

Used for demos without internet/keys and as a baseline in the agent evaluation.
Same tools and numbers as the Claude agent; answers are built from tool results only,
and each one ends with a suggestion chosen from those results.

Understands: menu items (names, owner keywords, Hinglish words), prices ("₹60", "20 rupaye"),
hours ("8 am", "7 baje"), months, "last month", "tomorrow"/"next week", fests, exams and seasons.
"""
import re
from datetime import date, timedelta

import numpy as np
import pandas as pd

# Hinglish / generic words -> chai-stall item ids (used only when that id is on the menu)
ITEM_WORDS = {"samos": "SAMOSA", "kachori": "KACHORI", "maggi": "MAGGI", "chai": "MASALA_CHAI",
              "tea": "MASALA_CHAI", "poha": "POHA", "lassi": "LASSI", "mirchi": "MIRCHI_BADA",
              "pakod": "BREAD_PAKODA", "coffee": "HOT_COFFEE", "sandwich": "VEG_SANDWICH",
              "paratha": "PARATHA", "omelette": "BREAD_OMELETTE", "cutting": "CUT_CHAI"}
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                      "august", "september", "october", "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items()) if k != "may"})
MONTHS.update({"janvari": 1, "farvari": 2, "aprail": 4, "julai": 7, "agast": 8, "sitambar": 9,
               "aktubar": 10, "navambar": 11, "disambar": 12})


def has(q, *words):
    return any(re.search(r"(?<!\w)" + w, q) for w in words)


def rs(x):
    return f"₹{x:,.0f}" if x is not None else "?"


class OfflineAgent:
    def __init__(self, analytics):
        self.A = analytics
        A = analytics
        words = []
        for iid in A.ids:
            name = re.sub(r"\(.*?\)", "", A.menu.names[iid]).lower().strip()
            words.append((name, iid, True))
        for iid, ws in (getattr(A.menu, "aliases", None) or {}).items():
            words += [(w.lower(), iid, True) for w in ws]
        for stem, iid in ITEM_WORDS.items():
            target = iid if iid in A.ids else self._try_resolve(stem)
            if target:
                words.append((stem, target, False))
        self.words = sorted(set(words), key=lambda x: -len(x[0]))

    # ------------------------------------------------------------------ understanding
    def _try_resolve(self, word):
        try:
            return self.A._resolve_item(word)
        except ValueError:
            return None

    def items_in(self, q):
        found, t = [], q
        for w, iid, whole in self.words:
            pat = r"(?<!\w)" + re.escape(w) + (r"(?:s|es|e)?(?!\w)" if whole else "")
            m = re.search(pat, t)
            if m:
                found.append((m.start(), iid))
                t = t[:m.start()] + " " * (m.end() - m.start()) + t[m.end():]
        out = []
        for _, iid in sorted(found):
            if iid not in out:
                out.append(iid)
        return out

    @staticmethod
    def numbers(q):
        return [float(x) for x in re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)", q)]

    def hour_in(self, q):
        m = re.search(r"(\d{1,2})\s*(am|pm|baje|bje|o'?clock)?", q)
        if not m or not m.group(2):
            return None
        h = int(m.group(1))
        if m.group(2) == "pm" or (m.group(2) in ("baje", "bje") and has(q, "shaam", "raat", "evening", "night")):
            h = h + 12 if h < 12 else h
        return h % 24

    def months_in(self, q):
        out = []
        for w, m in MONTHS.items():
            for hit in re.finditer(r"(?<!\w)" + w + r"(?!\w)", q):
                out.append((hit.start(), m))
        seen = []
        for _, m in sorted(out):
            if m not in seen:
                seen.append(m)
        return seen

    def month_range(self, m, future=False):
        A = self.A
        if future:
            y = A.last.year if m > A.last.month else A.last.year + 1
            s = date(y, m, 1)
            e = (pd.Timestamp(s) + pd.offsets.MonthEnd(0)).date()
            return s, e
        for y in (A.last.year, A.last.year - 1):
            s = date(y, m, 1)
            e = (pd.Timestamp(s) + pd.offsets.MonthEnd(0)).date()
            if s <= A.last and e >= A.first:
                return max(s, A.first), min(e, A.last)
        return None

    def _mix(self, mask):
        """Average estimated units per open day for each item on the days in mask."""
        A = self.A
        m = np.asarray(mask) & ~A.daily.closed.values
        if m.sum() == 0:
            return pd.Series(dtype=float), 0
        return A.units[m].mean(), int(m.sum())

    # ------------------------------------------------------------------ routing
    def ask(self, question):
        q = question.lower().replace("’", "'")
        items = self.items_in(q)
        tools = []
        try:
            answer = self._answer(q, items, tools)
        except Exception as e:                      # never crash the chat
            answer = (f"Is sawal ka jawab nikalte waqt dikkat aayi ({e}).\n"
                      "Suggestion: sawal thoda alag tareeke se poochho, jaise 'Kal kitne samose banau?'.")
        return dict(answer=answer, tools=[dict(tool=t, ok=True) for t in tools],
                    unsupported_numbers=[], ok=True, model="offline-router")

    def _answer(self, q, items, tools):
        A = self.A
        future = has(q, "will", "hoga", "hogi", "honge", "kamaunga", "forecast", "agle", "next", "upcoming",
                     "aane wal", "kal ", "kal$", "tomorrow", "look like")
        months = self.months_in(q)

        if has(q, "upi") and has(q, "band", "down", "outage", "ruk", "fail", "nahi chal"):
            tools.append("detect_outages"); return self.outages()
        if has(q, "customer", "grahak", "regular"):
            tools.append("customer_insights"); return self.customers(q)
        if items and has(q, "badhane ke baad", "after the price", "after raising", "elastic", "kam khareed",
                         "kam le rahe", "react"):
            tools.append("estimate_elasticity"); return self.elasticity(items[0])
        nums = [n for n in self.numbers(q) if n >= 5]
        if items and nums and has(q, "price", "daam", "dam ", "rate", "mehenga", "sasta", "raise", "badha",
                                  "rupaye", "rupees", "rs", "₹", "kar du", "karun", "karu", "kar doon"):
            tools.append("simulate_price"); return self.price(items[0], nums[-1])
        h = self.hour_in(q)
        if h is not None and has(q, "open", "khol", "khula", "close", "band kar", "late", "baad", "pehle",
                                 "early", "start"):
            tools.append("simulate_hours"); return self.hours(h)
        if has(q, "combo", "saath", "together", "bundle", "offer"):
            tools.append("combos"); return self.combos(items)
        if has(q, "fest", "oasis", "bosm", "apogee"):
            tools.append("sales_mix"); return self.fest(q)
        if has(q, "garmi", "summer", "hot day", "sardi", "thand", "winter", "cold day", "baarish", "rain"):
            tools.append("sales_by_condition"); return self.season(q)
        if has(q, "exam", "midsem", "compre") and not future:
            tools += ["hourly_profile", "sales_by_condition"]; return self.exams()
        if has(q, "cash", "nakad"):
            tools.append("overview"); return self.overview(q)
        if has(q, "profit", "munafa", "margin", "kamata", "earn the most"):
            tools.append("menu_matrix"); return self.menu(q, items)
        if has(q, "brief", "plan bata", "ka plan", "summary", "aaj ka", "kal ka plan"):
            tools.append("daily_brief"); return self.brief()
        if has(q, "banau", "banaun", "bana", "prep", "ready", "make", "mangwa", "stock", "maal", "doodh", "milk"):
            tools.append("prep_plan"); return self.prep(items, q)
        why = has(q, "kyu", "kyon", "kyun", "why", "giri", "gira", "drop", "kam ", "lower", "higher", "badh")
        if months and why:
            tools.append("compare_periods"); return self.compare(q, months)
        if why and has(q, "sale", "kamai", "bikri", "revenue"):
            tools.append("detect_shifts"); return self.why()
        if future or (months and has(q, "revenue", "sale", "kamai")):
            tools.append("forecast_revenue"); return self.forecast(q, months)
        if has(q, "hatau", "hata", "remove", "drop", "profit", "margin", "munafa", "rakhna", "rakhu", "menu",
               "kamata", "earn the most"):
            tools.append("menu_matrix"); return self.menu(q, items)
        if has(q, "rush", "bheed", "busy", "time", "kab", "hour", "ghante", "slow"):
            tools.append("hourly_profile"); return self.hourly()
        if has(q, "total", "saal", "year", "kamai", "earning", "cash", "nakad"):
            tools.append("overview"); return self.overview(q)
        if has(q, "bika", "bikta", "bik", "sell", "sold", "sale", "popular", "top", "kitna", "how much", "how many"):
            tools.append("sales_mix"); return self.sales(q, items)
        return ("Yeh sawal mujhe samajh nahi aaya. Main yeh bata sakta hoon:\n"
                "- Kal kitne samose banau? · Kal ki sale kitni hogi?\n"
                "- Maggi ₹60 karun toh? · Kaunsa combo chalau? · Menu me se kya hatau?\n"
                "- October me sales September se kam kyu thi? · Kis time bheed hoti hai?\n"
                "- Regular customers kaun hain? · Kya UPI band hua tha?\n"
                "Suggestion: upar wale jaisa sawal poochho, item ka naam saath me likho.")

    # ------------------------------------------------------------------ answers
    def prep(self, items, q):
        A = self.A
        r = A.prep_plan()
        rows = r["items"]
        names = {A.menu.names[i] for i in items}
        chosen = [x for x in rows if x["item"] in names] if names else rows
        lines = []
        if names and not chosen:      # asked about a non-batch item: forecast it instead
            fc = A.forecast_items(items, days=1)["forecasts"]
            for f in fc:
                lines.append(f"- {f['item']}: kal ~{f['p50']} (range {f['p10']}-{f['p90']})")
            return (f"Kal ({r['date']}) ka andaaza:\n" + "\n".join(lines) +
                    "\nSuggestion: yeh pehle se banne wala item nahi hai; jitna andaaza hai utna saaman rakho, thoda extra backup me.")
        if has(q, "doodh", "milk") and not names:
            chai = [i for i in A.ids if A.menu.category.get(i) == "beverage_hot"]
            fc = A.forecast_items(chai, days=1)["forecasts"]
            tot = sum(f["p50"] for f in fc); hi = sum(f["p90"] for f in fc)
            return (f"Kal ~{tot} garam drinks (busy din {hi} tak): " +
                    ", ".join(f"{f['item']} {f['p50']}" for f in fc if f["p50"] >= 1) +
                    "\nSuggestion: doodh in cups ke hisaab se mangwao (aapki recipe ka ml per cup x cups); "
                    f"busy din ke liye {hi} cups ka doodh rakho.")
        for x in chosen:
            lines.append(f"- {x['item']}: {x['recommended_prep']} banao "
                         f"(demand {x['demand_p10']}-{x['demand_p90']}, most likely {x['demand_most_likely']})")
        widest = max(chosen, key=lambda x: (x["demand_p90"] or 0) - (x["demand_p10"] or 0))
        return (f"Kal ({r['date']}) ke liye prep:\n" + "\n".join(lines) +
                f"\nSuggestion: {widest['item']} ka andaaza sabse kam pakka hai "
                f"({widest['demand_p10']}-{widest['demand_p90']}); pehle {widest['demand_most_likely']} banao, "
                "rush se pehle zaroorat ho to ek batch aur.")

    def forecast(self, q, months):
        A = self.A
        if months:
            s, e = self.month_range(months[0], future=True)
            days = (e - s).days + 1
            r = A.forecast_revenue(days=days, start=s)
            open_days = [d for d in r["days"] if not d["closed"]]
            periods = pd.Series([d["period"] for d in open_days]).value_counts().index.tolist()  # main first
            lo = min(d["revenue_p50"] for d in open_days); hi = max(d["revenue_p50"] for d in open_days)
            return (f"{s:%B %Y} ({', '.join(periods)}): roz ~{rs(lo)}-{rs(hi)} (most likely per day), "
                    f"poore mahine ~{rs(r['total_p50'])}. Mausam monthly average maana hai.\n"
                    f"Suggestion: {periods[0]} ke hisaab se stock plan karo; jo din sabse kam hai "
                    f"({rs(lo)}) us din kam batch banao.")
        week = has(q, "hafte", "week", "7 din", "saat din")
        r = A.forecast_revenue(days=7)
        d = r["days"][0]
        if week:
            best = max(r["days"], key=lambda x: x["revenue_p50"]); low = min(r["days"], key=lambda x: x["revenue_p50"])
            return (f"Agle 7 din: ~{rs(r['total_p50'])} total (cash share assume kiya). "
                    f"Sabse acha din {best['weekday']} ({rs(best['revenue_p50'])}), "
                    f"sabse kam {low['weekday']} ({rs(low['revenue_p50'])}).\n"
                    f"Suggestion: {best['weekday']} ke liye extra batch aur doodh ready rakho.")
        return (f"Kal {d['date']} ({d['weekday']}, {d['period']}): sale {rs(d['revenue_p10'])}-{rs(d['revenue_p90'])}, "
                f"most likely {rs(d['revenue_p50'])} (UPI ~{rs(d['upi_p50'])}; cash share assume kiya).\n"
                f"Suggestion: {rs(d['revenue_p50'])} ke hisaab se tayari karo, upar ke range ke liye thoda backup.")

    def price(self, iid, new_price):
        A = self.A
        r = A.simulate_price(iid, new_price)
        n, a = r["now"], r["after_most_likely"]
        risky = "assumed" in str(r["source"]).lower() or "unreliable" in str(r["source"]).lower()
        verdict = ("try it for 2 weeks and compare daily units" if r["profit_change_per_day"] > 0
                   else "keep the current price")
        return (f"{r['item']} {rs(r['current_price'])} -> {rs(r['new_price'])}: roz ~{n['units_per_day']} se "
                f"~{a['units_per_day']} units, profit {rs(n['profit_per_day'])} -> {rs(a['profit_per_day'])}/day "
                f"(range {rs(r['after_if_customers_more_sensitive']['profit_per_day'])}-"
                f"{rs(r['after_if_customers_less_sensitive']['profit_per_day'])}). Yeh andaaza kahan se: {r['source']}."
                + (" Yeh andaaza pakka nahi hai." if risky else "") +
                f"\nSuggestion: {verdict}.")

    def elasticity(self, iid):
        e = self.A.estimate_elasticity(iid)
        name = self.A.menu.names[iid]
        if not e:
            return (f"{name} ka daam data ke dauran badla nahi, isliye asar naap nahi sakte.\n"
                    f"Suggestion: daam badlo toh 2 hafte roz ki bikri note karo.")
        sure = "andaaza pakka hai" if e["reliable"] else f"andaaza pakka nahi ({e['reliability_note']})"
        effect = ("daam badhne par log kam khareedte hain" if e["elasticity"] and e["elasticity"] > 0
                  else "daam badhne ke baad bikri kam hoti nahi dikhi")
        return (f"{name}: {e['change']}. {effect}; {sure}.\n"
                "Suggestion: " + ("isi number se agla price decision lo." if e["reliable"] else
                                  "UPI remark me item likhwao (jaise 'maggi'), tab yeh naap pakka hoga."))

    def hours(self, h):
        r = self.A.simulate_hours(h)
        if "est_extra_revenue_per_day" not in r:
            return (f"{r['hour']} par stall pehle se khula hai (abhi ~{rs(r.get('current_revenue_per_day'))}/day).\n"
                    "Suggestion: timing badalne se pehle slow hours ka offer try karo.")
        return (f"{r['hour']} wala ghanta jodne se roz ~{rs(r['est_extra_revenue_per_day'])} extra "
                f"(range {rs(r['range'][0])}-{rs(r['range'][1])}); method: {r['method']}.\n"
                f"Suggestion: 2 hafte try karo; agar roz {rs(r['range'][0])} se kam aaye toh band kar do.")

    def combos(self, items):
        A = self.A
        r = A.combos()
        rules = r["rules"]
        if items:
            names = {A.menu.names[i] for i in items}
            own = [x for x in rules if x["if_buys"] in names or x["also_buys"] in names]
            if r.get("existing_combo") and r["existing_combo"]["item"] in names | {A.menu.names.get("COMBO_CS")}:
                c = r["existing_combo"]
                return (f"{c['item']} class days me roz ~{c['est_units_per_class_day']} bik raha hai "
                        f"(UPI amounts se andaaza).\n"
                        f"Suggestion: board pe combo ka daam bada likho aur shaam ke rush me bolkar offer karo.")
            if own:
                rules = own
        if not rules:
            return ("Remarks me itne combos nahi mile ki pakka keh sakein.\n"
                    "Suggestion: customers se UPI remark me item likhwao.")
        top = rules[:4]
        return ("Log yeh saath lete hain:\n" + "\n".join(
            f"- {x['if_buys']} lene wale {x['how_often_pct']}% log saath me {x['also_buys']} bhi lete hain ("
            f"{x['times_seen']} baar dekha)" for x in top) +
            f"\nSuggestion: {top[0]['if_buys']} + {top[0]['also_buys']} ka combo thoda kam daam pe try karo.")

    def menu(self, q, items):
        A = self.A
        r = A.menu_matrix()
        rows = r["items"]
        if items:
            names = {A.menu.names[i] for i in items}
            own = [x for x in rows if x["item"] in names]
            if own:
                x = own[0]
                return (f"{x['item']}: {x['class_']} (kul bikri ka {x['mix_pct']}%, ek piece pe kamai {rs(x['margin'])}, "
                        f"kul kamai {rs(x['contribution'])}, {r['period']}).\n"
                        f"Suggestion: {x['action']}.")
        if has(q, "profit", "munafa", "margin", "kamata", "earn"):
            top = rows[:5]
            return ("Sabse zyada kamai dene wale items:\n" + "\n".join(
                f"- {x['item']}: {rs(x['contribution'])} kul kamai ({x['class_']}, ek piece pe {rs(x['margin'])})" for x in top) +
                f"\nSuggestion: {top[0]['item']} kabhi khatam na ho; isko board pe upar rakho.")
        dogs = [x for x in rows if x["class_"] == "Weak item"][-5:]
        puzzles = [x for x in rows if x["class_"] == "Good profit, few buyers"][:3]
        s = "Kam bikne aur kam kamai wale items: " + ", ".join(f"{x['item']} ({x['mix_pct']}%)" for x in dogs)
        if puzzles:
            s += "\nAchhi kamai par kam bikri (inhe aage badhao): " + ", ".join(x["item"] for x in puzzles)
        return s + (f"\nSuggestion: {dogs[0]['item']} hatane ka socho, jab tak woh customers ko kheench nahi raha."
                    if dogs else "\nSuggestion: abhi koi item hatane layak nahi.")

    def hourly(self):
        r = self.A.hourly_profile(days=28)
        per = {x["hour"]: x for x in r["per_hour"]}
        b, s = r["busiest_hours"][0], r["slowest_hours"][0]
        return (f"Sabse zyada bheed: {', '.join(r['busiest_hours'])} "
                f"({b} pe roz ~{per[b]['upi_payments_per_day']} UPI payments). "
                f"Sabse kam: {', '.join(r['slowest_hours'])} ({s} pe ~{per[s]['upi_payments_per_day']}).\n"
                f"Suggestion: {b} se pehle batch ready rakho; {s} me chhota offer chalao.")

    def _condition(self, cond, extra=""):
        A = self.A
        r = A.sales_by_condition(cond)
        if "sells_more" not in r:
            return f"Aise din ka data kam hai ({r['definition']}).\nSuggestion: aise din bikri note karo."
        more = r["sells_more"][:5]
        rev = r["avg_daily_revenue"]
        return (f"{r['definition']} ({r['days']} din{extra}): roz ki kamai {rs(rev[0])} vs {rs(rev[1])}.\n"
                "Zyada bikta hai:\n" +
                "\n".join(f"- {x['item']}: {x['per_day']}/day vs {x['normal_per_day']} ({x['ratio']}x)" for x in more) +
                f"\nSuggestion: aise din {more[0]['item']} ka stock ~{more[0]['ratio']}x rakho.")

    def exams(self):
        h = self.A.hourly_profile(days=400, phase="compre")
        return self._condition("exam", extra=f", bheed {', '.join(h['busiest_hours'])} pe")

    def season(self, q):
        cond = "rain" if has(q, "baarish", "rain") else "cold" if has(q, "sardi", "thand", "winter", "cold") else "hot"
        return self._condition(cond)

    def fest(self, q):
        A = self.A
        cal = A.calendar.copy()
        cal["start"], cal["end"] = pd.to_datetime(cal["start"]).dt.date, pd.to_datetime(cal["end"]).dt.date
        fests = cal[(cal.phase == "fest") & (cal.start <= A.last)]
        named = [f for f in ("oasis", "bosm", "apogee") if f in q]
        if named:
            fests = fests[fests.label.str.lower().str.contains(named[0])]
        if fests.empty:
            return "Data me aisa fest nahi mila.\nSuggestion: fest ke din bikri note karo."
        f = fests.iloc[-1]
        idx = np.array(A.daily.index)
        mask = (idx >= f.start) & (idx <= f.end)
        base = (idx < f.start) & (idx >= f.start - timedelta(days=30)) & (A.daily.phase == "classes").values
        a, na = self._mix(mask); b, nb = self._mix(base)
        top = a.sort_values(ascending=False).head(6)
        nxt = cal[(cal.phase == "fest") & (cal.start > A.last)]
        when = f" Agla fest: {nxt.iloc[0].label} {nxt.iloc[0].start}." if len(nxt) else ""
        return (f"Pichla {f.label} ({f.start} to {f.end}) me roz:\n" +
                "\n".join(f"- {A.menu.names[i]}: {v:.0f}/day (normal {b[i]:.0f}, {v / max(b[i], 0.5):.1f}x)"
                          for i, v in top.items()) + when +
                f"\nSuggestion: fest ke din {A.menu.names[top.index[0]]} ka ~{top.iloc[0]:.0f} ka stock rakho.")

    def compare(self, q, months):
        A = self.A
        if len(months) >= 2:
            first, second = months[0], months[1]
            base, target = (second, first) if has(q, "than", "se ", "compared", "vs") else (first, second)
        else:
            target = months[0]
            base = target - 1 if target > 1 else 12
        ra, rb = self.month_range(base), self.month_range(target)
        if not ra or not rb:
            return "Us mahine ka data nahi hai.\nSuggestion: data wale mahine (Nov 2025 - Nov 2026) poochho."
        r = A.compare_periods(str(ra[0]), str(ra[1]), str(rb[0]), str(rb[1]))
        dr = sorted(((k, v) for k, v in r["drivers_pct_change"].items() if v is not None), key=lambda x: -abs(x[1]))
        ctx = "; ".join(r["context"]) or "calendar/weather me khaas fark nahi"
        return (f"{ra[0]:%B} vs {rb[0]:%B}: roz ki UPI sale {rs(r['avg_daily_upi_sales'][0])} -> "
                f"{rs(r['avg_daily_upi_sales'][1])} ({r['change_pct']}%).\n"
                f"Sabse bade kaaran: " + ", ".join(f"{k} {v}%" for k, v in dr[:3]) + ".\n"
                f"Context: {ctx}.\n"
                f"Customers: {r['customers']['new_in_b']} naye, {r['customers']['not_returning']} wapas nahi aaye.\n"
                f"Suggestion: sabse bada kaaran '{dr[0][0]}' hai; agar woh calendar ki wajah se hai toh normal hai, "
                "warna us par kaam karo.")

    def why(self):
        A = self.A
        r = A.detect_shifts()
        if r["shifts"]:
            s = max(r["shifts"], key=lambda x: abs(x["change_pct"]))
            return (f"{s['slot']} ({s['hours']}) ki sale {s['since']} se {s['change_pct']}% badli "
                    f"({rs(s['before_per_day'])} -> {rs(s['after_per_day'])} per day UPI).\n"
                    "Suggestion: us din ke aas-paas kya badla (naya competitor, timing, menu) check karo.")
        b, a = A.last - timedelta(days=29), A.last
        r2 = A.compare_periods(str(b - timedelta(days=30)), str(b - timedelta(days=1)), str(b), str(a))
        return (f"Koi lasting badlav nahi mila. Pichle 30 din vs usse pehle: {r2['change_pct']}% "
                f"({'; '.join(r2['context']) or 'calendar same'}).\n"
                "Suggestion: kisi khaas mahine ke liye poochho, jaise 'October me sales kam kyu thi?'.")

    def sales(self, q, items):
        A = self.A
        days = 365 if has(q, "saal", "year") else 30
        r = A.sales_mix(days=days)
        rows = r["items"]
        if items:
            names = {A.menu.names[i] for i in items}
            own = [x for x in rows if x["item"] in names]
            if own:
                return ("\n".join(f"{x['item']}: {x['units']} units ({x['per_day']}/day, {x['share_units']}% of units), "
                                  f"~{rs(x['revenue'])} in {r['period']}" for x in own) +
                        "\nSuggestion: yeh UPI amounts se andaaza hai (+/-25%); ek hafta haath se gin ke check karo.")
        top = rows[:6]
        return (f"Sabse zyada bikne wale ({r['period']}, per day): " +
                ", ".join(f"{x['item']} {x['per_day']}" for x in top) +
                f"\nSuggestion: {top[0]['item']} aur {top[1]['item']} kabhi khatam na hon; rush se pehle check karo.")

    def overview(self, q):
        r = self.A.overview()
        lo, hi = sorted(r["estimated_total_revenue_range"])
        cash = r["estimated_total_revenue"] - r["upi_sales_total"]
        if has(q, "cash", "nakad"):
            return (f"UPI se {rs(r['upi_sales_total'])} aaye. Cash dikhta nahi; {r['cash_share_assumed']:.0%} maan kar "
                    f"cash ~{rs(cash)} (range {r['cash_share_range'][0]:.0%}-{r['cash_share_range'][1]:.0%}).\n"
                    "Suggestion: ek hafta roz ka cash gin lo, phir yeh andaaza pakka ho jayega.")
        return (f"{r['data_period']}: kul kamai ~{rs(r['estimated_total_revenue'])} (range {rs(lo)}-{rs(hi)}), "
                f"jisme UPI {rs(r['upi_sales_total'])}. {r['days_open']} din khula; class ke din roz "
                f"~{rs(r['avg_daily_revenue_class_days'])}.\n"
                "Suggestion: cash ka asli hissa ek hafta gin lo, range chhoti ho jayegi.")

    def customers(self, q):
        r = self.A.customer_insights()
        if has(q, "band ho", "stopped", "nahi aa", "nahi aate", "lapsed", "chhod"):
            lost = r["regulars_not_seen_21d"]
            if not lost:
                return "Koi regular 3 hafte se gayab nahi hai.\nSuggestion: regulars ko naam se yaad rakho."
            return (f"{len(lost)} regulars 3 hafte se nahi aaye:\n" + "\n".join(
                f"- {x['name']} (pehle {x['visits_per_week']}/week, aakhri baar {x['last_seen']})" for x in lost[:5]) +
                f"\nSuggestion: {lost[0]['name']} jaise regulars ko phone/WhatsApp pe chhota offer bhejo.")
        if has(q, "naye", "new"):
            return (f"Pichle 30 din me {r['new_customers_last_30d']} naye UPI customers aaye "
                    f"(kul {r['unique_upi_customers']}).\n"
                    "Suggestion: naye customers ko doosri visit pe chhota discount do.")
        top = r["top_customers"][:5]
        return (f"{r['regulars']} regulars, UPI sale ka {r['regulars_share_of_upi_sales_pct']}%. Top customers:\n" +
                "\n".join(f"- {x['name']}: {x['visits']} visits, {rs(x['spend'])}" for x in top) +
                "\nSuggestion: top regulars ke liye loyalty card (10 chai pe 1 free) try karo.")

    def outages(self):
        o = self.A.detect_outages()["suspected_outages"]
        if not o:
            return "Busy time pe UPI rukne ka koi saaf case nahi mila.\nSuggestion: cash ka chhutta ready rakho."
        return (f"{len(o)} baar busy time pe UPI ruka:\n" +
                "\n".join(f"- {x['date']} ({', '.join(x['hours'])}, ~{x['expected_payments']} payments miss)" for x in o[:5]) +
                "\nSuggestion: dusra UPI QR (alag bank) aur chhutta cash ready rakho.")

    def brief(self):
        r = self.A.daily_brief()
        d = r["revenue_forecast"]
        prep = ", ".join(f"{p['item']} {p['recommended_prep']}" for p in r["prep_list"])
        return (f"{r['date']} ({r['period']}): sale {rs(d['revenue_p10'])}-{rs(d['revenue_p90'])}, most likely "
                f"{rs(d['revenue_p50'])}. Rush: {', '.join(r['rush_hours'])}.\nPrep: {prep}.\n"
                f"Alerts: {'; '.join(r['alerts']) or 'none'}.\n"
                f"Suggestion: {r['rush_hours'][0]} se pehle prep poora rakho.")
