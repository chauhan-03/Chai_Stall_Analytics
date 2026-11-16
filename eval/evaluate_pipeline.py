"""Score every pipeline stage against the synthetic answer key.

    python -m eval.evaluate_pipeline            # writes eval/report.md + eval/metrics.json
"""
import json
import math
import sys
import warnings
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.pipeline.analytics import default_analytics  # noqa: E402
from src.pipeline.forecast import QuantileForecaster, add_level, baseline_last_week, pinball  # noqa: E402

KEY = ROOT / "data" / "answer_key"
CUTOFF = date(2026, 10, 4)          # train up to here, test the last 6 weeks
M = {}
lines = []


def h(t): lines.append(f"\n## {t}\n")
def p(t=""): lines.append(t)


def table(df):
    p(df.to_markdown(index=True) if hasattr(df, "to_markdown") else df.to_string())


def main(use_owner_prior=True):
    A = default_analytics(use_owner_prior=use_owner_prior)
    orders = pd.read_csv(KEY / "orders.csv", parse_dates=["datetime"])
    orders["date"] = pd.to_datetime(orders["date"]).dt.date
    oi = pd.read_csv(KEY / "order_items.csv")
    daily = pd.read_csv(KEY / "daily_truth.csv")
    daily["date"] = pd.to_datetime(daily["date"]).dt.date
    daily = daily.set_index("date")
    labels = pd.read_csv(KEY / "statement_row_labels.csv", dtype={"upi_ref": str})
    truth = json.loads((KEY / "truth_parameters.json").read_text())

    # ---------------------------------------------------------------- 1 ingest
    h("1. Statement row classification")
    m = A.tx.merge(labels[["upi_ref", "true_type"]], left_on="ref", right_on="upi_ref", how="left")
    norm = (m.true_type.str.replace(r"^expense_.*", "expense", regex=True)
            .replace({"sale_deferred": "sale", "sale_typo": "sale", "personal_family": "personal_sent",
                      "personal_recharge": "personal_sent", "cashback": "other"}))
    acc = float((norm == m["class"]).mean())
    sale_mask_t, sale_mask_p = norm == "sale", m["class"] == "sale"
    prec = float((sale_mask_t & sale_mask_p).sum() / sale_mask_p.sum())
    rec = float((sale_mask_t & sale_mask_p).sum() / sale_mask_t.sum())
    M["classification"] = dict(accuracy=acc, sale_precision=prec, sale_recall=rec)
    p(f"Rows: {len(m):,}. Accuracy **{acc:.2%}**; sale precision {prec:.2%}, recall {rec:.2%}.")
    ct = pd.crosstab(norm.rename("truth"), m["class"].rename("predicted"))
    table(ct)

    # ---------------------------------------------------------------- 2 revenue
    h("2. Revenue reconstruction (UPI only -> all modes)")
    true_rev = daily.upi_sales + daily.cash_sales + orders[orders["mode"] == "khata"].groupby("date").amount.sum(
    ).reindex(daily.index).fillna(0)
    est = A.daily.revenue_est.reindex(daily.index).fillna(0)
    lo = A.daily.revenue_high.reindex(daily.index).fillna(0)   # note: high cash share -> more revenue
    hi = A.daily.revenue_low.reindex(daily.index).fillna(0)
    true_cash = daily.cash_sales.sum() / (daily.upi_sales.sum() + daily.cash_sales.sum())
    upi_err = abs(A.daily.upi_sales.sum() - daily.upi_sales.sum()) / daily.upi_sales.sum()
    tot_err = (est.sum() - true_rev.sum()) / true_rev.sum()
    open_ = true_rev > 0
    wape_daily = float((est[open_] - true_rev[open_]).abs().sum() / true_rev[open_].sum())
    inside = float(((true_rev >= np.minimum(lo, hi)) & (true_rev <= np.maximum(lo, hi)))[open_].mean())
    M["revenue"] = dict(true_cash_share=true_cash, assumed=A.cash_share, upi_sales_error=upi_err,
                        total_revenue_error=tot_err, daily_wape=wape_daily, days_within_range=inside)
    p(f"- UPI sales recovered from the statement: error {upi_err:.2%}")
    p(f"- True cash share {true_cash:.1%} vs assumed {A.cash_share:.0%} (range {A.cash_range})")
    p(f"- Total revenue: estimated ₹{est.sum():,.0f} vs true ₹{true_rev.sum():,.0f} ({tot_err:+.1%})")
    p(f"- Daily revenue WAPE {wape_daily:.1%}; true value inside the cash-share range on {inside:.0%} of days")

    # ---------------------------------------------------------------- 3 decomposition
    h("3. Basket decomposition (which items were sold)")
    tr_basket = oi.pivot_table(index="order_id", columns="item_id", values="qty", aggfunc="sum", fill_value=0)
    lab = A.sales.merge(labels[["upi_ref", "order_id", "true_type"]], left_on="ref", right_on="upi_ref", how="left")
    ok = lab.true_type.isin(["sale", "sale_deferred"]).values & lab.order_id.notna().values
    T = tr_basket.reindex(lab.order_id[ok]).fillna(0).reindex(columns=A.ids, fill_value=0).values
    MAP = A.map.values[ok]
    exact = float((MAP == T).all(1).mean())
    conf = A.sales.map_confidence.values[ok]
    hi_conf = conf >= 0.6
    exact_hi = float((MAP[hi_conf] == T[hi_conf]).all(1).mean()) if hi_conf.any() else float("nan")
    # item mix: all modes truth vs scaled estimate
    true_units = oi.merge(orders[["order_id", "date"]], on="order_id").groupby(["date", "item_id"]).qty.sum(
    ).unstack(fill_value=0).reindex(columns=A.ids, fill_value=0)
    est_units = A.units.reindex(true_units.index).fillna(0)
    tot_t, tot_e = true_units.sum(), est_units.sum()
    mix_wape = float((tot_e - tot_t).abs().sum() / tot_t.sum())
    share_t, share_e = tot_t / tot_t.sum(), tot_e / tot_e.sum()
    share_mae = float((share_e - share_t).abs().mean() * 100)
    per_item = pd.DataFrame({"true_units": tot_t.round(0).values, "estimated": tot_e.round(0).values,
                             "error_%": ((tot_e - tot_t) / tot_t * 100).round(1).values,
                             "daily_corr": [np.corrcoef(est_units[i], true_units[i])[0, 1].round(3) for i in A.ids]},
                            index=[A.menu.names[i] for i in A.ids]).sort_values("true_units", ascending=False)
    rank_corr = float(pd.Series(tot_t.values).corr(pd.Series(tot_e.values), method="spearman"))
    M["decomposition"] = dict(exact_basket_accuracy=exact, exact_accuracy_conf_ge_0_6=exact_hi,
                              share_conf_ge_0_6=float(hi_conf.mean()), item_total_wape=mix_wape,
                              item_share_mae_pp=share_mae, popularity_rank_spearman=rank_corr,
                              prior=A.prior_used)
    p(f"- Exact basket correct: **{exact:.1%}** of payments ({exact_hi:.1%} when model confidence ≥ 60%, "
      f"which is {hi_conf.mean():.0%} of payments)")
    p(f"- Item totals WAPE **{mix_wape:.1%}**; mean absolute error in item share {share_mae:.2f} pp; "
      f"popularity rank correlation {rank_corr:.2f}")
    p(f"- Prior used: {A.prior_used}")
    table(per_item)

    # ---------------------------------------------------------------- 4 combos
    h("4. Combos (association rules)")
    tb = (tr_basket > 0).astype(int)
    n = len(tb)
    sup = tb.mean()
    true_pairs = []
    cols = tb.columns
    X = tb.values.astype(np.float32)
    co = X.T @ X / n
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            if co[i, j] >= 0.004:
                true_pairs.append((frozenset((cols[i], cols[j])), co[i, j] / (sup.iloc[i] * sup.iloc[j]), co[i, j]))
    true_pairs.sort(key=lambda x: -x[1] * math.log1p(x[2] * 1000))
    true_top = [tp[0] for tp in true_pairs[:10]]
    found = A.combos()["rules"]
    name2id = {v: k for k, v in A.menu.names.items()}
    found_sets = [frozenset((name2id[r["if_buys"]], name2id[r["also_buys"]])) for r in found]
    true_lift = {tp[0]: tp[1] for tp in true_pairs}
    hits = [f for f in found_sets if f in true_lift and true_lift[f] > 1.3]
    precision = len(hits) / max(len(found_sets), 1)
    recall = len(set(found_sets) & set(true_top)) / len(true_top)
    M["combos"] = dict(precision_vs_true_lift_gt_1_3=precision, recall_of_true_top10=recall)
    p(f"- Rules reported: {len(found_sets)}; **{precision:.0%}** are real associations (true lift > 1.3)")
    p(f"- Recall of the 10 strongest true pairs: {recall:.0%}")
    p("\nTrue top pairs (from the answer key):")
    for tp in true_pairs[:10]:
        a_, b_ = sorted(tp[0])
        p(f"- {A.menu.names[a_]} + {A.menu.names[b_]}: lift {tp[1]:.2f}, in {tp[2]*100:.1f}% of orders")
    p("\nRules found by the pipeline:")
    for r in found:
        p(f"- {r['if_buys']} → {r['also_buys']}: lift {r['lift']}, seen {r['times_seen']}×")

    # ---------------------------------------------------------------- 5 forecast backtest
    h(f"5. Forecast backtest (train ≤ {CUTOFF}, test {CUTOFF + timedelta(days=1)} → {A.last})")
    fr = A.frame.copy()
    y = A.daily.upi_sales.values
    fr["level"] = add_level(fr, y)
    train = (fr.date <= CUTOFF).values
    test = ~train & ~fr.closed.values
    model = QuantileForecaster().fit(fr[train].reset_index(drop=True), y[train])
    te = fr[~train].copy(); te["level"] = fr.loc[train, "level"].iloc[-1]
    pred = model.predict(te.reset_index(drop=True))
    yt = daily.upi_sales.reindex(te.date).values
    open_te = ~te.closed.values
    base = baseline_last_week(y, fr.date, list(te.date))
    def wape(a, b): return float(np.abs(a - b).sum() / np.abs(b).sum())
    w_model, w_base = wape(pred.p50.values[open_te], yt[open_te]), wape(base[open_te], yt[open_te])
    cov = float(((yt >= pred.p10.values) & (yt <= pred.p90.values))[open_te].mean())
    pin = np.mean([pinball(yt[open_te], pred[c].values[open_te], q) for c, q in
                   (("p10", .1), ("p50", .5), ("p90", .9))])
    M["forecast_revenue"] = dict(wape_model=w_model, wape_last_week=w_base, p10_p90_coverage=cov, pinball=pin)
    p(f"- Daily UPI sales WAPE: model **{w_model:.1%}** vs same-weekday-last-week {w_base:.1%}")
    p(f"- P10–P90 interval contains the truth on {cov:.0%} of days (target 80%)")
    p("- Test window includes mid-sems, Oasis, Diwali break and the competitor effect.")
    bt = pd.DataFrame({"date": te.date.values, "period": te.period_label.values, "true_upi": yt,
                       "p10": pred.p10.round(0), "p50": pred.p50.round(0), "p90": pred.p90.round(0),
                       "last_week": base.round(0)})
    bt["phase"] = te.phase.values
    agg = bt[open_te].groupby("phase")[["true_upi", "p50", "last_week"]].mean().round(0)
    table(agg)

    # ---------------------------------------------------------------- 6 newsvendor
    h("6. Prep plan (newsvendor) vs the owner's habit, same test window")
    res, sens = [], {}
    for iid in [i for i in A.ids if A.menu.batch.get(i) and i != "COMBO_CS"]:
        yi = A.units[iid].values.copy()
        if iid == "SAMOSA":
            yi = yi + A.units["COMBO_CS"].values
        fr_i = A.frame.copy(); fr_i["level"] = add_level(fr_i, yi)
        mdl = QuantileForecaster().fit(fr_i[train].reset_index(drop=True), yi[train])
        te_i = fr_i[~train].copy(); te_i["level"] = fr_i.loc[train, "level"].iloc[-1]
        pr = mdl.predict(te_i.reset_index(drop=True))
        price, cost = A._price(iid), A.menu.cost[iid]
        cu, co_ = price - cost, cost
        cr = cu / (cu + co_)
        q = np.array([A._quantile(a, b, c, cr) for a, b, c in zip(pr.p10, pr.p50, pr.p90)])
        bs = 10 if iid in ("SAMOSA", "KACHORI") else 5
        q = np.ceil(np.clip(q, 0, None) / bs) * bs
        D = daily[f"demand_{iid}"].reindex(te_i.date).values.astype(float)
        if iid == "SAMOSA":
            D = D + daily["demand_COMBO_CS"].reindex(te_i.date).values
        owner = daily[f"prepared_{iid}"].reindex(te_i.date).values.astype(float)
        op = ~te_i.closed.values
        def outcome(qq):
            sold = np.minimum(qq, D)
            return dict(profit=float((price * sold - cost * qq)[op].sum()), waste=float((qq - sold)[op].sum()),
                        lost=float((D - sold)[op].sum()), stockout_days=int(((D > qq) & op).sum()))
        o_m, o_o = outcome(q), outcome(owner)
        for k in (1.1, 1.2, 1.3, 1.4):
            sens.setdefault(k, 0.0)
            sens[k] += outcome(np.ceil(q * k / bs) * bs)["profit"]
        res.append(dict(item=A.menu.names[iid], owner_profit=o_o["profit"], model_profit=o_m["profit"],
                        owner_waste=o_o["waste"], model_waste=o_m["waste"], owner_lost=o_o["lost"],
                        model_lost=o_m["lost"], owner_stockout_days=o_o["stockout_days"],
                        model_stockout_days=o_m["stockout_days"]))
    nv = pd.DataFrame(res).set_index("item")
    gain = nv.model_profit.sum() - nv.owner_profit.sum()
    M["newsvendor"] = dict(profit_gain=float(gain), owner_profit=float(nv.owner_profit.sum()),
                           waste_owner=float(nv.owner_waste.sum()), waste_model=float(nv.model_waste.sum()),
                           lost_owner=float(nv.owner_lost.sum()), lost_model=float(nv.model_lost.sum()))
    p(f"- Batch-item profit over the test window: model ₹{nv.model_profit.sum():,.0f} vs owner "
      f"₹{nv.owner_profit.sum():,.0f} (**{gain:+,.0f}**)")
    p(f"- Units wasted: {nv.owner_waste.sum():,.0f} → {nv.model_waste.sum():,.0f}; "
      f"demand lost to stockouts: {nv.owner_lost.sum():,.0f} → {nv.model_lost.sum():,.0f}")
    table(nv.round(0))
    M["newsvendor"]["safety_factor_sensitivity"] = {str(k): v for k, v in sens.items()}
    p("\nSensitivity (NOT tuned, shown to explain the under-prep bias): multiply the recommendation by k")
    for k, v in sens.items():
        p(f"- k={k}: profit ₹{v:,.0f} ({v - nv.owner_profit.sum():+,.0f} vs owner)")
    p("\nWhy: amounts alone under-count cheap fried items (see section 3), and sell-out days hide true "
      "demand. A one-tap 'sold out at hh:mm' log from the owner would let the model correct this.")

    # ---------------------------------------------------------------- 7 elasticity
    h("7. Price elasticity")
    rows = []
    for iid in ["MAGGI", "MASALA_MAGGI", "KULHAD_CHAI"]:
        e = A.estimate_elasticity(iid)
        true_e = truth["elasticity"]["maggi" if "MAGGI" in iid else "default"]
        rows.append(dict(item=A.menu.names[iid], true=true_e, estimate=e["elasticity"], ci90=str(e["ci90"]),
                         reliable=e["reliable"], note=e["reliability_note"]))
    el = pd.DataFrame(rows).set_index("item")
    M["elasticity"] = el.reset_index().to_dict("records")
    table(el)

    # ---------------------------------------------------------------- 8 diagnostics
    h("8. Diagnostics: competitor shift, UPI outages")
    sh = A.detect_shifts()["shifts"]
    outs = A.detect_outages()["suspected_outages"]
    true_out = {o[0] for o in truth["upi_outages"]}
    found_out = {o["date"] for o in outs}
    M["diagnostics"] = dict(shifts=sh, outage_recall=len(true_out & found_out) / len(true_out),
                            outage_precision=len(true_out & found_out) / max(len(found_out), 1))
    p(f"- Competitor truly opened {truth['competitor_open']} (night demand x{truth['competitor_effect']['night']}).")
    for s_ in sh:
        p(f"  - Detected: {s_['slot']} sales {s_['change_pct']}% since {s_['since']} (t={s_['t_stat']})")
    p(f"- UPI outages: found {len(true_out & found_out)}/{len(true_out)}; "
      f"{len(found_out - true_out)} false alarms ({sorted(found_out - true_out)})")

    # ---------------------------------------------------------------- 9 khata
    h("9. Khata (credit) outstanding")
    ko = pd.read_csv(KEY / "khata_outstanding_end.csv")
    ci = A.customer_insights()
    est_total = ci["khata_total_est_outstanding"]
    cust = pd.read_csv(KEY / "customers.csv")
    cust["active_to"] = pd.to_datetime(cust.active_to).dt.date
    ks = pd.read_csv(KEY / "khata_settlements.csv")
    upi_settlers = set(ks[ks["mode"] == "upi"].customer_id)
    active = set(cust[cust.active_to >= A.last].customer_id)
    true_all = float(ko.outstanding.sum())
    gone = float(ko[~ko.customer_id.isin(active)].outstanding.sum())
    true_active_upi = float(ko[ko.customer_id.isin(active & upi_settlers)].outstanding.sum())
    M["khata"] = dict(estimated=est_total, true_all=true_all, true_bad_debt_graduated=gone,
                      true_active_upi_settlers=true_active_upi)
    p(f"- True outstanding at year end: ₹{true_all:,.0f}, of which ₹{gone:,.0f} is owed by students who "
      f"graduated (likely bad debt, invisible in UPI data)")
    p(f"- Active customers who settle by UPI owe ₹{true_active_upi:,.0f}; pipeline estimate ₹{est_total:,}")
    p("- The estimate only sees settlements, not the credit given, so it is a rough lower bound. "
      "A simple khata book in the app would make this exact.")

    out = ROOT / "eval"
    (out / "metrics.json").write_text(json.dumps(M, indent=2, default=str))
    head = ["# Pipeline evaluation against the synthetic answer key",
            f"\nGenerated by `eval/evaluate_pipeline.py`. Item prior: **{A.prior_used}**."]
    (out / "report.md").write_text("\n".join(head + lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main(use_owner_prior="--no-owner-prior" not in sys.argv)
