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
from src.profiles import RAW  # noqa: E402  (STALL_PROFILE=redi for the real-menu stall)
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
use_prior = st.sidebar.checkbox("Use my rough guess of daily sales per item (menu file)", True)
key = hashlib.md5(Path(stmt).read_bytes()[:200000] + Path(menu).read_bytes()).hexdigest()
A = load(str(stmt), str(menu), str(hist) if hist else None, str(RAW / "campus_calendar.csv"),
         str(RAW / "weather_pilani.csv"), str(RAW / "stall_closed_days.csv"), cash, use_prior, key)
st.sidebar.caption(f"Data: {A.first} → {A.last}")

PERIOD = {"classes": "Class days", "midsem": "Mid-sem exams", "compre": "Final exams",
          "compre_tail": "After final exams", "winter_break": "Winter break", "summer_break": "Summer break",
          "holi_break": "Holi break", "diwali_break": "Diwali break", "fest": "Fests",
          "orientation": "New students arrive"}
GROUP_COLORS = {"Best seller": "#2e7d32", "Popular, low profit": "#f9a825",
                "Good profit, few buyers": "#1565c0", "Weak item": "#c62828"}

tabs = st.tabs(["Summary", "Items sold", "Bought together", "Sales forecast & prep", "Menu check", "What if",
                "Customers", "Changes & problems", "Ask AI"])

# ------------------------------------------------------------------ summary
with tabs[0]:
    ov = A.overview()
    lo_r, hi_r = sorted(ov["estimated_total_revenue_range"])
    c = st.columns(4)
    c[0].metric("Total sales this year (estimate)", f"₹{ov['estimated_total_revenue']:,}",
                help=f"Likely between ₹{lo_r:,} and ₹{hi_r:,}, depending on how much is paid in cash.")
    c[1].metric("Paid by UPI", f"₹{ov['upi_sales_total']:,}")
    c[2].metric("Average sales on a class day", f"₹{ov['avg_daily_revenue_class_days']:,}")
    c[3].metric("UPI payments on a class day", f"{ov['avg_upi_payments_per_class_day']}")
    d = A.daily.reset_index().rename(columns={"index": "date"})
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d.date, y=d.revenue_high, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=d.date, y=d.revenue_low, fill="tonexty", line=dict(width=0),
                             fillcolor="rgba(200,120,40,0.2)", name="likely range (depends on cash)"))
    fig.add_trace(go.Scatter(x=d.date, y=d.revenue_est, name="total sales (estimate)", line=dict(color="#b5651d")))
    fig.add_trace(go.Scatter(x=d.date, y=d.upi_sales, name="UPI only", line=dict(color="#555", dash="dot")))
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10), title="Sales per day",
                      yaxis_title="₹ per day", hovermode="x unified")
    st.plotly_chart(fig, width="stretch")
    st.caption(f"Cash sales don't appear in the UPI statement, so they are added as {A.cash_share:.0%} of sales "
               "(change this in the sidebar).")
    ph = d.groupby("phase").agg(days=("date", "size"), avg=("revenue_est", "mean")).round(0)
    ph = ph.sort_values("avg", ascending=False).reset_index()
    ph["phase"] = ph["phase"].map(lambda x: PERIOD.get(x, x))
    st.subheader("Sales by time of year")
    st.dataframe(ph.rename(columns={"phase": "Period", "days": "Days", "avg": "Average sales per day (₹)"}),
                 hide_index=True, width="stretch")

# ------------------------------------------------------------------ items sold
with tabs[1]:
    days = st.select_slider("Look at the last ... days", [7, 14, 30, 60, 90, 180, 365], value=30)
    mix = pd.DataFrame(A.sales_mix(days=days)["items"])
    c1, c2 = st.columns([3, 2])
    c1.plotly_chart(px.bar(mix, x="per_day", y="item", orientation="h", height=650,
                           labels={"per_day": "Pieces per day", "item": ""},
                           title=f"Pieces sold per day (last {days} days)").update_yaxes(autorange="reversed"),
                    width="stretch")
    c2.dataframe(mix.rename(columns={"item": "Item", "units": "Pieces sold", "per_day": "Per day",
                                     "revenue": "Sales (₹)", "share_units": "Share of all pieces (%)"})[
        ["Item", "Pieces sold", "Per day", "Sales (₹)", "Share of all pieces (%)"]],
        height=650, hide_index=True, width="stretch")
    st.caption("The UPI statement shows only amounts, not items, so these counts are worked out from the amounts "
               "and cash is added. A single item's count can be about 25% off.")
    names = [A.menu.names[i] for i in A.ids]
    pick = st.multiselect("Compare items over time", names, [n for n in names[:3]])
    if pick:
        ids = [k for k, v in A.menu.names.items() if v in pick]
        u = A.units[ids].rolling(7, min_periods=1).mean().rename(columns=A.menu.names)
        st.plotly_chart(px.line(u, title="Pieces per day (weekly average)", height=350,
                                labels={"value": "Pieces per day", "index": "", "variable": "Item"}), width="stretch")
    hp = pd.DataFrame(A.hourly_profile(days=days)["per_hour"])
    st.plotly_chart(px.bar(hp, x="hour", y="est_revenue_per_day", title="Sales by hour of the day", height=300,
                           labels={"hour": "Hour", "est_revenue_per_day": "Sales per day (₹)"}), width="stretch")

# ------------------------------------------------------------------ bought together
with tabs[2]:
    cb = A.combos()
    st.write(f"Based on **{cb['labelled_baskets']:,}** payments where customers typed what they bought.")
    rules = pd.DataFrame(cb["rules"])
    if len(rules):
        st.dataframe(rules.rename(columns={"if_buys": "If someone buys", "also_buys": "They often also buy",
                                           "how_often_pct": "How often (%)", "times_seen": "Times seen"})[
            ["If someone buys", "They often also buy", "How often (%)", "Times seen"]],
            hide_index=True, width="stretch")
    if cb["existing_combo"]:
        st.metric(f"{cb['existing_combo']['item']} sold per class day (estimate)",
                  cb["existing_combo"]["est_units_per_class_day"])
    st.caption(cb["caveat"])

# ------------------------------------------------------------------ forecast & prep
with tabs[3]:
    n = st.slider("Days ahead", 7, 30, 14)
    fc = pd.DataFrame(A.forecast_revenue(days=n)["days"])
    fig = go.Figure()
    hist_d = A.daily.tail(42).reset_index().rename(columns={"index": "date"})
    fig.add_trace(go.Scatter(x=hist_d.date, y=hist_d.revenue_est, name="recent sales", line=dict(color="#555")))
    fig.add_trace(go.Scatter(x=fc.date, y=fc.revenue_p90, line=dict(width=0), showlegend=False))
    fig.add_trace(go.Scatter(x=fc.date, y=fc.revenue_p10, fill="tonexty", line=dict(width=0),
                             fillcolor="rgba(200,120,40,0.25)", name="likely range"))
    fig.add_trace(go.Scatter(x=fc.date, y=fc.revenue_p50, name="most likely", line=dict(color="#b5651d")))
    fig.update_layout(height=360, title="Expected sales", margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, width="stretch")
    fc["period"] = fc["period"].astype(str)
    st.dataframe(fc.rename(columns={"date": "Date", "weekday": "Day", "period": "Period",
                                    "revenue_p50": "Most likely (₹)", "revenue_p10": "Low (₹)",
                                    "revenue_p90": "High (₹)"})[
        ["Date", "Day", "Period", "Most likely (₹)", "Low (₹)", "High (₹)"]],
        hide_index=True, width="stretch", height=250)
    st.subheader("What to make")
    day = st.date_input("For date", A.last + timedelta(days=1))
    with st.spinner("Working out how much to make..."):
        pp = A.prep_plan(day)
    st.dataframe(pd.DataFrame(pp["items"]).rename(columns={
        "item": "Item", "recommended_prep": "Make this many", "demand_most_likely": "Most likely needed",
        "demand_p10": "Low", "demand_p90": "High", "batch_size": "Batch size"})[
        ["Item", "Make this many", "Most likely needed", "Low", "High", "Batch size"]],
        hide_index=True, width="stretch")
    st.caption(pp["method"].capitalize() + ". " + pp["caveat"])

# ------------------------------------------------------------------ menu check
with tabs[4]:
    mm = A.menu_matrix()
    df = pd.DataFrame(mm["items"])
    fig = px.scatter(df, x="mix_pct", y="margin", color="class_", text="item", size="contribution", height=520,
                     color_discrete_map=GROUP_COLORS,
                     labels={"mix_pct": "Share of pieces sold (%)", "margin": "Profit per piece (₹)", "class_": "Group",
                             "contribution": "Total profit (₹)"})
    fig.add_vline(x=mm["popularity_cutoff_pct"], line_dash="dot")
    fig.add_hline(y=mm["avg_margin_cutoff"], line_dash="dot")
    fig.update_traces(textposition="top center")
    st.plotly_chart(fig, width="stretch")
    st.markdown("**Best seller**: sells a lot and earns well · **Popular, low profit**: sells a lot, earns little · "
                "**Good profit, few buyers**: earns well, sells little · **Weak item**: sells little, earns little")
    st.dataframe(df.rename(columns={"item": "Item", "class_": "Group", "mix_pct": "Share sold (%)", "price": "Price (₹)",
                                    "margin": "Profit per piece (₹)", "contribution": "Total profit (₹)",
                                    "action": "What to do"}),
                 hide_index=True, width="stretch")
    st.caption(f"Based on {mm['period']}. The dotted lines are the average: right = sells more than most, "
               "top = earns more per piece than most.")

# ------------------------------------------------------------------ what if
with tabs[5]:
    st.subheader("Change a price")
    c1, c2 = st.columns(2)
    item = c1.selectbox("Item", [A.menu.names[i] for i in A.ids if not pd.isna(A._price(i))])
    iid = next(k for k, v in A.menu.names.items() if v == item)
    newp = c2.number_input("New price ₹", value=float(A._price(iid)) + 5, step=5.0)
    sim = A.simulate_price(iid, newp)
    k = st.columns(3)
    k[0].metric("Pieces per day", sim["after_most_likely"]["units_per_day"],
                round(sim["after_most_likely"]["units_per_day"] - sim["now"]["units_per_day"], 1))
    k[1].metric("Sales per day", f"₹{sim['after_most_likely']['revenue_per_day']:,}",
                sim["after_most_likely"]["revenue_per_day"] - sim["now"]["revenue_per_day"])
    k[2].metric("Profit per day", f"₹{sim['after_most_likely']['profit_per_day']:,}", sim["profit_change_per_day"])
    p_lo = sim["after_if_customers_more_sensitive"]["profit_per_day"]
    p_hi = sim["after_if_customers_less_sensitive"]["profit_per_day"]
    st.write(f"Profit per day could be anywhere from **₹{min(p_lo, p_hi):,} to ₹{max(p_lo, p_hi):,}**, depending on "
             f"how many customers buy less at the new price. How much people cut back is based on {sim['source']}.")
    st.caption(sim["note"])
    st.subheader("Open for one more hour")
    h = st.slider("Open the stall also at this hour", 0, 23, 8, format="%d:00")
    sh = A.simulate_hours(h)
    if "est_extra_revenue_per_day" in sh:
        lo, hi = sh["range"]
        c1, c2 = st.columns(2)
        c1.metric(f"Extra sales per day if open at {sh['hour']}", f"₹{sh['est_extra_revenue_per_day']:,}")
        c2.metric("Likely range", f"₹{lo:,} – ₹{hi:,}")
        st.caption("No sales exist for an hour the stall has never been open, so this assumes about 45% of the "
                   "busier neighbouring hour's sales. Treat it as a rough guide; try it for 2 weeks to know.")
    else:
        st.info(f"The stall is already open at {sh['hour']} "
                f"(about ₹{sh.get('current_revenue_per_day', 0):,} per day at that hour).")

# ------------------------------------------------------------------ customers
with tabs[6]:
    ci = A.customer_insights()
    c = st.columns(4)
    c[0].metric("Customers who paid by UPI", f"{ci['unique_upi_customers']:,}")
    c[1].metric("Regular customers", ci["regulars"])
    c[2].metric("Regulars' share of UPI sales", f"{ci['regulars_share_of_upi_sales_pct']}%")
    c[3].metric("New customers (last 30 days)", ci["new_customers_last_30d"])
    cols = {"name": "Name", "visits": "Visits", "spend": "Spent (₹)", "last_seen": "Last visit",
            "visits_per_week": "Visits per week", "upi_id": "UPI ID"}
    order = ["Name", "Visits", "Visits per week", "Spent (₹)", "Last visit", "UPI ID"]
    st.subheader("Top customers")
    st.dataframe(pd.DataFrame(ci["top_customers"]).rename(columns=cols)[order], hide_index=True, width="stretch")
    st.subheader("Regulars who haven't come for 3+ weeks")
    lost = pd.DataFrame(ci["regulars_not_seen_21d"])
    if len(lost):
        st.dataframe(lost.rename(columns=cols)[order], hide_index=True, width="stretch")
    else:
        st.write("None right now.")
    st.caption("Only customers who pay by UPI can be seen; each UPI ID counts as one customer. A regular comes "
               "at least 20 times and about twice a week or more.")

# ------------------------------------------------------------------ diagnostics
with tabs[7]:
    st.subheader("Lasting changes in sales")
    sh = A.detect_shifts()["shifts"]
    if not sh:
        st.write("No lasting change found in the last 60 days of class days.")
    for x in sh:
        up = x["change_pct"] > 0
        st.markdown(f"{'🔺' if up else '🔻'} **{x['slot'].capitalize()} sales ({x['hours']})** "
                    f"{'rose' if up else 'fell'} **{abs(x['change_pct'])}%** from **{x['since']}**: "
                    f"₹{x['before_per_day']:,} → ₹{x['after_per_day']:,} UPI sales per day.")
    st.caption("Compares class days before and after the date where sales changed most; only clear, lasting "
               "changes are shown. A drop in one time slot can mean a new competitor or a timing change.")

    st.subheader("Suspected UPI outages")
    outs = A.detect_outages()["suspected_outages"]
    if outs:
        st.dataframe(pd.DataFrame([{"Date": o["date"], "Hours with no UPI payments": ", ".join(o["hours"]),
                                    "Payments normally expected": o["expected_payments"]} for o in outs]),
                     hide_index=True, width="stretch")
        st.caption("Busy hours with zero UPI payments: likely UPI or bank downtime. Those sales probably "
                   "moved to cash or were lost.")
    else:
        st.write("No suspected UPI outages.")

    st.subheader("Compare two periods")
    c = st.columns(4)
    a0 = c[0].date_input("A from", A.last - timedelta(days=90)); a1 = c[1].date_input("A to", A.last - timedelta(days=46))
    b0 = c[2].date_input("B from", A.last - timedelta(days=45)); b1 = c[3].date_input("B to", A.last)
    cp = A.compare_periods(a0, a1, b0, b1)
    k = st.columns(3)
    k[0].metric("UPI sales per day, A", f"₹{cp['avg_daily_upi_sales'][0]:,}")
    k[1].metric("UPI sales per day, B", f"₹{cp['avg_daily_upi_sales'][1]:,}", f"{cp['change_pct']}%")
    cu = cp["customers"]
    k[2].metric("Customers in B", f"{cu['in_b']:,}", f"{cu['in_b'] - cu['in_a']:+,} vs A")
    dr = pd.DataFrame([{"What changed": n.capitalize(), "Change (%)": v}
                       for n, v in cp["drivers_pct_change"].items() if v is not None])
    st.plotly_chart(px.bar(dr, x="Change (%)", y="What changed", orientation="h", height=260,
                           color=dr["Change (%)"] > 0, color_discrete_map={True: "#2a9d8f", False: "#e76f51"}
                           ).update_layout(showlegend=False, margin=dict(l=0, r=0, t=10, b=0)), width="stretch")
    st.write(f"**Customers:** {cu['new_in_b']:,} new in B; {cu['not_returning']:,} from A did not come back in B.")
    if cp["context"]:
        st.write("**Possible reasons (context):**")
        for line in cp["context"]:
            st.write(f"- {line}")

# ------------------------------------------------------------------ chat
with tabs[8]:
    # AI assistant only: Groq if its key is set, otherwise Claude
    if "agent" not in st.session_state or st.session_state.get("agent_key") != key:
        mem = ROOT / "data" / "processed" / "agent_memory.json"
        st.session_state.agent, st.session_state.agent_error = None, None
        try:
            if os.environ.get("GROQ_API_KEY"):
                from src.agent.groq_agent import GroqAgent
                st.session_state.agent = GroqAgent(A, memory_path=mem)
            elif os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
                from src.agent.agent import StallAgent
                st.session_state.agent = StallAgent(A, memory_path=mem)
            else:
                st.session_state.agent_error = ("No AI key found. Set GROQ_API_KEY (free at console.groq.com) "
                                                "and restart the app.")
        except Exception as e:          # bad key / no network
            st.session_state.agent_error = f"AI assistant could not start: {e}"
        st.session_state.agent_key, st.session_state.chat = key, []
    if st.session_state.agent is None:
        st.error(st.session_state.agent_error)
        st.stop()
    for role, text in st.session_state.chat:
        st.chat_message(role).write(text)
    st.caption("Try: Kal kitne samose banau? · Maggi ₹60 karun toh? · Kaunsa combo chalau? · "
               "October me sales September se kam kyu thi?")
    if q := st.chat_input("Poochiye..."):
        st.chat_message("user").write(q)
        with st.spinner("Soch raha hoon..."):
            r = st.session_state.agent.ask(q)
        st.chat_message("assistant").write(r["answer"])
        st.session_state.chat += [("user", q), ("assistant", r["answer"])]
