"""Customer pool: students and staff with persistent habits and UPI identities."""
from datetime import date
import numpy as np
import pandas as pd
from . import config as C

FIRST = """Aarav Aditya Akash Aman Amit Ananya Anika Anirudh Ankit Anmol Anushka Arjun Arnav Aryan
Ayush Bhavya Chirag Devansh Dhruv Diya Eshaan Gaurav Harsh Harshita Ishaan Ishita Jatin Kabir Karan
Kartik Kavya Khushi Krish Kunal Lakshya Manav Meera Mehul Mohit Naman Navya Neha Nikhil Nisha Om
Palak Parth Pooja Pranav Prateek Priya Rahul Rajat Raghav Ritika Riya Rohan Rohit Saanvi Sahil Sakshi
Samarth Sanya Shivam Shreya Shubham Siddharth Simran Sneha Soham Tanay Tanvi Tanya Tushar Utkarsh
Vaibhav Varun Vedant Vihaan Vikram Vishal Yash Yashika Zoya Abhinav Advait Akshay Aniket Deepak
Gautam Hemant Manish Nitin Pankaj Praveen Rakesh Sandeep Sunil Vivek Keerthana Sai Venkat Lakshmi
Arvind Karthik Divya Swathi Anirban Sourav Debjani Rupam Gurpreet Harleen Jaspreet Manpreet Farhan
Imran Ayesha Sana Rehan Tenzin Lalit""".split()
LAST = """Sharma Verma Gupta Agarwal Jain Singh Kumar Yadav Mehta Shah Patel Reddy Rao Nair Menon Iyer
Pillai Das Ghosh Banerjee Mukherjee Chatterjee Bose Sen Mishra Pandey Tiwari Dubey Shukla Tripathi
Chauhan Rathore Shekhawat Saini Meena Joshi Bhatt Kulkarni Deshpande Patil Kapoor Malhotra Khanna
Arora Bansal Goyal Mittal Garg Choudhary Thakur Rawat Negi Bisht Saxena Srivastava Sinha Jha Prasad
Khan Ansari Siddiqui Gill Sandhu Dhillon Naidu Hegde Kamath Murthy Bhattacharya Dutta Kaur""".split()


def _upi_identity(rng, first, last):
    app = rng.choice(list(C.UPI_APPS), p=np.array(list(C.UPI_APPS.values())) / sum(C.UPI_APPS.values()))
    handle = rng.choice(C.APP_HANDLES[app])
    phone4 = f"{rng.integers(0, 10000):04d}"
    style = rng.random()
    if app in ("Paytm", "CRED") or (app == "PhonePe" and style < 0.55):
        vpa = f"******{phone4}@{handle}"                     # masked phone handle
    elif app == "Google Pay" and style < 0.5:
        vpa = f"{first.lower()}{last.lower()}{rng.integers(1, 9999)}@{handle}"
    elif style < 0.8:
        vpa = f"{first.lower()}.{last.lower()[:5]}{rng.integers(10, 99)}@{handle}"
    else:
        vpa = f"{first.lower()}{rng.integers(100, 99999)}@{handle}"
    return app, vpa


def _display_name(rng, first, last):
    r = rng.random()
    if r < 0.15:
        return f"{first} {last}".upper()            # bank KYC caps
    if r < 0.20:
        return f"{first}  {last}"                   # double space quirk
    if r < 0.27:
        return f"{first} {last[0]}"                 # truncated surname
    if r < 0.31:
        return f"{last} {first}"                    # surname first
    return f"{first} {last}"


def make_customers(rng: np.random.Generator, items: list) -> pd.DataFrame:
    n_items = len(items)
    base = np.array([it["base_pop"] for it in items])
    rows = []
    n_grad = int(C.N_STUDENTS_START * C.GRADUATING_SHARE)
    n_fresh = int(C.N_STUDENTS_START * C.FRESHER_SHARE)
    specs = ([("student", C.START, date(2026, 5, 16))] * n_grad
             + [("student", C.START, C.END)] * (C.N_STUDENTS_START - n_grad)
             + [("student", date(2026, 8, 1), C.END)] * n_fresh
             + [("staff", C.START, C.END)] * C.N_STAFF)
    used = set()
    for cid, (ctype, a_from, a_to) in enumerate(specs):
        while True:
            first, last = rng.choice(FIRST), rng.choice(LAST)
            if (first, last) == ("Jatin", "Chauhan"):
                last = "Choudhary"            # avoid matching the project author's real name
            app, vpa = _upi_identity(rng, first, last)
            if vpa not in used:
                used.add(vpa); break
        # visit rate: heavy-tailed -> a few loyal regulars, many occasional
        if ctype == "student":
            rate = float(np.clip(rng.lognormal(np.log(0.047), 0.95), 0.003, 0.9))
            cash_p = float(rng.beta(1.5, 6.0))
            chrono = rng.choice(["early", "normal", "owl"], p=[0.18, 0.52, 0.30])
            khata = bool(rate > 0.35 and rng.random() < 0.25)
        else:
            rate = float(np.clip(rng.lognormal(np.log(0.16), 0.7), 0.01, 1.2))
            cash_p = float(rng.beta(2.5, 3.0))
            chrono = rng.choice(["early", "normal", "owl"], p=[0.45, 0.50, 0.05])
            khata = bool(rng.random() < 0.18)
        # persistent taste: gamma noise around the menu's base popularity
        fav = base * rng.gamma(0.9, 1 / 0.9, n_items)
        rows.append({
            "customer_id": f"C{cid:05d}", "type": ctype, "first": first, "last": last,
            "display_name": _display_name(rng, first, last), "app": app, "vpa": vpa,
            "active_from": a_from, "active_to": a_to, "rate": rate, "cash_p": cash_p,
            "chronotype": chrono, "khata": khata,
            "stays_winter": bool(rng.random() < (0.12 if ctype == "student" else 0.85)),
            "stays_summer": bool(rng.random() < (0.20 if ctype == "student" else 0.80)),
            "group_payer": float(rng.beta(2, 5)),
            "fav": fav,
        })
    return pd.DataFrame(rows)
