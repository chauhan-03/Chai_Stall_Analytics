"""Research-backed assumptions for the synthetic chai stall.

Every number here is a modelling assumption. Sources and confidence levels are
listed in docs/RESEARCH_AND_ASSUMPTIONS.md. Change values here, rerun the
generator, and the answer key changes with it.
"""
from datetime import date

SEED = 42
START = date(2025, 11, 16)   # same window as the reference Paytm statement
END = date(2026, 11, 15)

STALL = {
    "name": "Shyam Chai Corner",
    "owner": "Shyam Lal Saini",          # fictional
    "location": "Near hostel cluster, BITS Pilani campus (fictional stall)",
    "open_hour": 9,                      # 09:00 first sale
    "close_hour": 19,                    # 19:00 close (last sale before 7 pm)
    "masked_phone": "******4417",
    "masked_email": "shyam.chai****@gmail.com",
    "receive_account": "State Bank Of India - 07",
    "second_account": "Punjab National Bank - 52",
}

# --------------------------------------------------------------------------
# MENU
# temp: +1 sells more when cold, -1 sells more when hot, 0 neutral
# slots: relative appeal by time slot  (morning 9-10, midday 11-15,
#        evening 16-18; night/late values are unused while the stall closes at 19:00.
#        Maggi/coffee evening appeal is raised so the hostel snack crowd that used to
#        come at night now comes before closing)
# batch: prepared in advance in batches (perishable, can stock out)
# fried: demand rises on rainy days
# --------------------------------------------------------------------------
M, D, E, N, L = "morning", "midday", "evening", "night", "late"

MENU = [
    # id, name, category, price, cost, temp, slots, batch, fried, base_pop
    ("CUT_CHAI",   "Cutting Chai",            "beverage_hot", 10, 4.5, 1,  {M:1.3, D:0.9, E:1.2, N:1.0, L:1.1}, False, False, 1.00),
    ("MASALA_CHAI","Masala Chai",             "beverage_hot", 15, 6.0, 1,  {M:1.3, D:0.9, E:1.3, N:1.0, L:1.0}, False, False, 1.25),
    ("ADRAK_CHAI", "Adrak Elaichi Chai",      "beverage_hot", 20, 7.5, 1,  {M:1.1, D:0.7, E:1.2, N:1.0, L:0.9}, False, False, 0.45),
    ("KULHAD_CHAI","Kulhad Chai",             "beverage_hot", 25, 11.0, 1, {M:0.8, D:0.6, E:1.3, N:1.2, L:0.8}, False, False, 0.35),
    ("HOT_COFFEE", "Hot Coffee",              "beverage_hot", 25, 9.5, 1,  {M:0.9, D:0.7, E:1.25, N:1.2, L:1.6}, False, False, 0.40),
    ("COLD_COFFEE","Cold Coffee",             "beverage_cold",50, 20.0,-1, {M:0.3, D:1.4, E:1.3, N:1.1, L:0.6}, False, False, 0.35),
    ("LASSI",      "Sweet Lassi",             "beverage_cold",40, 16.0,-1, {M:0.6, D:1.5, E:1.1, N:0.6, L:0.2}, True,  False, 0.25),
    ("SHIKANJI",   "Nimbu Shikanji",          "beverage_cold",20, 6.0, -1, {M:0.5, D:1.5, E:1.2, N:0.7, L:0.3}, False, False, 0.30),
    ("COLD_DRINK", "Cold Drink 250ml",        "packaged",     20, 15.0,-1, {M:0.3, D:1.3, E:1.1, N:1.1, L:0.9}, False, False, 0.35),
    ("WATER",      "Water Bottle 1L",         "packaged",     20, 13.0,-1, {M:0.6, D:1.3, E:1.0, N:0.8, L:0.6}, False, False, 0.25),
    ("SAMOSA",     "Samosa",                  "snack_fried",  15, 6.0, 0,  {M:0.4, D:1.1, E:1.6, N:0.9, L:0.3}, True,  True,  1.10),
    ("KACHORI",    "Pyaaz Kachori",           "snack_fried",  25, 10.0, 0, {M:1.4, D:1.0, E:1.2, N:0.5, L:0.1}, True,  True,  0.55),
    ("MIRCHI_BADA","Mirchi Bada",             "snack_fried",  20, 8.0, 0,  {M:0.6, D:1.0, E:1.5, N:0.6, L:0.1}, True,  True,  0.40),
    ("BREAD_PAKODA","Bread Pakoda",           "snack_fried",  25, 10.0, 0, {M:1.2, D:0.9, E:1.3, N:0.6, L:0.2}, True,  True,  0.45),
    ("POHA",       "Poha",                    "breakfast",    30, 11.0, 0, {M:2.6, D:0.5, E:0.2, N:0.1, L:0.0}, True,  False, 0.45),
    ("PARATHA",    "Aloo Paratha",            "breakfast",    40, 15.0, 1, {M:2.2, D:0.9, E:0.2, N:0.4, L:0.2}, False, False, 0.35),
    ("BUN_MASKA",  "Bun Maska",               "snack",        25, 9.0, 0,  {M:1.6, D:0.8, E:1.0, N:0.8, L:0.7}, False, False, 0.35),
    ("MAGGI",      "Plain Maggi",             "maggi",        40, 16.0, 1, {M:0.4, D:1.0, E:1.45, N:1.6, L:2.0}, False, False, 0.85),
    ("MASALA_MAGGI","Masala Veg Maggi",       "maggi",        55, 22.0, 1, {M:0.3, D:1.0, E:1.45, N:1.6, L:1.8}, False, False, 0.50),
    ("CHEESE_MAGGI","Cheese Maggi",           "maggi",        70, 32.0, 1, {M:0.2, D:0.9, E:1.35, N:1.5, L:1.8}, False, False, 0.30),
    ("VEG_SANDWICH","Veg Sandwich",           "sandwich",     40, 16.0, 0, {M:0.9, D:1.3, E:1.1, N:1.0, L:0.7}, False, False, 0.30),
    ("GRILL_SANDWICH","Grilled Cheese Sandwich","sandwich",   70, 30.0, 0, {M:0.5, D:1.2, E:1.1, N:1.3, L:1.0}, False, False, 0.25),
    ("BREAD_OMELETTE","Bread Omelette",       "egg",          50, 20.0, 1, {M:1.6, D:0.9, E:0.8, N:1.1, L:1.2}, False, False, 0.35),
    ("BISCUIT",    "Biscuit Packet",          "packaged",     10, 8.0, 0,  {M:1.2, D:0.9, E:1.0, N:0.9, L:1.1}, False, False, 0.30),
    ("CHIPS",      "Chips Packet",            "packaged",     20, 16.0, 0, {M:0.4, D:1.1, E:1.0, N:1.2, L:1.2}, False, False, 0.30),
    ("COMBO_CS",   "Chai Samosa Combo",       "combo",        25, 12.0, 0, {M:0.4, D:1.0, E:1.5, N:0.8, L:0.3}, True,  True,  0.00),
]

# Menu events the owner knows about (they go in the owner's menu file too)
LAUNCHES = {"COLD_COFFEE": date(2026, 3, 15), "COMBO_CS": date(2026, 2, 1)}
PRICE_CHANGES = [  # (item, effective date, new price)
    ("MAGGI", date(2026, 9, 1), 50),          # clean mid-semester hike for elasticity
    ("MASALA_MAGGI", date(2026, 9, 1), 60),
    ("KULHAD_CHAI", date(2026, 1, 15), 30),   # kulhad supplier raised cup cost
]
COST_CHANGES = [  # milk price hike (cooperative dairies revise ~₹2/L, spring)
    ("milk", date(2026, 4, 1), 1.06),
]
MILK_ITEMS = {"CUT_CHAI": .06, "MASALA_CHAI": .08, "ADRAK_CHAI": .09, "KULHAD_CHAI": .10,
              "HOT_COFFEE": .12, "COLD_COFFEE": .20, "LASSI": .0, "COMBO_CS": .08,
              "BUN_MASKA": .0}
CURD_ITEMS = {"LASSI": .25}

# --------------------------------------------------------------------------
# ACADEMIC CALENDAR  (BITS Pilani style; see docs for confidence)
# phase -> (student presence, closing-hours multiplier 17-19h, outsider multiplier)
# --------------------------------------------------------------------------
PHASES = {
    "classes":      (1.00, 1.00, 1.0),
    "midsem":       (0.97, 1.65, 0.6),
    "compre":       (0.90, 1.90, 0.5),
    "compre_tail":  (0.45, 1.40, 0.5),   # students leaving as their papers end
    "winter_break": (0.12, 0.60, 0.8),
    "summer_break": (0.20, 0.80, 0.8),   # summer term + PS-1 + PhD scholars
    "holi_break":   (0.35, 0.70, 0.5),
    "diwali_break": (0.45, 0.70, 0.6),
    "fest":         (1.05, 1.50, 7.0),   # outsiders flood campus
    "orientation":  (1.10, 1.10, 3.0),   # freshers + parents
}

CALENDAR = [  # (start, end inclusive, phase, label)
    (date(2025, 11, 16), date(2025, 11, 30), "classes", "Sem I classes (2025-26)"),
    (date(2025, 12, 1),  date(2025, 12, 10), "compre", "Sem I comprehensive exams"),
    (date(2025, 12, 11), date(2025, 12, 16), "compre_tail", "Sem I compre tail"),
    (date(2025, 12, 17), date(2026, 1, 4),   "winter_break", "Winter break"),
    (date(2026, 1, 5),   date(2026, 3, 2),   "classes", "Sem II classes"),
    (date(2026, 3, 3),   date(2026, 3, 5),   "holi_break", "Holi"),
    (date(2026, 3, 6),   date(2026, 3, 8),   "classes", "Sem II classes"),
    (date(2026, 3, 9),   date(2026, 3, 14),  "midsem", "Sem II mid-semester exams"),
    (date(2026, 3, 15),  date(2026, 4, 1),   "classes", "Sem II classes"),
    (date(2026, 4, 2),   date(2026, 4, 5),   "fest", "APOGEE (tech fest)"),
    (date(2026, 4, 6),   date(2026, 4, 30),  "classes", "Sem II classes"),
    (date(2026, 5, 1),   date(2026, 5, 10),  "compre", "Sem II comprehensive exams"),
    (date(2026, 5, 11),  date(2026, 5, 16),  "compre_tail", "Sem II compre tail"),
    (date(2026, 5, 17),  date(2026, 7, 31),  "summer_break", "Summer vacation / summer term"),
    (date(2026, 8, 1),   date(2026, 8, 4),   "orientation", "Sem I start + freshers arrive"),
    (date(2026, 8, 5),   date(2026, 9, 16),  "classes", "Sem I classes (2026-27)"),
    (date(2026, 9, 17),  date(2026, 9, 20),  "fest", "BOSM (sports fest)"),
    (date(2026, 9, 21),  date(2026, 10, 4),  "classes", "Sem I classes"),
    (date(2026, 10, 5),  date(2026, 10, 10), "midsem", "Sem I mid-semester exams"),
    (date(2026, 10, 11), date(2026, 10, 28), "classes", "Sem I classes"),
    (date(2026, 10, 29), date(2026, 11, 1),  "fest", "Oasis (cultural fest)"),
    (date(2026, 11, 2),  date(2026, 11, 6),  "classes", "Sem I classes"),
    (date(2026, 11, 7),  date(2026, 11, 9),  "diwali_break", "Diwali"),
    (date(2026, 11, 10), date(2026, 11, 15), "classes", "Sem I classes"),
]

# Upcoming calendar (public info the forecaster may use; not simulated)
FUTURE_CALENDAR = [
    (date(2026, 11, 16), date(2026, 11, 30), "classes", "Sem I classes"),
    (date(2026, 12, 1),  date(2026, 12, 10), "compre", "Sem I comprehensive exams"),
    (date(2026, 12, 11), date(2026, 12, 16), "compre_tail", "Sem I compre tail"),
    (date(2026, 12, 17), date(2027, 1, 4),   "winter_break", "Winter break"),
]

CLOSED_DAYS = {  # stall shut (owner-side events, appear as zero-sale days)
    date(2026, 3, 4): "Holi (Dhulandi) - stall closed",
    date(2026, 2, 18): "Owner at family wedding",
    date(2026, 2, 19): "Owner at family wedding",
    date(2026, 2, 20): "Owner at family wedding",
    date(2026, 7, 9): "Owner unwell",
    date(2026, 11, 8): "Diwali - stall closed",
}

# Synthetic UPI outages (real ones happened 26 Mar, 2 Apr, 12 Apr 2025)
UPI_OUTAGES = [  # (date, start hour float, end hour float)
    (date(2026, 1, 23), 17.0, 18.75),
    (date(2026, 4, 11), 11.0, 13.5),
    (date(2026, 8, 26), 16.0, 17.0),
]

# Competitor: a second tea stall opens nearby and takes part of the evening crowd (16-19h)
COMPETITOR_OPEN = date(2026, 9, 21)
COMPETITOR_EFFECT = {"evening": 0.72, "other": 0.95}

# --------------------------------------------------------------------------
# CUSTOMERS & PAYMENTS
# --------------------------------------------------------------------------
N_STUDENTS_START = 2400        # stall's catchment of students at start
GRADUATING_SHARE = 0.22        # leave after Sem II compre
FRESHER_SHARE = 0.26           # join on orientation
N_STAFF = 140                  # faculty, staff, mess/security workers, PhD

# UPI app share for receive-side rows (NPCI 2025: PhonePe ~46%, GPay ~35%,
# Paytm ~7%, Navi/super.money/CRED rising). Students skew slightly to GPay.
UPI_APPS = {"PhonePe": 0.44, "Google Pay": 0.38, "Paytm": 0.08, "Navi": 0.04,
            "super.money": 0.03, "CRED": 0.02, "BHIM": 0.01}
APP_HANDLES = {
    "PhonePe": ["ybl", "ibl", "axl"],
    "Google Pay": ["okaxis", "oksbi", "okhdfcbank", "okicici"],
    "Paytm": ["ptyes", "ptsbi", "pthdfc", "ptaxis"],
    "Navi": ["naviaxis"],
    "super.money": ["superyes"],
    "CRED": ["axisb"],
    "BHIM": ["upi"],
}
CASH_TREND = 0.22          # relative fall in cash propensity across the year

# --------------------------------------------------------------------------
# MENU-SPECIFIC BEHAVIOUR (chai stall values; the redi profile overrides them)
# --------------------------------------------------------------------------
BATCH_START = {"SAMOSA": 130, "KACHORI": 45, "MIRCHI_BADA": 30, "BREAD_PAKODA": 35,
               "POHA": 30, "LASSI": 12}          # owner's first-day prep, before any history
STOCK_USES = {"COMBO_CS": "SAMOSA"}              # dish -> batch item it uses up
SUBSTITUTES = ("SAMOSA", "KACHORI", "MIRCHI_BADA", "BREAD_PAKODA", "BUN_MASKA")  # on sell-out
ADDONS = None             # None -> the hand-written chai-stall basket rules in simulate.py
EXTRA_MILK = {"LASSI": 0.25, "BUN_MASKA": 0.01}  # litres (curd counted as milk)
PACKAGED_ITEMS = ["COLD_DRINK", "WATER", "BISCUIT", "CHIPS"]
BAKERY_COST = {"BUN_MASKA": 6, "VEG_SANDWICH": 7, "GRILL_SANDWICH": 8, "BREAD_PAKODA": 3,
               "BREAD_OMELETTE": 4}
KULHAD_COST = {"KULHAD_CHAI": 3}
REMARK_WORDS = None       # None -> statement.py's chai-stall remark words
GENERIC_REMARKS = None
MENU_ALIASES = None       # redi: written to menu.csv so the pipeline can read remarks
COMBO_RULES_TEXT = [
    "fried snack -> chai (58% normal, 35% when tmax>=36)",
    "poha / bread omelette -> chai (50%)", "paratha -> masala chai (45%)",
    "maggi -> cold drink (hot) or coffee (after 17:00) / chai",
    "sandwich -> cold coffee (30% after launch)",
    "chai -> bun maska / kachori (morning), samosa / mirchi bada (evening) 28%",
    "masala chai + samosa -> Chai Samosa Combo (75% after 1 Feb 2026)"]

from ..profiles import PROFILE  # noqa: E402
if PROFILE == "redi":
    from .config_redi import OVERRIDES
    globals().update(OVERRIDES)
