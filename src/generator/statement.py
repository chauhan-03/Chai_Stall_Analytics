"""Render the ground truth as a Paytm UPI statement (.xlsx), same layout as a real one.

Sheets: 'Summary' and 'Passbook Payment History' with columns
Date | Time | Transaction Details | Other Transaction Details (UPI ID or A/c No) |
Your Account | Amount | UPI Ref No. | Order ID | Remarks | Tags | Comment
"""
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font
from . import config as C
from .simulate import before_close

COLS = ["Date", "Time", "Transaction Details", "Other Transaction Details (UPI ID or A/c No)",
        "Your Account", "Amount", "UPI Ref No.", "Order ID", "Remarks", "Tags", "Comment"]

REMARK_WORDS = {
    "CUT_CHAI": ["chai", "cutting", "chai bhaiya"], "MASALA_CHAI": ["chai", "masala chai", "tea"],
    "ADRAK_CHAI": ["adrak chai"], "KULHAD_CHAI": ["kulhad"], "HOT_COFFEE": ["coffee"],
    "COLD_COFFEE": ["cold coffee"], "LASSI": ["lassi"], "SHIKANJI": ["shikanji", "nimbu pani"],
    "COLD_DRINK": ["coke", "cold drink", "thums up"], "WATER": ["water", "paani"],
    "SAMOSA": ["samosa", "samose"], "KACHORI": ["kachori"], "MIRCHI_BADA": ["mirchi bada"],
    "BREAD_PAKODA": ["bread pakoda"], "POHA": ["poha"], "PARATHA": ["paratha"],
    "BUN_MASKA": ["bun maska"], "MAGGI": ["maggi"], "MASALA_MAGGI": ["masala maggi", "maggi"],
    "CHEESE_MAGGI": ["cheese maggi"], "VEG_SANDWICH": ["sandwich"], "GRILL_SANDWICH": ["grilled sandwich"],
    "BREAD_OMELETTE": ["bread omelette", "omelette"], "BISCUIT": ["biscuit"], "CHIPS": ["chips", "lays"],
    "COMBO_CS": ["combo", "chai samosa"],
}
GENERIC_REMARKS = ["🙏", "thanks bhaiya", "UPI", "Paid via app", "food", "👍", "shyam bhaiya", "snacks"]
REMARK_WORDS = C.REMARK_WORDS or REMARK_WORDS          # redi profile brings its own menu words
GENERIC_REMARKS = C.GENERIC_REMARKS or GENERIC_REMARKS

VENDORS = {  # fictional suppliers: (display, vpa, tag)
    "dairy": ("Shree Ganesh Dairy", "paytmqr28100505019kx3dairy@paytm on Paytm", "#🛒 Groceries"),
    "gas": ("Jai Ambe Gas Service", "jaiambegas.pilani@oksbi on Google Pay", "#🧾 Bill Payments"),
    "kirana": ("Agarwal Kirana Bhandar", "q284719033@ybl on PhonePe", "#🛒 Groceries"),
    "bakery": ("New Pilani Bakery", "newpilanibakery@okaxis on Google Pay", "#🥘 Food"),
    "packaged": ("Marudhar Distributors", "marudhardist01@ybl on PhonePe", "#🛍 Shopping"),
    "kulhad": ("Prajapati Kulhad Udyog", "paytmqr6kul8hd@ptys on Paytm", "#🔄 Miscellaneous"),
    "licence": ("Campus Shop Licence Fee", "campusestate.fee@sbi", "#🏦 Services"),
}


class StatementWriter:
    def __init__(self, sim_out, customers, rng):
        self.o, self.oi = sim_out["orders"], sim_out["order_items"]
        self.daily, self.deferred = sim_out["daily"], sim_out["deferred"]
        self.cust = customers.set_index("customer_id")
        self.rng = rng
        self.rows, self.key = [], []
        self.used_refs = set()

    def ref(self, t):
        while True:
            r = f"{t.year % 10}{t.timetuple().tm_yday:03d}{self.rng.integers(0, 10**8):08d}"
            if r not in self.used_refs:
                self.used_refs.add(r); return r

    def add(self, t, details, vpa, amount, tags, remarks=None, account=None, kind="", order_id=None,
            customer_id=None, comment=None):
        sign = "+" if amount > 0 else "-"
        ref = self.ref(t)
        self.rows.append({
            "_t": t, "Date": t.strftime("%d/%m/%Y"), "Time": t.strftime("%H:%M:%S"),
            "Transaction Details": details, "Other Transaction Details (UPI ID or A/c No)": vpa,
            "Your Account": account or C.STALL["receive_account"],
            "Amount": f"{sign}{abs(amount):,.2f}", "UPI Ref No.": ref, "Order ID": None,
            "Remarks": remarks, "Tags": tags, "Comment": comment})
        self.key.append(dict(upi_ref=ref, datetime=t, amount=amount, true_type=kind,
                             order_id=order_id, customer_id=customer_id))
        return ref

    # ---------------------------------------------------------------- customers
    def payer(self, cid):
        if cid in self.cust.index:
            c = self.cust.loc[cid]
            return c.display_name, c.vpa, c.app
        # outsider: one-off identity, cached so refunds go back to the same VPA
        if not hasattr(self, "_out_ids"):
            self._out_ids = {}
        if cid not in self._out_ids:
            from .people import FIRST, LAST, _upi_identity, _display_name
            f, l = self.rng.choice(FIRST), self.rng.choice(LAST)
            app, vpa = _upi_identity(self.rng, f, l)
            self._out_ids[cid] = (_display_name(self.rng, f, l), vpa, app)
        return self._out_ids[cid]

    def receipt(self, t, cid, amount, kind, order_id=None, remark=None):
        name, vpa, app = self.payer(cid)
        details = name if app == "CRED" else f"Received from {name}"
        acct = "Other UPI App - CRED" if app == "CRED" else None
        return self.add(t, details, f"{vpa} on {app}", amount, "#💵 Money Received", remark,
                        acct, kind, order_id, cid)

    def build_sales(self):
        rng = self.rng
        items_by_order = self.oi.groupby("order_id").apply(
            lambda g: dict(zip(g.item_id, g.qty)), include_groups=False).to_dict()
        upi = self.o[self.o["mode"] == "upi"]
        for r in upi.itertuples():
            basket = items_by_order.get(r.order_id, {})
            remark = None
            u = rng.random()
            if u < 0.045 and basket:
                parts = []
                for iid, q in basket.items():
                    w = rng.choice(REMARK_WORDS[iid])
                    parts.append(f"{q} {w}" if q > 1 else w)
                remark = " + ".join(parts) if rng.random() < 0.7 else parts[0]
            elif u < 0.06:
                remark = rng.choice(GENERIC_REMARKS)
            amt = float(r.amount)
            # typo: customer types 450 instead of 45 -> owner refunds difference
            if rng.random() < 0.0008 and amt < 100:
                self.receipt(r.datetime, r.customer_id, amt * 10, "sale_typo", r.order_id, remark)
                name, vpa, app = self.payer(r.customer_id)
                self.add(before_close(r.datetime + timedelta(minutes=int(rng.integers(2, 30)))),
                         f"Money sent to {name}", f"{vpa} on {app}", -amt * 9, "#💵 Money Transfer",
                         None, None, "refund", r.order_id, r.customer_id)
                continue
            self.receipt(r.datetime, r.customer_id, amt, "sale", r.order_id, remark)
            # duplicate payment (network retry) -> refunded later
            if rng.random() < 0.002:
                t2 = before_close(r.datetime + timedelta(seconds=int(rng.integers(20, 180))))
                self.receipt(t2, r.customer_id, amt, "duplicate", r.order_id)
                name, vpa, app = self.payer(r.customer_id)
                self.add(before_close(t2 + timedelta(minutes=int(rng.integers(5, 240)))), f"Money sent to {name}",
                         f"{vpa} on {app}", -amt, "#💵 Money Transfer", None, None, "refund",
                         r.order_id, r.customer_id)
        for r in self.deferred.itertuples():
            self.receipt(r.datetime, r.customer_id, float(r.amount), "sale_deferred", r.order_id,
                         rng.choice([None, None, "kal wala", "UPI down tha"]))

    # ---------------------------------------------------------------- owner side
    def build_owner(self):
        rng = self.rng
        d = self.daily.copy()
        d["date"] = pd.to_datetime(d["date"])
        sold_cols = [c for c in d.columns if c.startswith("sold_")]
        from .simulate import build_items, cost_on
        items = {it["id"]: it for it in build_items()}
        milk_l, cogs = [], []
        for _, row in d.iterrows():
            day = row["date"].date()
            m = sum(row[f"sold_{i}"] * C.MILK_ITEMS.get(i, 0) for i in items)
            m += sum(row[f"sold_{i}"] * q for i, q in C.EXTRA_MILK.items())
            milk_l.append(m)
            cogs.append(sum(row[f"sold_{i}"] * cost_on(i, day, items) for i in items))
        d["milk_l"], d["cogs"] = milk_l, cogs
        milk_price = np.where(d["date"] >= pd.Timestamp(2026, 4, 1), 59.5, 56.0)
        d["milk_cost"] = d["milk_l"] * milk_price
        d["packaged_cost"] = sum(d[f"sold_{i}"] * items[i]["cost0"] for i in C.PACKAGED_ITEMS)
        d["bakery_cost"] = sum(d[f"sold_{i}"] * c for i, c in C.BAKERY_COST.items())
        d["kirana_cost"] = (d["cogs"] - d["milk_cost"] - d["packaged_cost"] - d["bakery_cost"]).clip(lower=0)
        d["kulhad_cost"] = sum(d[f"sold_{i}"] * c for i, c in C.KULHAD_COST.items())

        def pay_every(col, vendor, every, upi_share, hour_rng, rnd=10):
            acc, last = 0.0, None
            for _, row in d.iterrows():
                acc += row[col]
                day = row["date"]
                if last is None: last = day
                if (day - last).days >= every and acc > 0:
                    if rng.random() < upi_share:
                        name, vpa, tag = VENDORS[vendor]
                        t = day + timedelta(hours=float(rng.uniform(*hour_rng)))
                        amt = round(acc / rnd) * rnd if rnd else round(acc, 2)
                        self.add(t, f"Paid to {name}", vpa, -max(amt, rnd), tag, rng.choice(
                            [None, "Verified Paytm Merchant", "UPI"]), kind=f"expense_{vendor}")
                    acc, last = 0.0, day

        pay_every("milk_cost", "dairy", 7, 0.9, (9, 10.5))
        pay_every("kirana_cost", "kirana", 4, 0.75, (10, 13))
        pay_every("bakery_cost", "bakery", 3, 0.7, (9, 10))
        pay_every("packaged_cost", "packaged", 6, 0.85, (11, 15))
        pay_every("kulhad_cost", "kulhad", 14, 0.8, (9, 12))
        # gas: 19 kg commercial cylinder ~ ₹1,750-1,850, usage proportional to cooking volume
        d["gas_units"] = d["cogs"] / 9000.0
        acc = 0
        for _, row in d.iterrows():
            acc += row["gas_units"]
            if acc >= 1:
                acc -= 1
                price = 1780 if row["date"] < pd.Timestamp(2026, 6, 1) else 1745
                t = row["date"] + timedelta(hours=float(rng.uniform(9, 12)))
                self.add(t, f"Paid to {VENDORS['gas'][0]}", VENDORS["gas"][1], -price,
                         VENDORS["gas"][2], None, kind="expense_gas")
        # monthly: licence fee, electricity, helpers, recharge, family, sweeps
        months = pd.date_range(C.START, C.END, freq="MS")
        for m in months:
            t = m + timedelta(days=int(rng.integers(1, 6)), hours=float(rng.uniform(10, 18)))
            self.add(t, f"Paid to {VENDORS['licence'][0]}", VENDORS["licence"][1], -6500,
                     VENDORS["licence"][2], "Monthly licence", kind="expense_licence")
            t = m + timedelta(days=int(rng.integers(8, 15)), hours=float(rng.uniform(10, 18.9)))
            summer = m.month in (6, 7)
            self.add(t, "Bill Payment for Electricity", "JVVNL - K No ******8812",
                     -float(rng.integers(1100, 1600) if summer else rng.integers(1700, 2600)),
                     "#🧾 Bill Payments", "Transaction success", kind="expense_electricity")
            for helper, sal, v in (("Ramesh Kumar Meena", 9500, "******2231@ybl on PhonePe"),
                                   ("Sonu Prajapat", 8000, "sonuprajapat98@oksbi on Google Pay")):
                if helper.startswith("Sonu") and m.month in (6, 7):
                    continue  # second helper goes home in summer
                t = m + timedelta(days=int(rng.integers(0, 4)), hours=float(rng.uniform(17.5, 18.9)))
                self.add(t, f"Money sent to {helper}", v, -sal, "#💵 Money Transfer", None,
                         kind="expense_wages")
            t = m + timedelta(days=int(rng.integers(10, 20)), hours=float(rng.uniform(9, 18.9)))
            self.add(t, f"Money sent to Kamla Devi", "******7720@ptsbi on Paytm",
                     -float(rng.choice([8000, 10000, 12000])), "#💵 Money Transfer", None,
                     kind="personal_family")
            t = m + timedelta(days=int(rng.integers(0, 27)), hours=float(rng.uniform(9, 18.9)))
            self.add(t, "Recharge of Mobile ******4417", "Prepaid recharge", -349.0,
                     "#🧾 Bill Payments", "Recharge successful", kind="personal_recharge")
        # weekly sweep of balance to the other bank (self transfer)
        weekly = d.set_index("date")["upi_sales"].resample("W-SUN").sum()
        for wk, val in weekly.items():
            if val > 3000:
                t = wk + timedelta(hours=float(rng.uniform(18, 18.95)))
                amt = int(val * rng.uniform(0.35, 0.6) / 1000) * 1000
                self.add(t, f"Transferred to Self, {C.STALL['second_account']}", "******4417@ptsbi on Paytm",
                         -amt, "#💵 Self Transfer", None, kind="self_transfer")
        # non-sale money received: relatives, a loan repayment, cashback
        for when, who, amt in ((pd.Timestamp(2026, 1, 14, 16, 20), "Mahesh Saini", 5000),
                               (pd.Timestamp(2026, 6, 3, 11, 5), "Mahesh Saini", 2000),
                               (pd.Timestamp(2026, 8, 20, 18, 40), "Raju Saini", 3500)):
            self.add(when.to_pydatetime(), f"Received from {who}", f"******{rng.integers(1000, 9999)}@ybl on PhonePe",
                     amt, "#💵 Money Received", None, kind="personal_received")
        for _ in range(4):
            t = pd.Timestamp(C.START) + timedelta(days=int(rng.integers(0, 360)), hours=float(rng.uniform(9, 18.9)))
            self.add(t.to_pydatetime(), "Cashback Received", "Paytm Cashback", float(rng.integers(1, 25)),
                     "#💰 Cashback", "Cashback", kind="cashback")

    # ---------------------------------------------------------------- write
    def write(self, path):
        df = pd.DataFrame(self.rows)
        df["_t"] = pd.to_datetime(df["_t"])
        df = df[df["_t"] < pd.Timestamp(C.END) + pd.Timedelta(days=1)].sort_values("_t", ascending=False)
        amt = df["Amount"].str.replace(",", "").astype(float)
        wb = Workbook()
        ws = wb.active; ws.title = "Summary"
        for _ in range(4): ws.append([""])
        ws.append([C.STALL["owner"]]); ws.append([C.STALL["masked_phone"]]); ws.append([C.STALL["masked_email"]])
        ws.append([""])
        ws.append(["Paytm Statement for :", f"{C.START:%d %b'%y} - {C.END:%d %b'%y}".upper()])
        paid = amt[amt < 0]; recv = amt[amt > 0]
        self_mask = df["Tags"].eq("#💵 Self Transfer")
        ws.append(["Money Paid (Amount in Rs.)", f"{paid[~self_mask].sum():,.2f}"])
        ws.append(["Money Paid (No. of Payments)", str(int((amt[~self_mask] < 0).sum()))])
        ws.append(["Money Received (Amount in Rs.)", f"+{recv.sum():,.2f}"])
        ws.append(["Money Received (No. of Payments)", str(int(len(recv)))])
        ws.append([""])
        ws.append(["Accounts", "Money Paid\n(Amount in Rs.)", "Money Paid\n(No. of Payments)",
                   "Money Received\n(Amount in Rs.)", "Money Received\n(No. of Payments)"])
        for acct, g in df.assign(a=amt).groupby("Your Account"):
            gp, gr = g.a[(g.a < 0) & ~g.Tags.eq("#💵 Self Transfer")], g.a[g.a > 0]
            ws.append([acct, f"{-gp.sum():,.2f}", str(len(gp)), f"{gr.sum():,.2f}", str(len(gr))])
        ws.append([""])
        ws.append(["All payments done by you on Paytm App are reflected in this statement"])
        ws.append(["Notes:"])
        ws.append(["- Self transfer payments are not included in the total money paid and money received calculations."])
        ws.append(["- Payments that you might have hidden on payment history page will not be included in this statement."])
        ws2 = wb.create_sheet("Passbook Payment History")
        ws2.append(COLS)
        for c in ws2[1]: c.font = Font(bold=True)
        for row in df[COLS].itertuples(index=False):
            ws2.append([None if (isinstance(v, float) and np.isnan(v)) else v for v in row])
        wb.save(path)
        key = pd.DataFrame(self.key)
        key = key[key["upi_ref"].isin(set(df["UPI Ref No."]))]
        return df, key
