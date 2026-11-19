"""Chai Stall Analytics - Streamlit app.

    .venv/bin/streamlit run app.py
"""
import hashlib
import os
import warnings
from datetime import timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

warnings.filterwarnings("ignore")
from src.pipeline.analytics import StallAnalytics  # noqa: E402

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw"
UP = ROOT / "data" / "uploads"
st.set_page_config(page_title="Chai Stall Analytics", page_icon="☕", layout="wide")


@st.cache_resource(show_spinner="Reading statement and decomposing payments (first run ~1-2 min)...")
def load(stmt, menu, hist, cal, weather, closed, cash, use_prior, _key):
    return StallAnalytics(stmt, menu, hist, cal, weather, closed, cash_share=cash,
                          cash_range=(max(cash - 0.07, 0.0), min(cash + 0.07, 0.9)),
                          use_owner_prior=use_prior)


def save_upload(f):
    UP.mkdir(parents=True, exist_ok=True)
    p = UP / f.name
    p.write_bytes(f.getvalue())
    return p


# ------------------------------------------------------------------ sidebar
st.sidebar.title("☕ Chai Stall Analytics")
src = st.sidebar.radio("Data", ["Sample stall (synthetic)", "Upload my files"])
if src == "Upload my files":
    f_stmt = st.sidebar.file_uploader("Paytm UPI statement (.xlsx)", type=["xlsx"])
    f_menu = st.sidebar.file_uploader("Menu (.csv: item_id,item,category,price,cost,made_in_batches)", type=["csv"])
    f_hist = st.sidebar.file_uploader("Price history (optional .csv)", type=["csv"])
    if not (f_stmt and f_menu):
        st.info("Upload a statement and a menu to begin, or switch to the sample stall.")
        st.stop()
    stmt, menu = save_upload(f_stmt), save_upload(f_menu)
    hist = save_upload(f_hist) if f_hist else None
else:
    stmt = next(RAW.glob("Paytm*.xlsx"))
    menu, hist = RAW / "menu.csv", RAW / "menu_price_history.csv"
cash = st.sidebar.slider("Share of sales paid in cash", 0.0, 0.6, 0.25, 0.01,
                         help="UPI statements can't see cash. Revenue is scaled up by this share; "
                              "the range shown is ±7 points.")
use_prior = st.sidebar.checkbox("Use owner's rough daily estimates (menu column)", True)
key = hashlib.md5(Path(stmt).read_bytes()[:200000] + Path(menu).read_bytes()).hexdigest()
A = load(str(stmt), str(menu), str(hist) if hist else None, str(RAW / "campus_calendar.csv"),
         str(RAW / "weather_pilani.csv"), str(RAW / "stall_closed_days.csv"), cash, use_prior, key)
st.sidebar.caption(f"Data: {A.first} → {A.last}")

tabs = st.tabs(["Overview", "Items", "Combos", "Forecast & prep", "Menu matrix", "What-if",
                "Customers", "Diagnostics", "Ask (chat)"])

# ------------------------------------------------------------------ overview
with tabs[0]:
    ov = A.overview()
    c = st.columns(4)
    c[0].metric("Estimated revenue (year)", f"₹{ov['estimated_total_revenue']:,}",
                help=f"Range ₹{ov['estimated_total_revenue_range'][1]:,} – ₹{ov['estimated_total_revenue_range'][0]:,}")
    c[1].metric("UPI sales", f"₹{ov['upi_sales_total']:,}")
    c[2].metric("Avg revenue / class day", f"₹{ov['avg_daily_revenue_class_days']:,}")
    c[3].metric("UPI payments / class day", f"{ov['avg_upi_payments_per_class_day']}")
    d = A.daily.reset_index().rename(columns={"index": "date"})
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d.date, y=d.revenue_high, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=d.date, y=d.revenue_low, fill="tonexty", line=dict(width=0),
                             fillcolor="rgba(200,120,40,0.2)", name="range (cash share)"))
    fig.add_trace(go.Scatter(x=d.date, y=d.revenue_est, name="estimated revenue", line=dict(color="#b5651d")))
    fig.add_trace(go.Scatter(x=d.date, y=d.upi_sales, name="UPI sales", line=dict(color="#555", dash="dot")))
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10), title="Daily revenue",
                      yaxis_title="₹ per day", hovermode="x unified")
    st.plotly_chart(fig, width="stretch")
    ph = d.groupby("phase").agg(days=("date", "size"), avg_revenue=("revenue_est", "mean")).round(0)
    st.subheader("By academic period")
    st.dataframe(ph.sort_values("avg_revenue", ascending=False), width="stretch")
    st.caption(f"Statement rows: {ov['statement_rows']}")

# ------------------------------------------------------------------ items
with tabs[1]:
    days = st.select_slider("Window", [7, 14, 30, 60, 90, 180, 365], value=30)
    mix = pd.DataFrame(A.sales_mix(days=days)["items"])
    c1, c2 = st.columns([3, 2])
    c1.plotly_chart(px.bar(mix, x="per_day", y="item", orientation="h", height=650,
                           title=f"Estimated units per day (last {days} days)").update_yaxes(autorange="reversed"),
                    width="stretch")
    c2.dataframe(mix[["item", "units", "per_day", "revenue", "share_units"]], height=650, width="stretch")
    st.caption("Estimated from UPI amounts (which items add up to each payment), scaled up for cash. "
               "Treat single items as ±25%.")
    pick = st.multiselect("Items over time", [A.menu.names[i] for i in A.ids], ["Samosa", "Plain Maggi", "Cold Coffee"])
    if pick:
        ids = [k for k, v in A.menu.names.items() if v in pick]
        u = A.units[ids].rolling(7, min_periods=1).mean().rename(columns=A.menu.names)
        st.plotly_chart(px.line(u, title="7-day average units/day", height=350), width="stretch")
    hp = pd.DataFrame(A.hourly_profile(days=days)["per_hour"])
    st.plotly_chart(px.bar(hp, x="hour", y="est_revenue_per_day", title="Revenue by hour", height=300),
                    width="stretch")

# ------------------------------------------------------------------ combos
with tabs[2]:
    cb = A.combos()
    st.write(f"Based on **{cb['labelled_baskets']:,}** payments where customers typed what they bought.")
    st.dataframe(pd.DataFrame(cb["rules"]), width="stretch")
    if cb["existing_combo"]:
        st.metric(cb["existing_combo"]["item"] + " per class day", cb["existing_combo"]["est_units_per_class_day"])
    st.caption(cb["method"] + ". " + cb["caveat"])

# ------------------------------------------------------------------ forecast & prep
with tabs[3]:
    n = st.slider("Days ahead", 7, 30, 14)
    fc = pd.DataFrame(A.forecast_revenue(days=n)["days"])
    fig = go.Figure()
    hist_d = A.daily.tail(42).reset_index().rename(columns={"index": "date"})
    fig.add_trace(go.Scatter(x=hist_d.date, y=hist_d.revenue_est, name="recent (estimated)", line=dict(color="#555")))
    fig.add_trace(go.Scatter(x=fc.date, y=fc.revenue_p90, line=dict(width=0), showlegend=False))
    fig.add_trace(go.Scatter(x=fc.date, y=fc.revenue_p10, fill="tonexty", line=dict(width=0),
                             fillcolor="rgba(200,120,40,0.25)", name="P10–P90"))
    fig.add_trace(go.Scatter(x=fc.date, y=fc.revenue_p50, name="most likely", line=dict(color="#b5651d")))
    fig.update_layout(height=360, title="Revenue forecast", margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, width="stretch")
    st.dataframe(fc, width="stretch", height=250)
    st.subheader("Prep plan")
    day = st.date_input("For", A.last + timedelta(days=1))
    with st.spinner("Forecasting batch items..."):
        pp = A.prep_plan(day)
    st.dataframe(pd.DataFrame(pp["items"]), width="stretch")
    st.caption(pp["method"] + ". " + pp["caveat"])

# ------------------------------------------------------------------ menu matrix
with tabs[4]:
    mm = A.menu_matrix()
    df = pd.DataFrame(mm["items"])
    fig = px.scatter(df, x="mix_pct", y="margin", color="class_", text="item", size="contribution", height=520,
                     color_discrete_map={"Star": "#2e7d32", "Plowhorse": "#f9a825", "Puzzle": "#1565c0", "Dog": "#c62828"})
    fig.add_vline(x=mm["popularity_cutoff_pct"], line_dash="dot")
    fig.add_hline(y=mm["avg_margin_cutoff"], line_dash="dot")
    fig.update_traces(textposition="top center")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(df, width="stretch")

# ------------------------------------------------------------------ what-if
with tabs[5]:
    c1, c2 = st.columns(2)
    item = c1.selectbox("Item", [A.menu.names[i] for i in A.ids if not pd.isna(A._price(i))])
    iid = next(k for k, v in A.menu.names.items() if v == item)
    newp = c2.number_input("New price ₹", value=float(A._price(iid)) + 5, step=5.0)
    sim = A.simulate_price(iid, newp)
    k = st.columns(3)
    k[0].metric("Units/day", sim["after_most_likely"]["units_per_day"],
                round(sim["after_most_likely"]["units_per_day"] - sim["now"]["units_per_day"], 1))
    k[1].metric("Revenue/day", f"₹{sim['after_most_likely']['revenue_per_day']}",
                sim["after_most_likely"]["revenue_per_day"] - sim["now"]["revenue_per_day"])
    k[2].metric("Profit/day", f"₹{sim['after_most_likely']['profit_per_day']}", sim["profit_change_per_day"])
    st.write(f"Elasticity {sim['elasticity_used']} (range {sim['elasticity_range']}), from {sim['source']}.")
    st.caption(sim["note"])
    st.subheader("Extra opening hour")
    h = st.slider("Hour", 0, 23, 8)
    st.json(A.simulate_hours(h))

# ------------------------------------------------------------------ customers
with tabs[6]:
    ci = A.customer_insights()
    c = st.columns(4)
    c[0].metric("UPI customers", ci["unique_upi_customers"])
    c[1].metric("Regulars", ci["regulars"])
    c[2].metric("Regulars' share of UPI sales", f"{ci['regulars_share_of_upi_sales_pct']}%")
    c[3].metric("New customers (30 days)", ci["new_customers_last_30d"])
    st.subheader("Top customers"); st.dataframe(pd.DataFrame(ci["top_customers"]), width="stretch")
    st.subheader("Regulars not seen for 3+ weeks"); st.dataframe(pd.DataFrame(ci["regulars_not_seen_21d"]), width="stretch")
    st.caption(ci["note"])

# ------------------------------------------------------------------ diagnostics
with tabs[7]:
    st.subheader("Lasting changes"); st.json(A.detect_shifts())
    st.subheader("Suspected UPI outages"); st.dataframe(pd.DataFrame(A.detect_outages()["suspected_outages"]))
    st.subheader("Compare two periods")
    c = st.columns(4)
    a0 = c[0].date_input("A from", A.last - timedelta(days=90)); a1 = c[1].date_input("A to", A.last - timedelta(days=46))
    b0 = c[2].date_input("B from", A.last - timedelta(days=45)); b1 = c[3].date_input("B to", A.last)
    st.json(A.compare_periods(a0, a1, b0, b1))

# ------------------------------------------------------------------ chat
with tabs[8]:
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    mode = "Claude agent" if has_key else "Offline (keyword router)"
    st.caption(f"Mode: **{mode}**. " + ("" if has_key else "Set ANTHROPIC_API_KEY to use the Claude agent."))
    if "agent" not in st.session_state or st.session_state.get("agent_key") != key:
        if has_key:
            from src.agent.agent import StallAgent
            st.session_state.agent = StallAgent(A, memory_path=ROOT / "data" / "processed" / "agent_memory.json")
        else:
            from src.agent.offline import OfflineAgent
            st.session_state.agent = OfflineAgent(A)
        st.session_state.agent_key, st.session_state.chat = key, []
    for role, text in st.session_state.chat:
        st.chat_message(role).write(text)
    st.caption("Try: Kal kitne samose banau? · Maggi ₹60 karun toh? · Kaunsa combo chalau? · Raat ki sales kyu giri?")
    if q := st.chat_input("Poochiye..."):
        st.chat_message("user").write(q)
        with st.spinner("Soch raha hoon..."):
            r = st.session_state.agent.ask(q)
        st.chat_message("assistant").write(r["answer"])
        with st.expander("Tools used / checks"):
            st.json({"tools": r["tools"], "unsupported_numbers": r.get("unsupported_numbers")})
        st.session_state.chat += [("user", q), ("assistant", r["answer"])]
