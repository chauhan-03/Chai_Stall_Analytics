"""StallAnalytics: one object that turns (statement + menu) into decisions.

Every public method returns plain dicts / lists (JSON-safe) so the agent can
use them as tools and the app can render them.
"""
from __future__ import annotations

import hashlib
import json
import math
import pickle
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from .decompose import BasketDecomposer, SLOTS
from .forecast import (QuantileForecaster, add_level, baseline_last_week, calendar_frame,
                       weather_frame)
from .ingest import ingest
from .menu import Menu

ROOT = Path(__file__).resolve().parents[2]
SLOT_HOURS = {"morning": (6, 10), "midday": (11, 15), "evening": (16, 19), "night": (20, 23), "late": (24, 26)}
BATCH_SIZE = {"SAMOSA": 10, "KACHORI": 10}


def _r(x, nd=0):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return int(round(x)) if nd == 0 else round(float(x), nd)


class StallAnalytics:
    def __init__(self, statement, menu_csv, history_csv=None, calendar_csv=None, weather_csv=None,
                 closed_csv=None, cash_share=0.25, cash_range=(0.18, 0.32), cache_dir=None,
                 use_owner_prior=True):
        self.paths = dict(statement=str(statement), menu=str(menu_csv), history=str(history_csv),
                          calendar=str(calendar_csv), weather=str(weather_csv), closed=str(closed_csv))
        self.menu = Menu(menu_csv, history_csv)
        self.ids = self.menu.ids
        self.calendar = pd.read_csv(calendar_csv) if calendar_csv else pd.DataFrame(
            columns=["start", "end", "phase", "label"])
        self.weather = pd.read_csv(weather_csv) if weather_csv else None
        self.closed = set(pd.to_datetime(pd.read_csv(closed_csv)["date"]).dt.date) if closed_csv else set()
        self.cash_share, self.cash_range = cash_share, cash_range
        self.use_owner_prior = use_owner_prior
        self.cache_dir = Path(cache_dir or ROOT / "data" / "processed")
        self._item_models = {}
        self._load()

    # ------------------------------------------------------------------ load
    def _fingerprint(self):
        h = hashlib.md5()
        for k in ("statement", "menu", "history", "weather"):
            p = Path(self.paths[k])
            if p.exists():
                h.update(p.read_bytes())
        h.update(str(self.use_owner_prior).encode())
        return h.hexdigest()[:12]

    def _load(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache = self.cache_dir / f"decomposed_{self._fingerprint()}.pkl"
        if cache.exists():
            st = pickle.loads(cache.read_bytes())
        else:
            tx = ingest(self.paths["statement"])
            sales = tx[tx["class"] == "sale"].copy()
            w = self.weather if self.weather is not None else pd.DataFrame(
                {"date": sorted(set(sales.business_date)), "tmax": 30.0})
            dec = BasketDecomposer(self.menu, use_owner_prior=self.use_owner_prior)
            res = dec.fit_transform(sales, w)
            st = dict(tx=tx, sales=res["tx"], expected=res["expected"], map=res["map"],
                      theta=dec.theta_table(), prior=dec.prior_used, pair_mats=res["pair_mats"])
            cache.write_bytes(pickle.dumps(st))
        self.tx, self.sales, self.expected = st["tx"], st["sales"], st["expected"]
        self.map, self.theta, self.prior_used = st["map"], st["theta"], st["prior"]
        self.pair_mats = st["pair_mats"]
        self._build_daily()

    def _build_daily(self):
        s, tx = self.sales, self.tx
        first, last = min(tx.business_date), max(tx.business_date)
        self.first, self.last = first, last
        days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
        cal = calendar_frame(days, self.calendar, self.closed)
        d = cal.set_index("date")
        d["upi_sales"] = s.groupby("business_date")["net_amount"].sum().reindex(d.index).fillna(0)
        d["n_txn"] = s.groupby("business_date").size().reindex(d.index).fillna(0)
        kh = tx[tx["class"] == "khata_settlement"]
        d["khata_received"] = kh.groupby("business_date")["amount"].sum().reindex(d.index).fillna(0)
        self.khata_ratio = float(d.khata_received.sum() / max(d.upi_sales.sum(), 1))
        d["closed"] = d["closed"] | (d["n_txn"] == 0)
        self.scale = (1 / (1 - self.cash_share)) * (1 + self.khata_ratio)
        lo, hi = self.cash_range
        d["revenue_est"] = d.upi_sales / (1 - self.cash_share) + d.upi_sales * self.khata_ratio
        d["revenue_low"] = d.upi_sales / (1 - lo) + d.upi_sales * self.khata_ratio
        d["revenue_high"] = d.upi_sales / (1 - hi) + d.upi_sales * self.khata_ratio
        if self.weather is not None:
            wf = weather_frame(list(d.index), self.weather).set_index("date")
            d = d.join(wf)
        units = self.expected.groupby(s["business_date"].values).sum().reindex(d.index).fillna(0)
        self.units_upi = units
        self.units = units * self.scale                       # estimated all-payment units
        self.daily = d
        self.frame = d.reset_index().rename(columns={"index": "date"})

    # ------------------------------------------------------------------ helpers
    def _period(self, start=None, end=None, days=None):
        end = pd.to_datetime(end).date() if end else self.last
        if start:
            start = pd.to_datetime(start).date()
        else:
            start = end - timedelta(days=(days or 30) - 1)
        return max(start, self.first), min(end, self.last)

    def _mask(self, start, end, open_only=True):
        idx = self.daily.index
        m = (idx >= start) & (idx <= end)
        if open_only:
            m &= ~self.daily.closed.values
        return m

    def _price(self, iid, d=None):
        v = self.menu.prices_on(d or self.last)
        return float(v[self.ids.index(iid)])

    def _resolve_item(self, name):
        if name in self.ids:
            return name
        n = name.lower().replace("_", " ")
        for iid in self.ids:
            if n == self.menu.names[iid].lower():
                return iid
        for iid in self.ids:
            if n in self.menu.names[iid].lower() or n in iid.lower().replace("_", " "):
                return iid
        alias = {"chai": "MASALA_CHAI", "tea": "MASALA_CHAI", "samose": "SAMOSA", "coke": "COLD_DRINK",
                 "omelette": "BREAD_OMELETTE", "sandwich": "VEG_SANDWICH", "coffee": "HOT_COFFEE"}
        for k, v in alias.items():
            if k in n:
                return v
        raise ValueError(f"Unknown item '{name}'. Menu items: {', '.join(self.menu.names.values())}")

    # ------------------------------------------------------------------ tools
    def overview(self):
        d = self.daily
        open_d = d[~d.closed]
        cls = open_d[open_d.phase == "classes"]
        by_class = self.tx["class"].value_counts().to_dict()
        return {
            "data_period": f"{self.first} to {self.last}",
            "days_open": int((~d.closed).sum()), "days_closed": int(d.closed.sum()),
            "upi_sales_total": _r(d.upi_sales.sum()),
            "estimated_total_revenue": _r(d.revenue_est.sum()),
            "estimated_total_revenue_range": [_r(d.revenue_high.sum()), _r(d.revenue_low.sum())],
            "cash_share_assumed": self.cash_share, "cash_share_range": list(self.cash_range),
            "khata_settlements_total": _r(d.khata_received.sum()),
            "avg_daily_revenue_class_days": _r(cls.revenue_est.mean()),
            "avg_upi_payments_per_class_day": _r(cls.n_txn.mean()),
            "avg_upi_ticket": _r(self.sales.net_amount.mean(), 1),
            "statement_rows": by_class,
            "item_prior_used": self.prior_used,
        }

    def sales_mix(self, start=None, end=None, days=30, top=None):
        a, b = self._period(start, end, days)
        m = self._mask(a, b)
        u = self.units[m].sum()
        n_days = max(int(m.sum()), 1)
        rows = []
        for iid, q in u.sort_values(ascending=False).items():
            p = self._price(iid, b)
            if np.isnan(p) or q < 0.5:
                continue
            rows.append(dict(item=self.menu.names[iid], item_id=iid, units=_r(q), per_day=_r(q / n_days, 1),
                             revenue=_r(q * p), share_units=_r(q / u.sum() * 100, 1)))
        return {"period": f"{a} to {b}", "open_days": n_days, "items": rows[:top] if top else rows,
                "note": "Units are estimated from UPI payment amounts and scaled up for cash and khata; "
                        "treat individual numbers as +/- 25%."}

    def hourly_profile(self, start=None, end=None, days=60, phase=None):
        a, b = self._period(start, end, days)
        s = self.sales[(self.sales.business_date >= a) & (self.sales.business_date <= b)]
        if phase:
            ph = self.daily.phase
            s = s[s.business_date.map(ph) == phase]
        n_days = max(s.business_date.nunique(), 1)
        g = s.groupby("hour").agg(payments=("net_amount", "size"), upi_sales=("net_amount", "sum"))
        g = g / n_days
        top = g.payments.sort_values(ascending=False).head(3).index.tolist()
        slow = g[(g.index >= 7) & (g.index <= 23)].payments.sort_values().head(3).index.tolist()
        fmt = lambda h: f"{h % 24:02d}:00"
        return {"period": f"{a} to {b}", "phase": phase or "all",
                "per_hour": [dict(hour=fmt(h), upi_payments_per_day=_r(r.payments, 1),
                                  est_revenue_per_day=_r(r.upi_sales * self.scale)) for h, r in g.iterrows()],
                "busiest_hours": [fmt(h) for h in top], "slowest_hours": [fmt(h) for h in slow]}

    def combos(self, start=None, end=None, days=365, top=10, min_pair=5):
        """Which items are bought together.

        Primary evidence: payments where the customer typed what they bought
        ("samosa + chai") - real baskets, about 4-5% of UPI payments.
        Secondary: probabilistic co-occurrence from the amount decomposition
        (weak: amounts alone say little about pairing).
        """
        a, b = self._period(start, end, days)
        s = self.sales[(self.sales.business_date >= a) & (self.sales.business_date <= b)]
        hints = [h for h in s["hint"] if len(h) >= 1]
        n = len(hints)
        cnt, pair = {}, {}
        for h in hints:
            for x in h:
                cnt[x] = cnt.get(x, 0) + 1
            for i in range(len(h)):
                for j in range(i + 1, len(h)):
                    k = tuple(sorted((h[i], h[j])))
                    pair[k] = pair.get(k, 0) + 1
        rules = []
        for (x, y), c in pair.items():
            if c < min_pair:
                continue
            lift = c * n / (cnt[x] * cnt[y])
            ante, cons = (x, y) if cnt[x] <= cnt[y] else (y, x)
            # Wilson lower bound on confidence: penalise tiny samples
            p_hat, m = c / cnt[ante], cnt[ante]
            z = 1.28
            lb = (p_hat + z * z / (2 * m) - z * math.sqrt(p_hat * (1 - p_hat) / m + z * z / (4 * m * m))) / (1 + z * z / m)
            rules.append(dict(if_buys=self.menu.names[ante], also_buys=self.menu.names[cons], times_seen=c,
                              confidence=_r(p_hat * 100, 1), confidence_lower_bound=_r(lb * 100, 1),
                              lift=_r(lift, 2)))
        rules.sort(key=lambda r: (-r["lift"] * math.log1p(r["times_seen"])))
        # explicit combo item uptake
        combo = None
        if "COMBO_CS" in self.ids and not np.isnan(self._price("COMBO_CS")):
            m = self._mask(a, b) & (self.daily.phase.values == "classes")
            combo = dict(item=self.menu.names["COMBO_CS"], est_units_per_class_day=_r(self.units.loc[m, "COMBO_CS"].mean(), 1))
        return {"period": f"{a} to {b}", "labelled_baskets": n, "rules": rules[:top],
                "existing_combo": combo,
                "method": "association rules (support, confidence, lift) on baskets customers described in "
                          "UPI remarks; confidence lower bound = Wilson 80%",
                "caveat": "Only ~5% of customers write remarks; rules are directional, check with the owner."}

    # ------------------------------------------------------------------ forecasting
    def _future_frame(self, days_ahead, start=None):
        start = pd.to_datetime(start).date() if start else self.last + timedelta(days=1)
        dates = [start + timedelta(days=i) for i in range(days_ahead)]
        f = calendar_frame(dates, self.calendar, self.closed)
        if self.weather is not None:
            f = f.merge(weather_frame(dates, self.weather), on="date", how="left")
        else:
            f["tmax"], f["rain_mm"], f["heatwave"] = 30.0, 0.0, 0.0
        return f

    def _fit(self, key, y, train_end=None):
        fr = self.frame.copy()
        fr["level"] = add_level(fr, y)
        mask = np.ones(len(fr), bool) if train_end is None else (fr.date <= train_end).values
        model = QuantileForecaster().fit(fr[mask].reset_index(drop=True), np.asarray(y)[mask])
        last_level = fr["level"][mask].iloc[-1]
        return model, last_level

    def forecast_revenue(self, days=7, start=None):
        model, lvl = self._fit("revenue", self.daily.upi_sales.values)
        f = self._future_frame(days, start)
        f["level"] = lvl
        p = model.predict(f)
        lo, hi = self.cash_range
        rows = []
        for r, fr in zip(p.itertuples(), f.itertuples()):
            k = lambda v, c: v / (1 - c) + v * self.khata_ratio
            rows.append(dict(date=str(r.date), weekday=pd.Timestamp(r.date).day_name(), period=fr.period_label,
                             upi_p50=_r(r.p50), revenue_p10=_r(k(r.p10, lo)), revenue_p50=_r(k(r.p50, self.cash_share)),
                             revenue_p90=_r(k(r.p90, hi)), closed=bool(fr.closed),
                             weather=f"{fr.tmax:.0f}C ({fr.weather_source})" if "weather_source" in f else None))
        tot = sum(r["revenue_p50"] for r in rows)
        return {"days": rows, "total_p50": tot,
                "method": "gradient-boosted quantile model on UPI sales; P10 uses low cash share, P90 high"}

    def _item_model(self, iid):
        if iid not in self._item_models:
            self._item_models[iid] = self._fit(iid, self.units[iid].values)
        return self._item_models[iid]

    def forecast_items(self, items=None, days=1, start=None):
        items = [self._resolve_item(i) for i in (items or self.ids)]
        f = self._future_frame(days, start)
        out = []
        for iid in items:
            if np.isnan(self._price(iid)):
                continue
            model, lvl = self._item_model(iid)
            ff = f.copy(); ff["level"] = lvl
            p = model.predict(ff)
            for r in p.itertuples():
                out.append(dict(date=str(r.date), item=self.menu.names[iid], item_id=iid,
                                p10=_r(r.p10), p50=_r(r.p50), p90=_r(r.p90)))
        return {"forecasts": out, "note": "Units across all payment modes (estimated)."}

    # ------------------------------------------------------------------ prep plan
    @staticmethod
    def _quantile(p10, p50, p90, cr):
        z = norm.ppf(cr)
        z10 = norm.ppf(0.9)
        if z <= 0:
            return p50 + (p50 - p10) * z / z10
        return p50 + (p90 - p50) * z / z10

    def prep_plan(self, day=None, salvage_share=0.0):
        day = pd.to_datetime(day).date() if day else self.last + timedelta(days=1)
        fc = self.forecast_items([i for i in self.ids if self.menu.batch.get(i) and i != "COMBO_CS"],
                                 days=1, start=day)["forecasts"]
        combo = self.forecast_items(["COMBO_CS"], days=1, start=day)["forecasts"] if not np.isnan(
            self._price("COMBO_CS")) else []
        rows = []
        for r in fc:
            iid = r["item_id"]
            p, c = self._price(iid, day), self.menu.cost[iid]
            cu, co = p - c, c - salvage_share * c
            cr = cu / (cu + co)
            p10, p50, p90 = r["p10"], r["p50"], r["p90"]
            if iid == "SAMOSA" and combo:               # combo uses a samosa too
                p10 += combo[0]["p10"]; p50 += combo[0]["p50"]; p90 += combo[0]["p90"]
            q = max(0.0, self._quantile(p10, p50, p90, cr))
            bs = BATCH_SIZE.get(iid, 5)
            q_rounded = int(math.ceil(q / bs) * bs)
            rows.append(dict(item=self.menu.names[iid], demand_p10=p10, demand_most_likely=p50, demand_p90=p90,
                             recommended_prep=q_rounded, batch_size=bs, critical_ratio=_r(cr, 2),
                             margin_per_unit=_r(cu, 1), cost_per_unit=_r(c, 1)))
        return {"date": str(day), "items": rows,
                "method": "newsvendor: prepare up to the demand quantile = margin / (margin + cost of a "
                          "wasted unit); rounded up to batch size",
                "caveat": "Demand is learned from sales; on sell-out days true demand was higher, so "
                          "treat P90 as a floor for big days."}

    # ------------------------------------------------------------------ menu engineering
    def menu_matrix(self, start=None, end=None, days=60):
        a, b = self._period(start, end, days)
        m = self._mask(a, b) & (self.daily.phase.values != "summer_break") & (
            self.daily.phase.values != "winter_break")
        u = self.units[m].sum()
        rows = []
        for iid in self.ids:
            p = self._price(iid, b)
            if np.isnan(p) or u[iid] < 1:
                continue
            cm = p - self.menu.cost[iid]
            rows.append(dict(item=self.menu.names[iid], item_id=iid, units=float(u[iid]), price=p, cm=cm))
        df = pd.DataFrame(rows)
        df["mix_pct"] = df.units / df.units.sum() * 100
        pop_cut = 0.7 * 100 / len(df)
        cm_cut = (df.cm * df.units).sum() / df.units.sum()
        def cls(r):
            hp, hc = r.mix_pct >= pop_cut, r.cm >= cm_cut
            return "Star" if hp and hc else "Plowhorse" if hp else "Puzzle" if hc else "Dog"
        df["class"] = df.apply(cls, axis=1)
        advice = {"Star": "keep quality and visibility; don't discount",
                  "Plowhorse": "popular but thin margin: small price rise or pair with a high-margin item",
                  "Puzzle": "good margin but few buyers: promote, rename, put in a combo",
                  "Dog": "low margin and few buyers: simplify or remove unless it drives traffic"}
        df["action"] = df["class"].map(advice)
        df["total_contribution"] = df.cm * df.units
        out = df.sort_values("total_contribution", ascending=False)
        return {"period": f"{a} to {b} (term days only)", "popularity_cutoff_pct": _r(pop_cut, 2),
                "avg_margin_cutoff": _r(cm_cut, 1),
                "items": [dict(item=r["item"], class_=r["class"], mix_pct=_r(r.mix_pct, 1), price=_r(r.price),
                               margin=_r(r.cm, 1), contribution=_r(r.total_contribution), action=r.action)
                          for _, r in out.iterrows()],
                "method": "Kasavana-Smith menu engineering matrix"}

    # ------------------------------------------------------------------ elasticity / what-if
    def estimate_elasticity(self, item, window=28, n_boot=300):
        iid = self._resolve_item(item)
        h = self.menu.hist[(self.menu.hist.item_id == iid) & (self.menu.hist.event == "price_change")]
        if h.empty:
            return None
        r = h.iloc[-1]
        eff = r.effective_date.date()
        changed = set(self.menu.hist[self.menu.hist.event == "price_change"].item_id)
        launched = set(self.menu.hist[self.menu.hist.event == "launch"].item_id)
        # control: unchanged items of the same category (same seasonality), else all unchanged
        same = [i for i in self.ids if i not in changed | launched and self.menu.category[i] == self.menu.category[iid]]
        ctrl = same if same and self.units[same].sum().sum() >= 0.3 * self.units[iid].sum() else \
            [i for i in self.ids if i not in changed | launched]
        d = self.daily
        ok = (~d.closed) & (d.phase == "classes")
        idx = d.index
        pre = [x for x in idx[ok & (idx < eff)]][-window:]
        post = [x for x in idx[ok & (idx >= eff)]][:window]
        if len(pre) < 7 or len(post) < 7:
            return None
        rel = np.log(self.units.loc[:, iid] + 0.5) - np.log(self.units.loc[:, ctrl].sum(1) + 0.5)
        dp = math.log(r.new_price / r.old_price)
        rng = np.random.default_rng(0)
        pre_v, post_v = rel.loc[pre].values, rel.loc[post].values
        est = -(post_v.mean() - pre_v.mean()) / dp
        boots = [-(rng.choice(post_v, len(post_v)).mean() - rng.choice(pre_v, len(pre_v)).mean()) / dp
                 for _ in range(n_boot)]
        # reliability: if the new price is a very common payment amount, the item's
        # sales can't be separated from other baskets with the same total
        post_sales = self.sales[self.sales.business_date.isin(post)]
        share_at_price = float((post_sales.net_amount.round() == round(r.new_price)).mean())
        reliable = share_at_price < 0.07 and est > 0
        return dict(item=self.menu.names[iid], change=f"₹{r.old_price:.0f} -> ₹{r.new_price:.0f} on {eff}",
                    reliable=bool(reliable),
                    reliability_note=(f"{share_at_price:.0%} of payments after the change were exactly "
                                      f"₹{r.new_price:.0f}, shared with other common baskets"
                                      if not reliable else "ok"),
                    elasticity=_r(est, 2), ci90=[_r(np.percentile(boots, 5), 2), _r(np.percentile(boots, 95), 2)],
                    control=[self.menu.names[c] for c in ctrl][:6],
                    method="difference-in-differences vs unchanged items, class days only")

    def simulate_price(self, item, new_price, days=28):
        iid = self._resolve_item(item)
        p0, c = self._price(iid), self.menu.cost[iid]
        e = self.estimate_elasticity(iid)
        source = "own price history"
        if e is None or e["elasticity"] is None or e["elasticity"] <= 0 or not e.get("reliable", True):
            same = [x for x in self.menu.hist.item_id.unique()
                    if self.menu.category.get(x) == self.menu.category[iid] and x != iid]
            ests = [self.estimate_elasticity(x) for x in same]
            ests = [x for x in ests if x and x["elasticity"] and x["elasticity"] > 0 and x["reliable"]]
            if ests:
                e = dict(elasticity=float(np.mean([x["elasticity"] for x in ests])),
                         ci90=[min(x["ci90"][0] for x in ests), max(x["ci90"][1] for x in ests)])
                source = f"same-category items ({', '.join(x['item'] for x in ests)})"
            else:
                e = dict(elasticity=0.8, ci90=[0.4, 1.2])
                source = "assumed typical value for street food (no price history)"
        a, b = self._period(None, None, 60)
        m = self._mask(a, b) & (self.daily.phase.values == "classes")
        q0 = float(self.units.loc[m, iid].tail(days).mean()) if m.any() else float(self.units[iid].mean())
        def outcome(el):
            q1 = q0 * (new_price / p0) ** (-el)
            return dict(units_per_day=_r(q1, 1), revenue_per_day=_r(q1 * new_price),
                        profit_per_day=_r(q1 * (new_price - c)))
        mid = outcome(e["elasticity"])
        lo, hi = outcome(max(e["ci90"][1], 0)), outcome(max(e["ci90"][0], 0))
        base = dict(units_per_day=_r(q0, 1), revenue_per_day=_r(q0 * p0), profit_per_day=_r(q0 * (p0 - c)))
        return {"item": self.menu.names[iid], "current_price": p0, "new_price": new_price, "unit_cost": c,
                "elasticity_used": _r(e["elasticity"], 2), "elasticity_range": e["ci90"], "source": source,
                "now": base, "after_most_likely": mid, "after_if_customers_more_sensitive": lo,
                "after_if_customers_less_sensitive": hi,
                "profit_change_per_day": _r(mid["profit_per_day"] - base["profit_per_day"]),
                "note": "Other items' sales may also shift (customers switch); not included."}

    def simulate_hours(self, extra_hour: int, days=30):
        """Rough value of opening one hour earlier/later, from the adjacent hour's sales."""
        prof = self.hourly_profile(days=days, phase="classes")["per_hour"]
        hrs = {int(r["hour"][:2]): r for r in prof}
        h = extra_hour % 24
        nb = [hrs[x]["est_revenue_per_day"] for x in ((h - 1) % 24, (h + 1) % 24) if x in hrs]
        if h in hrs:
            return {"hour": f"{h:02d}:00", "note": "already open at this hour",
                    "current_revenue_per_day": hrs[h]["est_revenue_per_day"]}
        est = 0.45 * max(nb) if nb else 0
        return {"hour": f"{h:02d}:00", "est_extra_revenue_per_day": _r(est),
                "range": [_r(est * 0.5), _r(est * 1.2)],
                "method": "45% of the busier neighbouring hour (demand thins at the edges of opening hours)"}

    # ------------------------------------------------------------------ diagnosis
    def compare_periods(self, a_start, a_end, b_start, b_end):
        A = self._period(a_start, a_end); B = self._period(b_start, b_end)
        def stats(p):
            m = self._mask(*p, open_only=False)
            d = self.daily[m]
            s = self.sales[(self.sales.business_date >= p[0]) & (self.sales.business_date <= p[1])]
            opn = d[~d.closed]
            slot_rev = {}
            for sl, (h0, h1) in SLOT_HOURS.items():
                slot_rev[sl] = s[(s.hour >= h0) & (s.hour <= h1)].net_amount.sum() / max(len(opn), 1)
            payers = set(s.vpa)
            return dict(days=len(d), closed_days=int(d.closed.sum()), avg_daily_upi=opn.upi_sales.mean(),
                        payments_per_day=opn.n_txn.mean(), avg_ticket=s.net_amount.mean(),
                        phase_mix=d.phase.value_counts().to_dict(),
                        avg_tmax=d.tmax.mean() if "tmax" in d else None,
                        rainy_days=int((d.rain_mm > 2).sum()) if "rain_mm" in d else None,
                        slot_rev=slot_rev, payers=payers)
        sa, sb = stats(A), stats(B)
        chg = lambda x, y: _r((y - x) / x * 100, 1) if x else None
        drivers = []
        drivers.append(("payments per day", chg(sa["payments_per_day"], sb["payments_per_day"])))
        drivers.append(("average ticket", chg(sa["avg_ticket"], sb["avg_ticket"])))
        for sl in SLOT_HOURS:
            drivers.append((f"{sl} sales", chg(sa["slot_rev"][sl], sb["slot_rev"][sl])))
        new = len(sb["payers"] - sa["payers"]); lost = len(sa["payers"] - sb["payers"])
        notes = []
        if sb["closed_days"] != sa["closed_days"]:
            notes.append(f"closed days: {sa['closed_days']} vs {sb['closed_days']}")
        if sa["phase_mix"] != sb["phase_mix"]:
            notes.append(f"academic calendar differs: {sa['phase_mix']} vs {sb['phase_mix']}")
        if sa["avg_tmax"] and sb["avg_tmax"] and abs(sa["avg_tmax"] - sb["avg_tmax"]) > 4:
            notes.append(f"weather: avg max temp {sa['avg_tmax']:.0f}C vs {sb['avg_tmax']:.0f}C")
        if sa["rainy_days"] is not None and abs(sa["rainy_days"] - sb["rainy_days"]) >= 3:
            notes.append(f"rainy days: {sa['rainy_days']} vs {sb['rainy_days']}")
        return {"period_a": f"{A[0]} to {A[1]}", "period_b": f"{B[0]} to {B[1]}",
                "avg_daily_upi_sales": [_r(sa["avg_daily_upi"]), _r(sb["avg_daily_upi"])],
                "change_pct": chg(sa["avg_daily_upi"], sb["avg_daily_upi"]),
                "drivers_pct_change": {k: v for k, v in drivers},
                "customers": dict(in_a=len(sa["payers"]), in_b=len(sb["payers"]), new_in_b=new, not_returning=lost),
                "context": notes}

    def detect_shifts(self, min_days=14):
        """Find lasting level shifts in each time slot (e.g. a competitor opening)."""
        d = self.daily
        ok = (~d.closed) & (d.phase == "classes")
        s = self.sales[self.sales.business_date.map(ok).fillna(False)]
        out = []
        for sl, (h0, h1) in SLOT_HOURS.items():
            ser = s[(s.hour >= h0) & (s.hour <= h1)].groupby("business_date").net_amount.sum()
            ser = ser.reindex(d.index[ok]).fillna(0)
            if len(ser) < 3 * min_days:
                continue
            best = None
            v = ser.values
            for k in range(min_days, len(v) - min_days):
                post = v[k:]
                if len(post) > 60:
                    continue                      # only look at the recent part of the year
                pre = v[max(0, k - 45):k]
                diff = post.mean() - pre.mean()
                se = math.sqrt(pre.var() / len(pre) + post.var() / len(post)) + 1e-9
                t = diff / se
                if best is None or abs(t) > abs(best[1]):
                    best = (ser.index[k], t, pre.mean(), post.mean())
            if best and abs(best[1]) > 4:
                out.append(dict(slot=sl, hours=f"{h0 % 24:02d}-{(h1 + 1) % 24:02d}h", since=str(best[0]),
                                before_per_day=_r(best[2]), after_per_day=_r(best[3]),
                                change_pct=_r((best[3] - best[2]) / best[2] * 100, 1), t_stat=_r(best[1], 1)))
        return {"shifts": out, "method": "largest mean shift on class days (t-stat > 4), recent 60 days"}

    def detect_outages(self, min_expected=8):
        """Hours with zero UPI payments when normally busy -> possible UPI downtime."""
        s = self.sales
        cnt = s.groupby(["business_date", "hour"]).size().unstack(fill_value=0)
        cnt = cnt.reindex(self.daily.index[~self.daily.closed]).fillna(0)
        phase = self.daily.phase.reindex(cnt.index)
        dow = pd.Series([x.weekday() for x in cnt.index], index=cnt.index)
        out = []
        for (ph, wd), g in cnt.groupby([phase.values, dow.values]):
            med = g.median()
            for day, row in g.iterrows():
                hrs = [h for h in row.index if row[h] == 0 and med[h] >= min_expected]
                if hrs:
                    out.append(dict(date=str(day), hours=[f"{h % 24:02d}:00" for h in hrs],
                                    expected_payments=_r(sum(med[h] for h in hrs))))
        return {"suspected_outages": sorted(out, key=lambda x: x["date"]),
                "note": "UPI payments stopped in normally busy hours: likely UPI/bank downtime, "
                        "sales probably shifted to cash or were lost."}

    # ------------------------------------------------------------------ customers
    def customer_insights(self, as_of=None, top=10):
        as_of = pd.to_datetime(as_of).date() if as_of else self.last
        s = self.sales[self.sales.business_date <= as_of]
        g = s.groupby("vpa").agg(name=("counterparty", "last"), visits=("net_amount", "size"),
                                 spend=("net_amount", "sum"), first=("business_date", "min"),
                                 last=("business_date", "max"), fav_hour=("hour", lambda x: x.mode().iat[0]))
        g["days_since"] = [(as_of - x).days for x in g["last"]]
        g["tenure_days"] = [(y - x).days + 1 for x, y in zip(g["first"], g["last"])]
        g["visits_per_week"] = g.visits / np.maximum(g.tenure_days, 7) * 7
        regular = (g.visits >= 20) & (g.visits_per_week >= 1.5)
        ph = self.daily.phase
        in_term = ph.get(as_of, "classes") in ("classes", "midsem", "fest")
        churn = g[regular & (g.days_since >= 21)] if in_term else g.iloc[0:0]
        new = g[g["first"] >= as_of - timedelta(days=30)]
        kh = self.tx[(self.tx["class"] == "khata_settlement") & (self.tx.business_date <= as_of)]
        khata = []
        for v, k in kh.groupby("vpa"):
            if len(k) < 2:
                continue
            span = (k.business_date.max() - k.business_date.min()).days
            rate = k.amount.iloc[1:].sum() / max(span, 1)
            since = (as_of - k.business_date.max()).days
            khata.append(dict(name=k.counterparty.iloc[-1], settlements=len(k), avg_settlement=_r(k.amount.mean()),
                              every_days=_r(span / (len(k) - 1)), last_paid=str(k.business_date.max()),
                              days_since_payment=since, est_outstanding=_r(rate * since)))
        khata.sort(key=lambda x: -(x["est_outstanding"] or 0))
        fmt = lambda df: [dict(name=r["name"], upi_id=vpa, visits=int(r.visits), spend=_r(r.spend), last_seen=str(r["last"]),
                               visits_per_week=_r(r.visits_per_week, 1)) for vpa, r in df.iterrows()]
        top_df = g.sort_values("spend", ascending=False).head(top)
        return {"as_of": str(as_of), "unique_upi_customers": int(len(g)),
                "regulars": int(regular.sum()),
                "regulars_share_of_upi_sales_pct": _r(g[regular].spend.sum() / g.spend.sum() * 100, 1),
                "top_customers": fmt(top_df), "new_customers_last_30d": int(len(new)),
                "regulars_not_seen_21d": fmt(churn.sort_values("spend", ascending=False).head(top)),
                "khata_accounts": khata[:top],
                "khata_total_est_outstanding": _r(sum(k["est_outstanding"] or 0 for k in khata)),
                "note": "Only UPI customers are visible. Customers are identified by UPI ID."}

    # ------------------------------------------------------------------ daily brief
    def daily_brief(self, day=None):
        day = pd.to_datetime(day).date() if day else self.last + timedelta(days=1)
        rev = self.forecast_revenue(days=7, start=day)
        prep = self.prep_plan(day)
        f = self._future_frame(10, day)
        hours = self.hourly_profile(days=28, phase=f.phase.iloc[0] if f.phase.iloc[0] in set(
            self.daily.phase) else None)
        alerts = []
        ph0 = f.phase.iloc[0]
        for r in f.itertuples():
            if r.phase != ph0:
                alerts.append(f"{r.period_label} starts {r.date} (in {(r.date - day).days} days)")
                break
        if f.closed.iloc[0]:
            alerts.append("Stall marked closed tomorrow")
        if "tmax" in f and f.tmax.iloc[0] >= 42:
            alerts.append("Very hot day expected: stock cold drinks/shikanji, fewer hot snacks after noon")
        shifts = self.detect_shifts()["shifts"]
        for s in shifts:
            alerts.append(f"{s['slot']} sales changed {s['change_pct']}% since {s['since']}")
        recent = self.units.tail(28).sum().sort_values(ascending=False).index[:8].tolist()
        top_items = sorted(self.forecast_items(recent, days=1, start=day)["forecasts"], key=lambda x: -x["p50"])[:6]
        return {"date": str(day), "period": f.period_label.iloc[0], "revenue_forecast": rev["days"][0],
                "week_total_p50": rev["total_p50"], "rush_hours": hours["busiest_hours"],
                "prep_list": prep["items"], "top_items": top_items, "alerts": alerts}

    def tool_names(self):
        return ["overview", "sales_mix", "hourly_profile", "combos", "forecast_revenue", "forecast_items",
                "prep_plan", "menu_matrix", "estimate_elasticity", "simulate_price", "simulate_hours",
                "compare_periods", "detect_shifts", "detect_outages", "customer_insights", "daily_brief"]


def default_analytics(**kw) -> StallAnalytics:
    raw = ROOT / "data" / "raw"
    stmt = next(raw.glob("Paytm*.xlsx"))
    return StallAnalytics(stmt, raw / "menu.csv", raw / "menu_price_history.csv",
                          raw / "campus_calendar.csv", raw / "weather_pilani.csv",
                          raw / "stall_closed_days.csv", **kw)
