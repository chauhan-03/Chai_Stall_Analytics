"""Parse a Paytm UPI statement and classify every row.

Classes
  sale               customer payment for food
  duplicate          repeat of a payment that was refunded
  refund             money returned to a customer
  personal_received  money from family/friends (not revenue)
  expense            supplier / bill / wage payments
  personal_sent      family transfers, recharges
  self_transfer      moving money between own accounts
  other              cashback etc.
"""
import re
from pathlib import Path
import numpy as np
import pandas as pd

SUPPLIER_WORDS = re.compile(r"dairy|gas|kirana|bakery|distribut|kulhad|licen|wholesale|traders|store", re.I)


def read_statement(path) -> pd.DataFrame:
    """Read the 'Passbook Payment History' sheet (header row detected automatically)."""
    xl = pd.ExcelFile(path)
    sheet = next((s for s in xl.sheet_names if "passbook" in s.lower() or "history" in s.lower()),
                 xl.sheet_names[-1])
    raw = pd.read_excel(path, sheet_name=sheet, dtype=str, header=None)
    hdr = raw.index[raw.apply(lambda r: r.astype(str).str.strip().eq("Date").any(), axis=1)][0]
    df = raw.iloc[hdr + 1:].copy()
    df.columns = [str(c).strip() for c in raw.iloc[hdr]]
    df = df.dropna(subset=["Date", "Amount"]).reset_index(drop=True)
    df["datetime"] = pd.to_datetime(df["Date"] + " " + df["Time"], format="%d/%m/%Y %H:%M:%S")
    df["amount"] = df["Amount"].str.replace(",", "").str.replace("+", "").astype(float)
    df["direction"] = np.where(df["amount"] > 0, "in", "out")
    upi_col = [c for c in df.columns if c.startswith("Other Transaction Details")][0]
    other = df[upi_col].fillna("")
    df["vpa"] = other.str.replace(r"\s+on\s+.*$", "", regex=True).str.strip()
    df["app"] = other.str.extract(r"\son\s(.+)$")[0].fillna("")
    det = df["Transaction Details"].fillna("")
    df["counterparty"] = (det.str.replace(r"^(Received from|Paid to|Money sent to|Transferred to)\s+", "",
                                          regex=True).str.replace(r"\s+", " ", regex=True).str.strip())
    df["remarks"] = df.get("Remarks", pd.Series(index=df.index, dtype=str)).fillna("")
    df["tags"] = df.get("Tags", pd.Series(index=df.index, dtype=str)).fillna("")
    df["ref"] = df["UPI Ref No."].astype(str)
    return df.sort_values("datetime").reset_index(drop=True)


def classify_incoming(df: pd.DataFrame, cls: pd.Series) -> pd.Series:
    inc = df.direction == "in"
    det = df["Transaction Details"].fillna("")
    cls[inc & det.str.contains("Cashback")] = "other"
    # duplicates: same vpa+amount within 5 minutes, later refunded
    refunds = df.loc[cls == "refund", ["refund_of", "amount"]].dropna()
    refunded = set(refunds.refund_of.astype(int))
    # partial refund within the hour = customer typed a wrong (bigger) amount -> still a sale
    for _, r in refunds.iterrows():
        j = int(r.refund_of)
        if -r.amount < df.at[j, "amount"] - 0.01:
            cls[j] = "sale"
    for i in refunded:
        if cls[i] == "sale":
            continue
        prev = df[(df.vpa == df.at[i, "vpa"]) & (df.amount == df.at[i, "amount"]) &
                  (df.datetime < df.at[i, "datetime"]) &
                  (df.datetime >= df.at[i, "datetime"] - pd.Timedelta(minutes=5))]
        if len(prev):
            cls[i] = "duplicate"
    cand = inc & (cls == "unclassified")
    amt = df.amount
    # payer-level feature: how often this UPI ID pays us
    n_pay = df[cand].groupby("vpa")["amount"].transform("size")
    df_n = pd.Series(0, index=df.index); df_n[cand] = n_pay
    # big round amounts from rare payers = money from family/friends, not food
    big_round = (amt >= 1000) & (amt % 500 == 0)
    cls[cand & big_round & (df_n <= 3)] = "personal_received"
    cls[cand & (cls == "unclassified")] = "sale"
    return cls


def classify_all(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    cls = pd.Series("unclassified", index=df.index)
    # re-run the outgoing logic, keep refund pointers
    det = df["Transaction Details"].fillna("")
    out = df.direction == "out"
    cls[out & (det.str.startswith("Transferred to Self") | df.tags.str.contains("Self Transfer"))] = "self_transfer"
    cls[out & det.str.match(r"^(Paid to|Bill Payment)")] = "expense"
    cls[out & det.str.match(r"^Recharge")] = "personal_sent"
    df["refund_of"] = None
    incoming = df[df.direction == "in"]
    by_vpa = {v: g for v, g in incoming.groupby("vpa")}
    for i in df.index[out & det.str.startswith("Money sent to") & (cls == "unclassified")]:
        g = by_vpa.get(df.at[i, "vpa"])
        if g is not None:
            win = g[(g.datetime <= df.at[i, "datetime"]) &
                    (g.datetime >= df.at[i, "datetime"] - pd.Timedelta(hours=6))]
            if len(win):
                cls[i] = "refund"; df.at[i, "refund_of"] = win.index[-1]; continue
        cls[i] = "personal_sent"
    # wages: same payee, same amount, roughly monthly
    ps = df[cls == "personal_sent"].groupby(["counterparty", "amount"]).size()
    for (cp, a), n in ps.items():
        if n >= 6 and abs(a) < 12000 and not cp.lower().startswith("recharge"):
            m = (df.counterparty == cp) & (df.amount == a) & (cls == "personal_sent")
            cls[m] = "expense"
    cls = classify_incoming(df, cls)
    df["class"] = cls
    # net sale value: subtract partial refunds (typo payments like 450 instead of 45)
    df["net_amount"] = df["amount"]
    for i in df.index[cls == "refund"]:
        j = df.at[i, "refund_of"]
        if j is not None and cls[j] == "sale":
            df.at[j, "net_amount"] = df.at[j, "amount"] + df.at[i, "amount"]
    df["expense_group"] = None
    e = cls == "expense"
    df.loc[e, "expense_group"] = np.select(
        [df.counterparty.str.contains("Dairy", case=False), df.counterparty.str.contains("Gas", case=False),
         df.counterparty.str.contains("Bakery", case=False), df.counterparty.str.contains("Kirana|Distribut", case=False),
         df["Transaction Details"].str.contains("Electricity", case=False),
         df.counterparty.str.contains("Licen", case=False)],
        ["milk", "gas", "bakery", "groceries/stock", "electricity", "licence"], default="wages/other")[e]
    return df


def ingest(path) -> pd.DataFrame:
    df = classify_all(read_statement(path))
    df["date"] = df["datetime"].dt.date
    # business day: sales after midnight (till 3am) belong to the previous day
    bd = df["datetime"] - pd.to_timedelta((df["datetime"].dt.hour < 3).astype(int), unit="D")
    df["business_date"] = bd.dt.date
    df["hour"] = df["datetime"].dt.hour + np.where(df["datetime"].dt.hour < 3, 24, 0)
    return df


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else next(Path("data/raw").glob("Paytm*.xlsx"))
    d = ingest(p)
    print(d["class"].value_counts())
