"""Basket decomposition: infer which items each UPI payment bought.

Model (fitted with EM, no labels needed):
  context c   = time slot (morning/midday/evening/night/late) x weather band (cold/mild/hot)
  basket size s ~ Categorical(pi)
  items       ~ Multinomial(s, theta_c)
  P(basket | amount) is proportional to P(s) * multinomial(n | s, theta_c),
  restricted to baskets whose price total equals the payment
  (prices as on that date). A customer remark naming items ("2 samose")
  up-weights baskets containing them.

E-step: posterior over all candidate baskets for each (regime, context, amount).
M-step: theta_c = expected item counts, pi = expected sizes.
"""
import itertools
import math
import re
import numpy as np
import pandas as pd
from scipy.special import gammaln, logsumexp

MAX_ITEMS = 5
SLOTS = ["morning", "midday", "evening", "night", "late"]
BANDS = ["cold", "mild", "hot"]
REMARK_MAP = {
    r"cutting": "CUT_CHAI", r"masala chai|(?<!adrak )(?<!kulhad )(?<!cutting )\bchai\b(?! samosa)|\btea\b": "MASALA_CHAI", r"adrak": "ADRAK_CHAI",
    r"kulhad": "KULHAD_CHAI", r"cold coffee": "COLD_COFFEE", r"(?<!cold )coffee": "HOT_COFFEE",
    r"lassi": "LASSI", r"shikanji|nimbu": "SHIKANJI", r"coke|cold drink|thums": "COLD_DRINK",
    r"water|paani": "WATER", r"(?<!chai )samos": "SAMOSA", r"kachori": "KACHORI", r"mirchi": "MIRCHI_BADA",
    r"bread pakoda": "BREAD_PAKODA", r"poha": "POHA", r"paratha": "PARATHA", r"bun": "BUN_MASKA",
    r"cheese maggi": "CHEESE_MAGGI", r"masala maggi": "MASALA_MAGGI", r"(?<!cheese )(?<!masala )maggi": "MAGGI",
    r"grilled": "GRILL_SANDWICH", r"(?<!grilled )sandwich": "VEG_SANDWICH", r"omelette": "BREAD_OMELETTE",
    r"biscuit": "BISCUIT", r"chips|lays": "CHIPS", r"combo|chai samosa": "COMBO_CS",
}


def slot_of(h):
    return 0 if h <= 10 else 1 if h <= 15 else 2 if h <= 19 else 3 if h <= 23 else 4


def band_of(tmax):
    return 0 if tmax < 24 else (2 if tmax > 34 else 1)


def remark_items(text, ids):
    if not isinstance(text, str) or not text:
        return ()
    t = text.lower()
    found = {iid for pat, iid in REMARK_MAP.items() if re.search(pat, t) and iid in ids}
    return tuple(sorted(found))


class Candidates:
    """All baskets of up to MAX_ITEMS items for one price vector, indexed by total."""

    def __init__(self, prices):
        avail = np.flatnonzero(~np.isnan(prices))
        n = len(prices)
        rows, totals, sizes = [], [], []
        for s in range(1, MAX_ITEMS + 1):
            for combo in itertools.combinations_with_replacement(avail, s):
                v = np.zeros(n, dtype=np.int8)
                for i in combo:
                    v[i] += 1
                rows.append(v); totals.append(prices[list(combo)].sum()); sizes.append(s)
        self.counts = np.array(rows)
        self.totals = np.array(totals).round().astype(int)
        self.sizes = np.array(sizes)
        self.logcoef = gammaln(self.sizes + 1) - gammaln(self.counts.astype(float) + 1).sum(1)
        order = np.argsort(self.totals, kind="stable")
        self.counts, self.totals, self.sizes, self.logcoef = (
            self.counts[order], self.totals[order], self.sizes[order], self.logcoef[order])
        self.counts_f = self.counts.astype(np.float32)
        self.prices = prices
        self.pair = np.zeros(len(self.counts), dtype=np.float32)

    def set_pairs(self, phi):
        pres = (self.counts > 0).astype(np.float32)
        self.pair = 0.5 * ((pres @ phi.astype(np.float32)) * pres).sum(1)

    def for_amount(self, a):
        lo, hi = np.searchsorted(self.totals, a, "left"), np.searchsorted(self.totals, a, "right")
        return slice(lo, hi)


class BasketDecomposer:
    def __init__(self, menu, n_iter=40, alpha=0.5, use_owner_prior=True, prior_strength=0.5,
                 use_pairs=False, kappa=150.0):
        self.menu, self.n_iter, self.alpha = menu, n_iter, alpha
        self.use_owner_prior, self.prior_strength = use_owner_prior, prior_strength
        self.use_pairs, self.kappa = use_pairs, kappa
        self.ids = menu.ids

    def fit_transform(self, sales: pd.DataFrame, weather: pd.DataFrame) -> dict:
        ids, n = self.ids, len(self.ids)
        s = sales.copy()
        w = weather.assign(date=pd.to_datetime(weather["date"]).dt.date).set_index("date")["tmax"]
        s["slot"] = s["hour"].map(slot_of)
        s["band"] = s["business_date"].map(w).fillna(30).map(band_of)
        s["ctx"] = s["slot"] * 3 + s["band"]
        s["amt"] = s["net_amount"].round().astype(int)
        s["hint"] = s["remarks"].map(lambda t: remark_items(t, set(ids)))
        reg_map, vecs = self.menu.regimes(s["business_date"])
        s["regime"] = s["business_date"].map(reg_map)
        self.cands = [Candidates(v) for v in vecs]
        self.vecs = vecs

        self.phi = self.pair_affinity(s["hint"], ids) if self.use_pairs else np.zeros((n, n))
        for cd in self.cands:
            cd.set_pairs(self.phi)

        groups = s.groupby(["regime", "ctx", "amt", "hint"]).size().rename("w").reset_index()
        G = []
        for g in groups.itertuples():
            cd = self.cands[g.regime]
            sl = cd.for_amount(g.amt)
            idx = np.arange(sl.start, sl.stop)
            bonus = None
            if g.hint and len(idx):
                hint_idx = [ids.index(h) for h in g.hint]
                has = (cd.counts[idx][:, hint_idx] > 0).sum(1)
                bonus = np.log(1 + 20 * has / len(hint_idx)).astype(np.float32)
            G.append((g.regime, g.ctx, g.amt, idx, g.w, bonus))

        # ---- priors: (a) items customers named in remarks, (b) owner's gut estimate
        n_ctx = len(SLOTS) * len(BANDS)
        hint_ctx = np.full((n_ctx, n), 0.5)
        for h, c in zip(s["hint"], s["ctx"]):
            for iid in h:
                hint_ctx[c, ids.index(iid)] += 1
        hint_glob = hint_ctx.sum(0) / hint_ctx.sum()
        prior_glob = hint_glob
        owner = getattr(self.menu, "owner_estimate", None)
        if self.use_owner_prior and owner is not None:
            prior_glob = owner / owner.sum()
        self.prior_used = "owner_estimate" if (self.use_owner_prior and owner is not None) else "remarks"
        n_per_ctx = np.bincount(s["ctx"], minlength=n_ctx).astype(float)
        # init: context pattern from remarks, level from the global prior
        init = (hint_ctx / hint_ctx.sum(1, keepdims=True)) * 0.5 + prior_glob * 0.5
        R = len(vecs)
        theta = np.repeat((init / init.sum(1, keepdims=True))[None], R, axis=0)   # regime x ctx x item
        prior_counts = self.prior_strength * n_per_ctx[:, None] * 1.6 * prior_glob[None, :]
        n_rc = np.zeros((R, n_ctx))
        np.add.at(n_rc, (s["regime"].values, s["ctx"].values), 1)
        prior_rc = self.prior_strength * n_rc[:, :, None] * 1.6 * prior_glob[None, None, :]
        pi = np.array([0.5, 0.27, 0.13, 0.07, 0.03])
        for it in range(self.n_iter):
            Ec = np.full((R, n_ctx, n), self.alpha / R)
            Es = np.full(MAX_ITEMS, 1.0)
            logt = np.log(theta).astype(np.float32)
            logpi = np.log(pi)
            fallback_mass = np.zeros((R, n_ctx, n))
            for regime, ctx, amt, idx, wt, bonus in G:
                cd = self.cands[regime]
                if len(idx) == 0:
                    # group orders beyond 5 items: spread by revenue-weighted mix
                    pr = np.nan_to_num(self.vecs[regime])
                    mix = theta[regime, ctx] * (pr > 0)
                    fallback_mass[regime, ctx] += wt * amt * mix / (mix * pr).sum()
                    continue
                lp = cd.counts_f[idx] @ logt[regime, ctx] + cd.logcoef[idx] + logpi[cd.sizes[idx] - 1] + cd.pair[idx]
                if bonus is not None:
                    lp = lp + bonus
                post = np.exp(lp - logsumexp(lp))
                Ec[regime, ctx] += wt * (post @ cd.counts_f[idx])
                np.add.at(Es, cd.sizes[idx] - 1, wt * post)
            Ec += fallback_mass
            # hierarchical: each price period shrinks toward the all-year pattern,
            # so a price change can move an item's share without overfitting
            glob = Ec.sum(0) + prior_counts
            glob = glob / glob.sum(1, keepdims=True)
            avail = np.array([~np.isnan(v) for v in vecs])[:, None, :]
            new_theta = (Ec + prior_rc + self.kappa * glob[None]) * avail + 1e-9
            new_theta = new_theta / new_theta.sum(2, keepdims=True)
            delta = np.abs(new_theta - theta).max()
            theta, pi = new_theta, Es / Es.sum()
            if delta < 1e-5:
                break
        self.theta, self.pi = theta, pi
        self.theta_global = glob

        # ---- final posterior per group -> per transaction
        logt = np.log(theta).astype(np.float32)
        res = []
        for regime, ctx, amt, idx, wt, bonus in G:
            cd = self.cands[regime]
            if len(idx) == 0:
                pr = np.nan_to_num(self.vecs[regime])
                mix = theta[regime, ctx] * (pr > 0)
                e = amt * mix / (mix * pr).sum()
                pres = np.clip(e, 0, 1)
                res.append((e, np.zeros(n, np.int8), 0.0, True, np.outer(pres, pres) * 0))
                continue
            lp = cd.counts_f[idx] @ logt[regime, ctx] + cd.logcoef[idx] + np.log(pi)[cd.sizes[idx] - 1] + cd.pair[idx]
            if bonus is not None:
                lp = lp + bonus
            post = np.exp(lp - logsumexp(lp))
            j = int(np.argmax(post))
            pres = (cd.counts[idx] > 0).astype(np.float32)
            pairm = pres.T @ (post[:, None].astype(np.float32) * pres)   # E[i and j both in basket]
            res.append((post @ cd.counts_f[idx], cd.counts[idx[j]], float(post[j]), False, pairm))
        groups["gid"] = np.arange(len(groups))
        gid = s.merge(groups[["regime", "ctx", "amt", "hint", "gid"]],
                      on=["regime", "ctx", "amt", "hint"], how="left")["gid"].values
        E = np.vstack([res[g][0] for g in gid]).astype(np.float32)
        MAP = np.vstack([res[g][1] for g in gid])
        conf = np.array([res[g][2] for g in gid])
        approx = np.array([res[g][3] for g in gid])
        s["gid"] = gid
        self.pair_mats = np.stack([r[4] for r in res]).astype(np.float32)
        exp_df = pd.DataFrame(E, columns=ids, index=s.index)
        map_df = pd.DataFrame(MAP, columns=ids, index=s.index)
        s["map_confidence"] = conf
        s["group_order_approx"] = approx
        s["map_basket"] = [", ".join(f"{q}x {self.menu.names[i]}" for i, q in zip(ids, row) if q)
                           if not a else "group order (>5 items)" for row, a in zip(MAP, approx)]
        return dict(tx=s, expected=exp_df, map=map_df, theta=theta, pi=pi, pair_mats=self.pair_mats)

    @staticmethod
    def pair_affinity(hints, ids, shrink=5.0, cap=2.5):
        """phi_ij = shrunk log-lift of items i,j named together in customer remarks."""
        n = len(ids)
        multi = [h for h in hints if len(h) >= 2]
        if len(multi) < 30:
            return np.zeros((n, n))
        # lift measured inside multi-item remarks only, so independent pairs -> 0
        cnt = np.zeros(n); pair = np.zeros((n, n)); n_pairs = 0
        for h in multi:
            for a in h:
                cnt[ids.index(a)] += 1
            for x in range(len(h)):
                for y in range(x + 1, len(h)):
                    i, j = ids.index(h[x]), ids.index(h[y])
                    pair[i, j] += 1; pair[j, i] += 1; n_pairs += 1
        p_item = cnt / cnt.sum()
        expected = 2 * n_pairs * np.outer(p_item, p_item)
        phi = np.clip(np.log((pair + shrink * 0.5) / (expected + shrink * 0.5)), -cap, cap)
        phi -= phi[np.triu_indices(n, 1)].mean()      # centred: no bonus for size itself
        np.fill_diagonal(phi, 0)
        return phi

    def theta_table(self):
        idx = pd.MultiIndex.from_product([SLOTS, BANDS], names=["slot", "weather"])
        return pd.DataFrame(self.theta_global, index=idx, columns=self.ids)
