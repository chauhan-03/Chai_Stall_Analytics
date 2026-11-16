"""Menu card + price history -> price/availability on any date."""
from datetime import date
import numpy as np
import pandas as pd


class Menu:
    def __init__(self, menu_csv, history_csv=None):
        self.menu = pd.read_csv(menu_csv)
        self.ids = list(self.menu.item_id)
        self.names = dict(zip(self.menu.item_id, self.menu.item))
        self.cost = dict(zip(self.menu.item_id, self.menu.cost))
        self.category = dict(zip(self.menu.item_id, self.menu.category))
        self.batch = dict(zip(self.menu.item_id, self.menu.made_in_batches))
        self.owner_estimate = (self.menu["owner_estimate_daily"].fillna(0).astype(float).values + 0.5
                               if "owner_estimate_daily" in self.menu else None)
        h = pd.read_csv(history_csv, parse_dates=["effective_date"]) if history_csv else pd.DataFrame(
            columns=["item_id", "effective_date", "event", "new_price", "old_price"])
        self.hist = h.sort_values("effective_date")

    def prices_on(self, d) -> np.ndarray:
        """Vector of prices (NaN = not on the menu yet)."""
        d = pd.Timestamp(d)
        out = []
        for iid, p_now in zip(self.menu.item_id, self.menu.price):
            h = self.hist[self.hist.item_id == iid]
            launch = h[h.event == "launch"]
            if len(launch) and d < launch.effective_date.min():
                out.append(np.nan); continue
            ch = h[h.event == "price_change"]
            p = p_now
            for r in ch.sort_values("effective_date", ascending=False).itertuples():
                if d < r.effective_date:
                    p = r.old_price
            out.append(float(p))
        return np.array(out)

    def regimes(self, dates):
        """Map each date to a price regime id; returns (date->regime, list of price vectors)."""
        vecs, mapping = [], {}
        for d in sorted(set(dates)):
            v = tuple(np.nan_to_num(self.prices_on(d), nan=-1))
            if v not in vecs:
                vecs.append(v)
            mapping[d] = vecs.index(v)
        return mapping, [np.where(np.array(v) < 0, np.nan, np.array(v)) for v in vecs]
