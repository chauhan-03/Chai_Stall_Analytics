"""Quantile forecasting of daily revenue and item units.

Model: gradient-boosted trees (median / absolute-error loss) for P50; P10/P90
from split-conformal intervals (multiplicative residuals of rolling-origin
backtests), which gives honest out-of-sample uncertainty.
Features: weekday, academic phase, position inside the phase, weather,
closure flags, and a 'recent level' (trailing mean on normal class days,
which picks up slow shifts such as a competitor opening).
Fallback when history is short (< 90 days): weekday x phase averages.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

QUANTILES = (0.1, 0.5, 0.9)
PHASES = ["classes", "midsem", "compre", "compre_tail", "winter_break", "summer_break",
          "holi_break", "diwali_break", "fest", "orientation"]


def calendar_frame(dates, calendar: pd.DataFrame, closed: set) -> pd.DataFrame:
    cal = calendar.copy()
    cal["start"], cal["end"] = pd.to_datetime(cal["start"]), pd.to_datetime(cal["end"])
    rows = []
    for d in pd.to_datetime(pd.Series(dates)).sort_values():
        hit = cal[(cal.start <= d) & (cal.end >= d)]
        if len(hit):
            r = hit.iloc[0]
            ph, label, s, e = r.phase, r.label, r.start, r.end
        else:
            ph, label, s, e = "classes", "Classes (assumed)", d, d
        rows.append(dict(date=d.date(), phase=ph, period_label=label,
                         phase_day=(d - s).days, phase_left=(e - d).days,
                         phase_len=(e - s).days + 1, dow=d.weekday(), closed=d.date() in closed))
    f = pd.DataFrame(rows)
    # days until the next exam block (students study late before it)
    exam_starts = cal[cal.phase.isin(["midsem", "compre"])].start.dt.date.tolist()
    f["days_to_exam"] = [min([(x - d).days for x in exam_starts if x >= d] or [99]) for d in f.date]
    return f


def weather_frame(dates, weather: pd.DataFrame) -> pd.DataFrame:
    w = weather.copy()
    w["date"] = pd.to_datetime(w["date"]).dt.date
    clim = w.assign(m=pd.to_datetime(w["date"]).dt.month).groupby("m")[["tmax", "rain_mm"]].mean()
    out = []
    known = w.set_index("date")
    for d in dates:
        if d in known.index:
            r = known.loc[d]
            out.append(dict(date=d, tmax=r.tmax, rain_mm=r.rain_mm, heatwave=float(r.heatwave),
                            weather_source="observed"))
        else:   # beyond the data: monthly climatology (swap in a weather API here)
            m = pd.Timestamp(d).month
            out.append(dict(date=d, tmax=clim.loc[m, "tmax"], rain_mm=clim.loc[m, "rain_mm"],
                            heatwave=0.0, weather_source="climatology"))
    return pd.DataFrame(out)


def design(frame: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame(index=frame.index)
    for p in PHASES:
        X[f"ph_{p}"] = (frame.phase == p).astype(int)
    for k in range(7):
        X[f"dow_{k}"] = (frame.dow == k).astype(int)
    for c in ["phase_day", "phase_left", "phase_len", "days_to_exam", "tmax", "rain_mm", "heatwave"]:
        X[c] = frame[c].astype(float)
    X["closed"] = frame.closed.astype(int)
    X["level"] = frame["level"].astype(float)
    return X


def add_level(frame: pd.DataFrame, target: pd.Series, origin=None, window=28) -> pd.Series:
    """Trailing mean of the target over recent normal class days (as of the day before)."""
    s = pd.Series(np.asarray(target, float), index=pd.to_datetime(frame.date))
    normal = (frame.phase.values == "classes") & (~frame.closed.values)
    s_norm = s.where(normal)
    lvl = s_norm.rolling(f"{window * 2}D", min_periods=5).mean().shift(1)
    lvl = lvl.ffill().bfill()
    return lvl.values


class QuantileForecaster:
    def __init__(self, min_history=90, **gbm):
        self.min_history = min_history
        self.gbm = dict(max_iter=250, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=8,
                        l2_regularization=0.5)
        self.gbm.update(gbm)
        self.models = {}

    def fit(self, frame: pd.DataFrame, y: pd.Series):
        self.frame, self.y = frame.reset_index(drop=True), pd.Series(np.asarray(y, float))
        self.simple = len(frame) < self.min_history
        if self.simple:
            df = frame.assign(y=self.y.values)
            self.table = df[~df.closed].groupby(["phase", "dow"]).y.describe(percentiles=[.1, .5, .9])
            return self
        X = design(self.frame)
        open_ = ~self.frame.closed.values
        self.model = self._new().fit(X[open_], self.y[open_])
        # split-conformal widths: rolling-origin backtests, multiplicative residuals
        n = len(self.frame)
        ratios = []
        for cut in np.linspace(int(n * 0.55), n - 14, 6).astype(int):
            tr = np.arange(n) < cut
            te = (np.arange(n) >= cut) & (np.arange(n) < cut + 14)
            m = self._new().fit(X[tr & open_], self.y[tr & open_])
            yh = m.predict(X[te & open_])
            ratios.extend(((self.y[te & open_].values + 1) / (np.clip(yh, 0, None) + 1)).tolist())
        r = np.array(ratios)
        self.r_lo, self.r_hi = np.quantile(r, 0.1), np.quantile(r, 0.9)
        self.r_med = np.quantile(r, 0.5)
        return self

    def _new(self):
        return HistGradientBoostingRegressor(loss="absolute_error", random_state=0, **self.gbm)

    def predict(self, frame: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame({"date": frame.date.values})
        if self.simple:
            for q, col in zip(QUANTILES, ["p10", "p50", "p90"]):
                vals = []
                for r in frame.itertuples():
                    key = (r.phase, r.dow)
                    pct = {0.1: "10%", 0.5: "50%", 0.9: "90%"}[q]
                    vals.append(self.table.loc[key, pct] if key in self.table.index else self.y.median())
                out[col] = vals
        else:
            X = design(frame.reset_index(drop=True))
            yh = np.clip(self.model.predict(X), 0, None)
            out["p50"] = yh
            out["p10"] = (yh + 1) * self.r_lo - 1
            out["p90"] = (yh + 1) * self.r_hi - 1
        out[["p10", "p50", "p90"]] = np.sort(out[["p10", "p50", "p90"]].clip(lower=0).values, axis=1)
        out.loc[frame.closed.values, ["p10", "p50", "p90"]] = 0
        return out


def baseline_last_week(y: pd.Series, dates, horizon_dates):
    s = pd.Series(np.asarray(y, float), index=pd.to_datetime(dates))
    out = []
    for d in pd.to_datetime(horizon_dates):
        ref = d - pd.Timedelta(days=7)
        while ref not in s.index or ref >= pd.to_datetime(horizon_dates[0]):
            ref -= pd.Timedelta(days=7)
            if ref < s.index.min():
                break
        out.append(s.get(ref, s.median()))
    return np.array(out)


def pinball(y, q_pred, q):
    d = y - q_pred
    return np.mean(np.maximum(q * d, (q - 1) * d))
