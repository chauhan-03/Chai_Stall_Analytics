"""Synthetic daily weather for Pilani (semi-arid, BSh).

Climatology targets (approx, from IMD/climate-data summaries):
  Jan  max ~20C, min ~5C (cold waves, morning fog)
  May-Jun max 40-42C, heatwave spikes 45-47C
  Jul-Sep monsoon: ~35-45% rain days, most rain in July
  Nov  driest month
"""
import math
import numpy as np
import pandas as pd

# monthly mean daily max / min (C), rain-day probability, mean mm on a rain day
CLIMATE = {
    1: (20.5, 5.5, 0.06, 6),  2: (24.0, 8.5, 0.06, 6),  3: (30.5, 14.0, 0.06, 5),
    4: (37.0, 20.0, 0.05, 5), 5: (41.0, 25.5, 0.08, 7), 6: (40.5, 28.0, 0.18, 12),
    7: (35.5, 27.0, 0.42, 16),8: (34.0, 26.0, 0.40, 14),9: (34.5, 24.0, 0.22, 12),
    10: (33.5, 18.5, 0.04, 5), 11: (28.5, 11.5, 0.02, 3), 12: (23.0, 6.5, 0.04, 4),
}


def make_weather(start, end, rng: np.random.Generator) -> pd.DataFrame:
    days = pd.date_range(start, end, freq="D")
    rows, anomaly = [], 0.0
    for d in days:
        m = d.month
        # interpolate climatology between months for smooth seasons
        nxt = m % 12 + 1
        frac = (d.day - 15) / 30.0
        a, b = CLIMATE[m], CLIMATE[nxt] if frac > 0 else CLIMATE[(m - 2) % 12 + 1]
        w = abs(frac)
        tmax_c = a[0] * (1 - w) + b[0] * w
        tmin_c = a[1] * (1 - w) + b[1] * w
        anomaly = 0.75 * anomaly + rng.normal(0, 1.6)   # AR(1) weather spells
        tmax = tmax_c + anomaly
        tmin = tmin_c + 0.7 * anomaly + rng.normal(0, 0.8)
        # heatwave spells in May-June
        if m in (5, 6) and rng.random() < 0.10:
            tmax += rng.uniform(3, 6)
        # cold wave in late Dec - Jan
        if (m == 1 or (m == 12 and d.day > 20)) and rng.random() < 0.12:
            tmax -= rng.uniform(3, 6); tmin -= rng.uniform(2, 4)
        rain_p = a[2] * (1 - w) + b[2] * w
        rain = 0.0
        if rng.random() < rain_p:
            rain = float(rng.gamma(1.2, (a[3])))
            tmax -= min(6, rain / 4)
        fog = bool((m in (12, 1)) and tmin < 6 and rng.random() < 0.45)
        rows.append({
            "date": d.date(), "tmax": round(tmax, 1), "tmin": round(min(tmin, tmax - 4), 1),
            "rain_mm": round(rain, 1), "heatwave": bool(tmax >= 44.0),
            "cold_wave": bool(tmin <= 4.0), "fog_morning": fog,
        })
    return pd.DataFrame(rows)
