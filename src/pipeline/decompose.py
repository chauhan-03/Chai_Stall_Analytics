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
MAX_CANDIDATES = 1_200_000   # memory guard: big menus enumerate baskets of fewer items
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


def remark_items(text, ids, aliases=None):
    """Items named in a payment remark. With owner keywords (menu 'aliases' column) the
    longest keyword wins, so 'chole samosa' is not also read as 'samosa'."""
    if not isinstance(text, str) or not text:
        return ()
    t = text.lower()
    if aliases is None:
        found = {iid for pat, iid in REMARK_MAP.items() if re.search(pat, t) and iid in ids}
        return tuple(sorted(found))
    found = set()
    for word, iid in sorted(((w.lower(), i) for i, ws in aliases.items() for w in ws if i in ids),
                            key=lambda x: -len(x[0])):
        pat = r"(?<!\w)" + re.escape(word) + r"(?!\w)"
        if re.search(pat, t):
            found.add(iid)
            t = re.sub(pat, " ", t)
    return tuple(sorted(found))


def basket_size_limit(n_items, cap=MAX_CANDIDATES):
    """Largest basket size (<= MAX_ITEMS) whose candidate count stays under the cap."""
    k, total = 0, 0
    for s in range(1, MAX_ITEMS + 1):
        total += math.comb(n_items + s - 1, s)
        if total > cap:
            break
        k = s
    return max(k, 2)


class Candidates:
    """All baskets of up to MAX_ITEMS items for one price vector, indexed by total."""

    def __init__(self, prices, max_items=MAX_ITEMS):
        avail = np.flatnonzero(~np.isnan(prices))
        n = len(prices)
        counts, totals, sizes = [], [], []
        for s in range(1, max_items + 1):
            combos = avail[np.array(list(itertools.combinations_with_replacement(range(len(avail)), s)),
                                    dtype=np.int64)]                    # same order as before, vectorised
            c = np.zeros((len(combos), n), dtype=np.int8)
            rows = np.arange(len(combos))
            for col in range(s):
                np.add.at(c, (rows, combos[:, col]), 1)
            counts.append(c); totals.append(prices[combos].sum(1)); sizes.append(np.full(len(combos), s))
        self.counts = np.vstack(counts)
        self.totals = np.concatenate(totals).round().astype(int)
        self.sizes = np.concatenate(sizes)
        self.logcoef = gammaln(self.sizes + 1) - gammaln(self.counts.astype(float) + 1).sum(1)
        order = np.argsort(self.totals, kind="stable")
        self.counts, self.totals, self.sizes, self.logcoef = (
            self.counts[order], self.totals[order], self.sizes[order], self.logcoef[order])
        self.prices = prices
        self.pair = np.zeros(len(self.counts), dtype=np.float32)

    def set_pairs(self, phi):
        if not np.any(phi):
            self.pair = np.zeros(len(self.counts), dtype=np.float32)
            return
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
        aliases = getattr(self.menu, "aliases", None)
        s["hint"] = s["remarks"].map(lambda t: remark_items(t, set(ids), aliases))
        reg_map, vecs = self.menu.regimes(s["business_date"])
        s["regime"] = s["business_date"].map(reg_map)
        self.max_items = K = basket_size_limit(n)
        self.cands = [Candidates(v, K) for v in vecs]
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
        pi = np.array([0.5, 0.27, 0.13, 0.07, 0.03])[:K]
        pi = pi / pi.sum()
        for it in range(self.n_iter):
            Ec = np.full((R, n_ctx, n), self.alpha / R)
            Es = np.full(K, 1.0)
            logt = np.log(theta).astype(np.float32)
            logpi = np.log(pi)
            fallback_mass = np.zeros((R, n_ctx, n))
            for regime, ctx, amt, idx, wt, bonus in G:
                cd = self.cands[regime]
                if len(idx) == 0:
                    # group orders beyond K items: spread by revenue-weighted mix
                    pr = np.nan_to_num(self.vecs[regime])
                    mix = theta[regime, ctx] * (pr > 0)
                    fallback_mass[regime, ctx] += wt * amt * mix / (mix * pr).sum()
                    continue
                cf = cd.counts[idx].astype(np.float32)
                lp = cf @ logt[regime, ctx] + cd.logcoef[idx] + logpi[cd.sizes[idx] - 1] + cd.pair[idx]
                if bonus is not None:
                    lp = lp + bonus
                post = np.exp(lp - logsumexp(lp))
                Ec[regime, ctx] += wt * (post @ cf)
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
        keep_pairs = n <= 40          # per-payment pair matrices (n x n each) are unused downstream
        for regime, ctx, amt, idx, wt, bonus in G:
            cd = self.cands[regime]
            if len(idx) == 0:
                pr = np.nan_to_num(self.vecs[regime])
                mix = theta[regime, ctx] * (pr > 0)
                e = amt * mix / (mix * pr).sum()
                pres = np.clip(e, 0, 1)
                res.append((e, np.zeros(n, np.int8), 0.0, True, np.outer(pres, pres) * 0 if keep_pairs else None))
                continue
            cf = cd.counts[idx].astype(np.float32)
            lp = cf @ logt[regime, ctx] + cd.logcoef[idx] + np.log(pi)[cd.sizes[idx] - 1] + cd.pair[idx]
            if bonus is not None:
                lp = lp + bonus
            post = np.exp(lp - logsumexp(lp))
            j = int(np.argmax(post))
            pairm = None
            if keep_pairs:
                pres = (cd.counts[idx] > 0).astype(np.float32)
                pairm = pres.T @ (post[:, None].astype(np.float32) * pres)   # E[i and j both in basket]
            res.append((post @ cf, cd.counts[idx[j]], float(post[j]), False, pairm))
        groups["gid"] = np.arange(len(groups))
        gid = s.merge(groups[["regime", "ctx", "amt", "hint", "gid"]],
                      on=["regime", "ctx", "amt", "hint"], how="left")["gid"].values
        E = np.vstack([res[g][0] for g in gid]).astype(np.float32)
        MAP = np.vstack([res[g][1] for g in gid])
        conf = np.array([res[g][2] for g in gid])
        approx = np.array([res[g][3] for g in gid])
        s["gid"] = gid
        self.pair_mats = np.stack([r[4] for r in res]).astype(np.float32) if keep_pairs else None
        exp_df = pd.DataFrame(E, columns=ids, index=s.index)
        map_df = pd.DataFrame(MAP, columns=ids, index=s.index)
        s["map_confidence"] = conf
        s["group_order_approx"] = approx
        s["map_basket"] = [", ".join(f"{q}x {self.menu.names[i]}" for i, q in zip(ids, row) if q)
                           if not a else f"group order (>{K} items)" for row, a in zip(MAP, approx)]
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
