"""Day-by-day simulation of the stall. Produces the ground-truth order log.

Real-world effects modelled (see docs/RESEARCH_AND_ASSUMPTIONS.md):
  academic phases, fests, breaks, exam-week evenings, graduation/fresher churn,
  weather (heat, cold, rain, fog), weekday rhythm, item complementarity
  (true combos), price elasticity, launches, a competitor opening,
  limited batches -> stockouts -> substitution or lost sales,
  cash vs UPI (falling cash share),
  UPI outages, group orders, split bills, duplicate/typo payments.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
import numpy as np
import pandas as pd
from . import config as C

OPEN_H, CLOSE_H = C.STALL["open_hour"], C.STALL["close_hour"]
HOURS = np.arange(OPEN_H, CLOSE_H)  # 9 .. 18 (last sale before 19:00)
_HOUR_SHAPE = {6: 0.25, 7: 0.9, 8: 1.1, 9: 0.8, 10: 0.7, 11: 0.75, 12: 0.7, 13: 0.8, 14: 0.6, 15: 0.55,
               16: 0.9, 17: 1.25, 18: 1.2, 19: 0.9, 20: 0.85, 21: 1.0, 22: 1.0, 23: 0.8, 24: 0.45, 25: 0.15}
BASE_HOUR = np.array([_HOUR_SHAPE[h] for h in HOURS])
CHRONO = {
    "early": np.where(HOURS <= 10, 1.6, 1.0),
    "normal": np.ones(len(HOURS)),
    "owl": np.where(HOURS <= 10, 0.55, np.where(HOURS >= 17, 1.4, 1.0)),
}
GROUP_P = {"normal": [0.62, 0.22, 0.09, 0.04, 0.02, 0.01],
           "big": [0.38, 0.27, 0.16, 0.10, 0.05, 0.04]}
ELASTICITY = {"maggi": 1.4, "default": 0.8}       # true own-price elasticities


def slot_of(h):
    return ("morning" if h <= 10 else "midday" if h <= 15 else
            "evening" if h <= 19 else "night" if h <= 23 else "late")


def into_open_hours(t: datetime) -> datetime:
    """Move a timestamp into opening hours (09:00-18:59). Before opening -> same day from 09:00,
    after closing -> next day from 09:00. Minutes/seconds are kept so times stay spread out."""
    if t.hour < OPEN_H:
        return t.replace(hour=OPEN_H)
    if t.hour >= CLOSE_H:
        return (t + timedelta(days=1)).replace(hour=OPEN_H)
    return t


def before_close(t: datetime) -> datetime:
    """Cap a same-day follow-up (retry, refund) at closing time instead of rolling to tomorrow."""
    return min(t, t.replace(hour=CLOSE_H - 1, minute=59, second=59))


def build_items():
    items = []
    for (iid, name, cat, price, cost, temp, slots, batch, fried, pop) in C.MENU:
        items.append(dict(id=iid, name=name, category=cat, price0=price, cost0=cost,
                          temp=temp, slots=slots, batch=batch, fried=fried, base_pop=pop))
    return items


def price_on(iid, d, items_by_id):
    p = items_by_id[iid]["price0"]
    for it, eff, newp in sorted(C.PRICE_CHANGES, key=lambda x: x[1]):
        if it == iid and d >= eff:
            p = newp
    return p


def cost_on(iid, d, items_by_id):
    c = items_by_id[iid]["cost0"]
    milk_l = C.MILK_ITEMS.get(iid, 0)
    for what, eff, mult in C.COST_CHANGES:
        if what == "milk" and d >= eff and milk_l:
            c += milk_l * 56 * (mult - 1)
    if iid == "KULHAD_CHAI" and d >= date(2026, 1, 15):
        c += 3.0
    return round(c, 2)


def phase_of(d):
    for a, b, ph, label in C.CALENDAR:
        if a <= d <= b:
            return ph, label
    return "classes", "Classes"


class Simulator:
    def __init__(self, customers: pd.DataFrame, weather: pd.DataFrame, rng):
        self.rng = rng
        self.items = build_items()
        self.ids = [it["id"] for it in self.items]
        self.idx = {iid: i for i, iid in enumerate(self.ids)}
        self.by_id = {it["id"]: it for it in self.items}
        self.cust = customers.reset_index(drop=True)
        self.fav = np.vstack(self.cust["fav"].values)
        self.weather = weather.set_index("date")
        self.orders, self.order_items, self.daily = [], [], []
        self.deferred = []
        self.sold_hist = defaultdict(list)   # item -> [(date, sold)]
        self.oid = 0
        self.base_pop = np.array([it["base_pop"] for it in self.items])

    # ------------------------------------------------------------ context
    def item_multipliers(self, d, hour, ctx):
        n = len(self.items)
        m = np.ones(n)
        w = ctx["w"]
        hot = np.clip((w.tmax - 32) / 10, 0, 1.5)
        cold = np.clip((24 - w.tmax) / 10, 0, 1.6)
        slot = slot_of(hour)
        for i, it in enumerate(self.items):
            iid = it["id"]
            launch = C.LAUNCHES.get(iid)
            if launch and d < launch:
                m[i] = 0; continue
            s = it["slots"][slot]
            if iid == "POHA" and hour > 11:
                s = 0.0                                        # only a morning batch
            t = it["temp"]
            tf = np.exp(0.40 * cold - 0.50 * hot) if t == 1 else (
                np.exp(1.0 * hot - 0.9 * cold) if t == -1 else 1.0)
            rf = 1.0
            if w.rain_mm > 2:
                rf = 1.45 if it["fried"] else (1.2 if it["category"] == "beverage_hot" else
                                                (0.7 if t == -1 else 1.0))
            ff = 1.25 if (w.fog_morning and hour <= 10 and it["category"] == "beverage_hot") else 1.0
            ph = ctx["phase"]
            pf = 1.0
            if ph in ("midsem", "compre") and it["category"] in ("maggi",) or iid == "HOT_COFFEE":
                pf = 1.35 if ph in ("midsem", "compre") else 1.0
            if ph == "fest" and it["category"] in ("beverage_cold", "packaged", "sandwich"):
                pf = 1.35
            if ctx["dow"] == 6 and iid == "PARATHA":
                pf *= 1.6                                      # Sunday paratha brunch
            p_now, p0 = price_on(iid, d, self.by_id), it["price0"]
            e = ELASTICITY["maggi"] if it["category"] == "maggi" else ELASTICITY["default"]
            prf = (p_now / p0) ** (-e)
            m[i] = s * tf * rf * ff * pf * prf
        return m

    def hour_weights(self, ctx, chrono):
        w = BASE_HOUR * CHRONO[chrono]
        late = HOURS >= 17                                   # exam / fest evenings
        w = np.where(late, w * ctx["late_mult"], w)
        wx = ctx["w"]
        if wx.heatwave:
            w = np.where((HOURS >= 12) & (HOURS <= 16), w * 0.45, w)
            w = np.where(HOURS >= 17, w * 1.2, w)              # people come out once it cools
        if ctx["dow"] == 6:
            w = np.where(HOURS <= 9, w * 0.5, w)
            w = np.where((HOURS >= 10) & (HOURS <= 12), w * 1.5, w)
        if ctx["competitor"]:
            w = np.where(HOURS >= 16, w * C.COMPETITOR_EFFECT["evening"], w)
        return w / w.sum()

    # ------------------------------------------------------------ stock
    def plan_stock(self, d):
        """Owner's rule of thumb: last two same weekdays' sales x 1.1."""
        plan = {}
        for it in self.items:
            if not it["batch"] or it["id"] == "COMBO_CS":
                continue
            hist = [s for (dd, s) in self.sold_hist[it["id"]][-14:] if dd.weekday() == d.weekday()]
            recent = [s for (_, s) in self.sold_hist[it["id"]][-3:]]
            if len(hist) >= 1:
                base = 0.6 * np.mean(hist) + 0.4 * np.mean(recent)
            else:
                base = {"SAMOSA": 130, "KACHORI": 45, "MIRCHI_BADA": 30, "BREAD_PAKODA": 35,
                        "POHA": 30, "LASSI": 12}[it["id"]]
            batch = 10 if it["id"] in ("SAMOSA", "KACHORI") else 5
            q = int(np.ceil(max(base * 1.22 * self.rng.normal(1, 0.07), batch) / batch) * batch)
            plan[it["id"]] = q
        return plan

    # ------------------------------------------------------------ main loop
    def run(self):
        d = C.START
        while d <= C.END:
            self.simulate_day(d)
            d += timedelta(days=1)
        return self.results()

    def simulate_day(self, d):
        rng = self.rng
        w = self.weather.loc[d]
        phase, label = phase_of(d)
        presence, late_mult, out_mult = C.PHASES[phase]
        ctx = dict(w=w, phase=phase, dow=d.weekday(), late_mult=late_mult,
                   competitor=d >= C.COMPETITOR_OPEN)
        closed = d in C.CLOSED_DAYS
        stock = self.plan_stock(d)
        stock0 = dict(stock)
        demand = defaultdict(int); sold = defaultdict(int); lost = defaultdict(int)
        if closed:
            self._record_day(d, phase, label, w, closed, stock0, demand, sold, lost, 0, 0)
            for k in stock0: self.sold_hist[k].append((d, 0))
            return

        # --- who comes today
        cu = self.cust
        active = (cu.active_from.values <= d) & (cu.active_to.values >= d)
        pres = np.full(len(cu), presence)
        if phase == "winter_break":
            pres = np.where(cu.stays_winter.values, 0.85, 0.0)
        elif phase == "summer_break":
            pres = np.where(cu.stays_summer.values, 0.85, 0.0)
        pres = np.where(cu.type.values == "staff", np.where(phase in ("winter_break", "summer_break"),
                                                           0.8, 1.0), pres)
        day_mult = {5: 0.95, 6: 0.88}.get(d.weekday(), 1.0)
        if w.rain_mm > 8: day_mult *= 0.85
        if w.heatwave: day_mult *= 0.9
        if w.cold_wave: day_mult *= 1.05
        if ctx["competitor"]: day_mult *= C.COMPETITOR_EFFECT["other"]
        day_mult *= rng.lognormal(0, 0.07)
        lam = cu.rate.values * pres * active * day_mult
        visits = rng.poisson(lam)
        visitors = np.repeat(np.arange(len(cu)), visits)

        # outsiders: parents, visitors, delivery staff; many more during fests
        n_out = rng.poisson(9 * out_mult * day_mult)
        events = [("C", int(c)) for c in visitors] + [("O", None)] * n_out

        # assign hours, then process chronologically so stock depletes realistically
        timed = []
        hw_cache = {}
        for kind, c in events:
            chrono = cu.chronotype.values[c] if kind == "C" else "normal"
            if chrono not in hw_cache:
                hw_cache[chrono] = self.hour_weights(ctx, chrono)
            h = int(rng.choice(HOURS, p=hw_cache[chrono]))
            sec = int(rng.integers(0, 3600))
            timed.append((h * 3600 + sec, kind, c))
        timed.sort(key=lambda x: x[0])

        mult_cache = {}
        upi_rev = cash_rev = 0
        for tsec, kind, c in timed:
            h = tsec // 3600
            if h not in mult_cache:
                mult_cache[h] = self.item_multipliers(d, h, ctx)
            mult = mult_cache[h]
            big = phase in ("fest", "orientation") or kind == "O"
            g = 1 + int(rng.choice(6, p=GROUP_P["big" if big else "normal"]))
            fav = self.fav[c] if kind == "C" else self.base_pop
            people = []
            for p in range(g):
                pref = fav if p == 0 else 0.5 * fav + 0.5 * self.base_pop
                basket = self.choose_person(pref * mult, h, ctx, stock, demand, sold, lost, d)
                if basket:
                    people.append(basket)
            if not people:
                continue
            # split bill?
            split = g >= 2 and rng.random() < 0.22
            payers = []
            if split:
                for k, b in enumerate(people):
                    if k == 0 or kind == "O":
                        payers.append((kind, c, b))
                    else:
                        friend = int(rng.choice(np.flatnonzero(active))) if active.any() else c
                        payers.append(("C", friend, b))
            else:
                merged = defaultdict(int)
                for b in people:
                    for iid, q in b.items(): merged[iid] += q
                payers.append((kind, c, dict(merged)))
            for j, (pk, pc, basket) in enumerate(payers):
                t = datetime.combine(d, datetime.min.time()) + timedelta(seconds=int(tsec) + j * int(rng.integers(5, 40)))
                t = min(t, datetime.combine(d, datetime.min.time()) + timedelta(hours=CLOSE_H, seconds=-1))
                r = self.pay(t, d, pk, pc, basket, phase)
                upi_rev += r[0]; cash_rev += r[1]
        for k in stock0:
            used = sold[k] + (sold["COMBO_CS"] if k == "SAMOSA" else 0)
            self.sold_hist[k].append((d, used))
        self._record_day(d, phase, label, w, closed, stock0, demand, sold, lost, upi_rev, cash_rev)

    def choose_person(self, weights, h, ctx, stock, demand, sold, lost, d):
        rng = self.rng
        wsum = weights.sum()
        if wsum <= 0:
            return {}
        p = weights / wsum
        primary = self.ids[int(rng.choice(len(p), p=p))]
        basket = defaultdict(int)
        qty = 2 if (self.by_id[primary]["fried"] and rng.random() < 0.3) else 1
        basket[primary] += qty
        hot = ctx["w"].tmax >= 36
        cat = self.by_id[primary]["category"]
        add = []
        if cat == "snack_fried":
            if rng.random() < (0.35 if hot else 0.58):
                add.append("MASALA_CHAI" if rng.random() < 0.6 else "CUT_CHAI")
            elif hot and rng.random() < 0.2:
                add.append("COLD_DRINK")
        elif primary in ("POHA", "BREAD_OMELETTE") and rng.random() < 0.5:
            add.append("MASALA_CHAI" if rng.random() < 0.55 else "CUT_CHAI")
        elif primary == "PARATHA":
            if rng.random() < 0.45: add.append("MASALA_CHAI")
            elif hot and rng.random() < 0.3: add.append("LASSI")
        elif cat == "maggi":
            r = rng.random()
            if hot and r < 0.22: add.append("COLD_DRINK")
            elif r < 0.25: add.append("HOT_COFFEE" if h >= 17 else "MASALA_CHAI")
        elif cat == "sandwich":
            if d >= C.LAUNCHES["COLD_COFFEE"] and rng.random() < 0.3: add.append("COLD_COFFEE")
            elif rng.random() < 0.2: add.append("COLD_DRINK")
        elif cat == "beverage_hot" and rng.random() < 0.28:
            slot = slot_of(h)
            opts = {"morning": (["BUN_MASKA", "KACHORI", "BREAD_PAKODA", "BISCUIT"], [.35, .3, .2, .15]),
                    "evening": (["SAMOSA", "MIRCHI_BADA", "BUN_MASKA", "BISCUIT"], [.55, .2, .15, .1])}
            o, pp = opts.get(slot, (["SAMOSA", "BUN_MASKA", "BISCUIT"], [.45, .3, .25]))
            add.append(o[int(rng.choice(len(o), p=pp))])
        elif primary == "COLD_COFFEE" and rng.random() < 0.2:
            add.append("GRILL_SANDWICH" if rng.random() < 0.5 else "VEG_SANDWICH")
        for a in add:
            basket[a] += 1
        # combo substitution: masala chai + samosa -> combo at ₹25
        if (d >= C.LAUNCHES["COMBO_CS"] and basket.get("MASALA_CHAI") == 1
                and basket.get("SAMOSA") == 1 and rng.random() < 0.75):
            del basket["MASALA_CHAI"]; del basket["SAMOSA"]; basket["COMBO_CS"] = 1

        # stock check: true demand is recorded even if not served
        final = {}
        for iid, q in basket.items():
            demand[iid] += q
            sk = "SAMOSA" if iid == "COMBO_CS" else iid
            if sk in stock:
                avail = stock[sk]
                if avail >= q:
                    stock[sk] -= q; final[iid] = final.get(iid, 0) + q; sold[iid] += q
                else:
                    if avail > 0:
                        stock[sk] = 0; final[iid] = final.get(iid, 0) + avail; sold[iid] += avail
                    short = q - max(avail, 0)
                    lost[iid] += short
                    # substitute with another in-stock fried snack or chai
                    if rng.random() < 0.55:
                        subs = [s for s in ("SAMOSA", "KACHORI", "MIRCHI_BADA", "BREAD_PAKODA", "BUN_MASKA")
                                if s != sk and (s not in stock or stock[s] > 0)]
                        s = subs[int(rng.integers(len(subs)))]
                        if s in stock: stock[s] -= 1
                        final[s] = final.get(s, 0) + 1; sold[s] += 1
            else:
                final[iid] = final.get(iid, 0) + q; sold[iid] += q
        return final

    # ------------------------------------------------------------ payments
    def pay(self, t, d, kind, c, basket, phase):
        rng = self.rng
        amount = sum(price_on(i, d, self.by_id) * q for i, q in basket.items())
        if amount <= 0:
            return 0, 0
        cu = self.cust
        regular = kind == "C" and cu.rate.values[c] > 0.25
        discount = 5 if (regular and amount >= 50 and rng.random() < 0.05) else 0
        amount -= discount
        hour = t.hour + t.minute / 60 + (24 if t.date() > d else 0)
        outage = any(o[0] == d and o[1] <= hour < o[2] for o in C.UPI_OUTAGES)
        frac_year = (d - C.START).days / 365
        cash_p = (cu.cash_p.values[c] if kind == "C" else 0.42) * (1 - C.CASH_TREND * frac_year)
        if amount <= 15: cash_p = min(1, cash_p + 0.15)
        mode = "cash" if rng.random() < cash_p else "upi"
        if mode == "upi" and outage:
            r = rng.random()
            mode = "cash" if r < 0.6 else ("upi_deferred" if r < 0.85 and kind == "C" else "lost")
        self.oid += 1
        oid = f"O{self.oid:06d}"
        cid = cu.customer_id.values[c] if kind == "C" else f"OUT{self.oid:06d}"
        self.orders.append(dict(order_id=oid, datetime=t, date=d, customer_id=cid,
                                customer_kind="outsider" if kind == "O" else cu.type.values[c],
                                amount=amount, discount=discount, mode=mode, n_items=sum(basket.values()),
                                outage=outage, phase=phase))
        for iid, q in basket.items():
            self.order_items.append(dict(order_id=oid, item_id=iid, qty=q,
                                         unit_price=price_on(iid, d, self.by_id)))
        if mode == "upi_deferred":
            later = into_open_hours(t + timedelta(hours=float(rng.uniform(1.5, 20))))
            self.deferred.append(dict(order_id=oid, datetime=later, customer_id=cid, amount=amount))
            return amount, 0
        if mode == "lost":
            return 0, 0
        return (amount, 0) if mode == "upi" else (0, amount)

    def _record_day(self, d, phase, label, w, closed, stock0, demand, sold, lost, upi_rev, cash_rev):
        row = dict(date=d, phase=phase, period_label=label, closed=closed, tmax=w.tmax, tmin=w.tmin,
                   rain_mm=w.rain_mm, heatwave=w.heatwave, cold_wave=w.cold_wave, fog=w.fog_morning,
                   competitor_open=d >= C.COMPETITOR_OPEN,
                   upi_outage=any(o[0] == d for o in C.UPI_OUTAGES),
                   upi_sales=upi_rev, cash_sales=cash_rev)
        for iid in self.ids:
            row[f"demand_{iid}"] = demand.get(iid, 0)
            row[f"sold_{iid}"] = sold.get(iid, 0)
            row[f"lost_{iid}"] = lost.get(iid, 0)
            if iid in stock0:
                row[f"prepared_{iid}"] = stock0[iid]
        self.daily.append(row)

    def results(self):
        return dict(orders=pd.DataFrame(self.orders), order_items=pd.DataFrame(self.order_items),
                    daily=pd.DataFrame(self.daily), deferred=pd.DataFrame(self.deferred))
