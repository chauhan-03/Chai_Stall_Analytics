"""Second synthetic stall: a redi / canteen with a real menu card (photographed).

Everything not listed here (campus, calendar, weather, customers, hours,
competitor, outages, cash trend) is shared with the chai stall in config.py,
so the two stalls differ only in their menu and what follows from it.

Prices are the ones on the card (= prices at the end of the year). Three items
had a price change and two were launched mid-year (the separate top board).
Costs, time-of-day appeal, popularity and combos are assumptions for a stall
of this type; see docs/RESEARCH_AND_ASSUMPTIONS.md.
"""
from datetime import date

M, D, E, N, L = "morning", "midday", "evening", "night", "late"

# time-of-day appeal templates (night/late unused while the stall closes at 19:00)
TEA      = {M: 1.3, D: 0.9, E: 1.3, N: 1.0, L: 1.0}
HOTMILK  = {M: 0.9, D: 0.6, E: 1.2, N: 1.2, L: 1.0}
COLD     = {M: 0.4, D: 1.4, E: 1.2, N: 0.9, L: 0.5}
JUICE    = {M: 1.0, D: 1.3, E: 1.0, N: 0.6, L: 0.3}
FRIED    = {M: 0.6, D: 1.0, E: 1.6, N: 0.8, L: 0.3}
MORNFRY  = {M: 1.4, D: 1.0, E: 1.1, N: 0.5, L: 0.1}
CHAAT    = {M: 0.2, D: 1.0, E: 1.7, N: 0.9, L: 0.3}
MEAL     = {M: 0.8, D: 1.5, E: 1.1, N: 0.8, L: 0.4}
BREAKFST = {M: 2.6, D: 0.5, E: 0.2, N: 0.1, L: 0.0}
BUN      = {M: 0.7, D: 1.2, E: 1.3, N: 1.1, L: 0.8}
MAGGI    = {M: 0.3, D: 1.0, E: 1.45, N: 1.6, L: 2.0}
NIBBLE   = {M: 0.5, D: 1.0, E: 1.3, N: 1.0, L: 0.8}

# id, name, category, price (start of year), cost, temp, slots, batch, fried, base popularity
MENU = [
    # hot drinks
    ("MASALA_CHAI",   "Special Tea",           "beverage_hot",  20, 7.0,  1, TEA,     False, False, 1.60),
    ("LEMON_TEA",     "Lemon Tea",             "beverage_hot",  20, 5.0,  1, TEA,     False, False, 0.25),
    ("HOT_COFFEE",    "Coffee",                "beverage_hot",  20, 8.0,  1, HOTMILK, False, False, 0.45),
    ("HOT_MILK",      "Milk",                  "beverage_hot",  25, 13.0, 1, HOTMILK, False, False, 0.20),
    ("HOT_BADAM_MILK","Hot Badam Milk",        "beverage_hot",  40, 18.0, 1, HOTMILK, False, False, 0.25),
    ("HOT_CHOCOLATE", "Hot Chocolate",         "beverage_hot",  40, 18.0, 1, HOTMILK, False, False, 0.15),
    ("HOT_KHUS",      "Hot Khus",              "beverage_hot",  40, 17.0, 1, HOTMILK, False, False, 0.08),
    ("HOT_ROSE",      "Hot Rose",              "beverage_hot",  40, 17.0, 1, HOTMILK, False, False, 0.08),
    # cold drinks, shakes, juices
    ("LASSI",         "Lassi",                 "beverage_cold", 40, 16.0, -1, COLD,   True,  False, 0.30),
    ("BANANA_SHAKE",  "Banana Shake",          "beverage_cold", 40, 18.0, -1, COLD,   False, False, 0.20),
    ("CHOCO_SHAKE",   "Chocolate Shake",       "beverage_cold", 40, 18.0, -1, COLD,   False, False, 0.25),
    ("STRAWBERRY_SHAKE","Strawberry Shake",    "beverage_cold", 40, 18.0, -1, COLD,   False, False, 0.15),
    ("MANGO_SHAKE",   "Mango Shake",           "beverage_cold", 50, 23.0, -1, COLD,   False, False, 0.25),
    ("BADAM_MILK",    "Badam Milk",            "beverage_cold", 40, 18.0, -1, COLD,   False, False, 0.25),
    ("ROSE_MILK",     "Rose Milk",             "beverage_cold", 40, 17.0, -1, COLD,   False, False, 0.12),
    ("KHUS_MILK",     "Khush Milk",            "beverage_cold", 40, 17.0, -1, COLD,   False, False, 0.08),
    ("COLD_MILK",     "Cold Milk",             "beverage_cold", 20, 11.0, -1, COLD,   False, False, 0.10),
    ("ROOHAFZA",      "Roohafza",              "beverage_cold", 25, 7.5, -1,  COLD,   False, False, 0.12),
    ("KHUS_SHARBAT",  "Khush Sharbat",         "beverage_cold", 25, 7.5, -1,  COLD,   False, False, 0.08),
    ("ORANGE_JUICE",  "Orange Juice",          "beverage_cold", 50, 25.0, -1, JUICE,  False, False, 0.12),
    ("MOSAMBI_JUICE", "Mosami Juice",          "beverage_cold", 50, 25.0, -1, JUICE,  False, False, 0.15),
    ("WATERMELON_JUICE","Watermelon Juice",    "beverage_cold", 50, 22.0, -1, JUICE,  False, False, 0.15),
    ("SHIKANJI",      "Shikanji",              "beverage_cold", 20, 6.0, -1,  COLD,   False, False, 0.35),
    ("LEMON_SODA",    "Lemon Soda",            "beverage_cold", 25, 9.0, -1,  COLD,   False, False, 0.30),
    ("COLD_COFFEE",   "Cold Coffee",           "beverage_cold", 35, 16.0, -1, COLD,   False, False, 0.45),
    ("ICE_TEA",       "Ice Tea",               "beverage_cold", 40, 14.0, -1, COLD,   False, False, 0.15),
    ("MASALA_COLD_DRINK","Masala Cold Drinks", "packaged",      35, 21.0, -1, COLD,   False, False, 0.35),
    # fried snacks (made in batches)
    ("SAMOSA",        "Samosa (Plain)",        "snack_fried",   20, 8.0,  0, FRIED,   True,  True,  1.10),
    ("SAMFRY",        "Samfry",                "snack_fried",   40, 16.0, 0, FRIED,   False, True,  0.15),
    ("MIRCHI_BHAJI",  "Mirchi Bhaji (Single)", "snack_fried",   20, 8.0,  0, FRIED,   True,  True,  0.30),
    ("BREAD_PAKODA",  "Bread Pakoda (Single)", "snack_fried",   20, 8.0,  0, MORNFRY, True,  True,  0.45),
    ("ALOO_BONDA",    "Aloo Bonda (Double)",   "snack_fried",   30, 12.0, 0, FRIED,   True,  True,  0.25),
    ("MIX_VEG_PAKODA","Mix Veg Pakoda",        "snack_fried",   40, 16.0, 0, FRIED,   True,  True,  0.20),
    ("DAL_KACHORI",   "Dal Kachori",           "snack_fried",   25, 10.0, 0, MORNFRY, True,  True,  0.50),
    # chaat
    ("SAMOSA_CHAAT",  "Samchat (Single)",      "chaat",         30, 12.0, 0, CHAAT,   False, False, 0.35),
    ("BUTTER_SAM_CHAAT","Butter Sam Chat",     "chaat",         50, 20.0, 0, CHAAT,   False, False, 0.12),
    ("CHOLE_SAMOSA",  "Chola Samosa",          "chaat",         50, 20.0, 0, CHAAT,   False, False, 0.40),
    ("TIKKI_CHAAT",   "Tikki Chat",            "chaat",         40, 16.0, 0, CHAAT,   False, False, 0.30),
    ("CHOLE_TIKKI_CHAAT","Chola Tikki Chat",   "chaat",         50, 20.0, 0, CHAAT,   False, False, 0.25),
    ("PAPDI_CHAAT",   "Papdi Chat",            "chaat",         40, 16.0, 0, CHAAT,   False, False, 0.25),
    ("BHELPURI",      "Bhelpuri",              "chaat",         30, 11.0, 0, CHAAT,   False, False, 0.30),
    ("KACHORI_CHAAT", "Kachori Chat",          "chaat",         40, 16.0, 0, CHAAT,   False, False, 0.20),
    ("CHOLE_KACHORI", "Chola Kachori",         "chaat",         50, 20.0, 0, CHAAT,   False, False, 0.25),
    ("FRUIT_CHAAT",   "Masala Fruit Chat",     "chaat",         50, 24.0, -1, JUICE,  False, False, 0.12),
    ("WATERMELON",    "Water Melon",           "chaat",         40, 18.0, -1, JUICE,  False, False, 0.10),
    # meals and breakfast
    ("CHOLE_KULCHA",  "Chola Kulcha",          "meal",          60, 24.0, 0, MEAL,    False, False, 0.45),
    ("CHEESE_CHOLE_KULCHA","Cheese Chola Kulcha","meal",        75, 32.0, 0, MEAL,    False, False, 0.12),
    ("VADA_PAV",      "Vada Pav",              "meal",          35, 13.0, 0, MEAL,    False, False, 0.40),
    ("POHA",          "Poha",                  "breakfast",     40, 14.0, 0, BREAKFST,True,  False, 0.40),
    # sandwiches and burgers
    ("SAM_SANDWICH",  "Sam Sandwich Single",   "sandwich",      35, 14.0, 0, BUN,     False, False, 0.20),
    ("BUTTER_SANDWICH","Butter Sandwich",      "sandwich",      50, 20.0, 0, BUN,     False, False, 0.20),
    ("TIKKI_SANDWICH","Tikki Sandwich Single", "sandwich",      30, 12.0, 0, BUN,     False, False, 0.25),
    ("PB_SANDWICH",   "Peanut Butter Sandwich","sandwich",      50, 22.0, 0, BUN,     False, False, 0.10),
    ("BURGER",        "Burger",                "burger",        40, 17.0, 0, BUN,     False, False, 0.40),
    ("CHEESE_BURGER", "Cheese Burger",         "burger",        50, 22.0, 0, BUN,     False, False, 0.25),
    ("PANEER_BURGER", "Paneer Burger",         "burger",        60, 28.0, 0, BUN,     False, False, 0.20),
    # maggi
    ("MAGGI",         "Maggie Extra Masala",   "maggi",         35, 15.0, 1, MAGGI,   False, False, 0.55),
    ("TAWA_MAGGI",    "Tawa Fried Maggie",     "maggi",         45, 18.0, 1, MAGGI,   False, False, 0.30),
    ("CHEESE_MAGGI",  "Cheese Maggie",         "maggi",         45, 22.0, 1, MAGGI,   False, False, 0.30),
    ("PANEER_MAGGI",  "Paneer Fried Maggi",    "maggi",         70, 32.0, 1, MAGGI,   False, False, 0.15),
    # small add-ons
    ("BHUJIYA",       "Bhujiya",               "packaged",      10, 7.0,  0, NIBBLE,  False, False, 0.30),
    ("MASALA_PAPAD",  "Masala Papad",          "snack",         15, 6.0,  0, NIBBLE,  False, False, 0.20),
]

LAUNCHES = {"PANEER_MAGGI": date(2026, 8, 1), "PANEER_BURGER": date(2026, 8, 1)}  # new top board
PRICE_CHANGES = [
    ("COLD_COFFEE", date(2026, 1, 15), 40),
    ("MAGGI", date(2026, 9, 1), 40),           # clean mid-semester hike, as in the chai stall
    ("CHEESE_MAGGI", date(2026, 9, 1), 50),
]
MILK_ITEMS = {"MASALA_CHAI": .08, "HOT_COFFEE": .12, "HOT_MILK": .25, "HOT_BADAM_MILK": .25,
              "HOT_CHOCOLATE": .25, "HOT_KHUS": .25, "HOT_ROSE": .25, "BANANA_SHAKE": .25,
              "CHOCO_SHAKE": .25, "STRAWBERRY_SHAKE": .25, "MANGO_SHAKE": .25, "BADAM_MILK": .25,
              "ROSE_MILK": .25, "KHUS_MILK": .25, "COLD_MILK": .25, "COLD_COFFEE": .20}

# what customers type in UPI remarks (vague words like "shake" or "juice" included on purpose)
REMARK_WORDS = {
    "MASALA_CHAI": ["chai", "tea", "special chai", "chai bhaiya"], "LEMON_TEA": ["lemon tea", "nimbu chai"],
    "HOT_COFFEE": ["coffee", "hot coffee"], "HOT_MILK": ["doodh", "milk", "garam doodh"],
    "HOT_BADAM_MILK": ["hot badam", "badam milk"], "HOT_CHOCOLATE": ["hot chocolate"],
    "HOT_KHUS": ["hot khus"], "HOT_ROSE": ["hot rose"],
    "LASSI": ["lassi"], "BANANA_SHAKE": ["banana shake", "shake"],
    "CHOCO_SHAKE": ["chocolate shake", "choco shake", "shake"],
    "STRAWBERRY_SHAKE": ["strawberry shake", "shake"], "MANGO_SHAKE": ["mango shake", "shake"],
    "BADAM_MILK": ["badam milk", "cold badam"], "ROSE_MILK": ["rose milk"], "KHUS_MILK": ["khus milk"],
    "COLD_MILK": ["cold milk", "thanda doodh"], "ROOHAFZA": ["roohafza", "rooh afza"],
    "KHUS_SHARBAT": ["khus sharbat", "sharbat"], "ORANGE_JUICE": ["orange juice", "juice"],
    "MOSAMBI_JUICE": ["mosambi", "mosambi juice", "juice"],
    "WATERMELON_JUICE": ["watermelon juice", "tarbooz juice", "juice"],
    "SHIKANJI": ["shikanji", "nimbu pani"], "LEMON_SODA": ["lemon soda", "soda"],
    "COLD_COFFEE": ["cold coffee"], "ICE_TEA": ["ice tea", "iced tea"],
    "MASALA_COLD_DRINK": ["masala cold drink", "cold drink", "masala coke"],
    "SAMOSA": ["samosa", "samose"], "SAMFRY": ["samfry", "samosa fry"],
    "MIRCHI_BHAJI": ["mirchi", "mirchi bhaji"], "BREAD_PAKODA": ["bread pakoda"],
    "ALOO_BONDA": ["aloo bonda", "bonda"], "MIX_VEG_PAKODA": ["pakode", "veg pakoda"],
    "DAL_KACHORI": ["kachori", "dal kachori"],
    "SAMOSA_CHAAT": ["samosa chaat", "sam chaat", "chaat"],
    "BUTTER_SAM_CHAAT": ["butter sam chaat", "butter samosa chaat"],
    "CHOLE_SAMOSA": ["chole samosa", "chola samosa"], "TIKKI_CHAAT": ["tikki chaat", "tikki"],
    "CHOLE_TIKKI_CHAAT": ["chole tikki", "chola tikki"], "PAPDI_CHAAT": ["papdi chaat", "papdi"],
    "BHELPURI": ["bhel", "bhelpuri"], "KACHORI_CHAAT": ["kachori chaat"],
    "CHOLE_KACHORI": ["chole kachori"], "FRUIT_CHAAT": ["fruit chaat"],
    "WATERMELON": ["watermelon", "tarbooz"],
    "CHOLE_KULCHA": ["chole kulche", "chole kulcha", "kulcha"], "CHEESE_CHOLE_KULCHA": ["cheese kulcha"],
    "VADA_PAV": ["vada pav", "vadapav"], "POHA": ["poha"],
    "SAM_SANDWICH": ["samosa sandwich", "sam sandwich", "sandwich"],
    "BUTTER_SANDWICH": ["butter sandwich", "sandwich"],
    "TIKKI_SANDWICH": ["tikki sandwich", "sandwich"], "PB_SANDWICH": ["peanut butter sandwich", "pb sandwich"],
    "BURGER": ["burger"], "CHEESE_BURGER": ["cheese burger"], "PANEER_BURGER": ["paneer burger"],
    "MAGGI": ["maggi", "masala maggi"], "TAWA_MAGGI": ["tawa maggi", "fried maggi", "maggi"],
    "CHEESE_MAGGI": ["cheese maggi", "maggi"], "PANEER_MAGGI": ["paneer maggi"],
    "BHUJIYA": ["bhujia", "bhujiya"], "MASALA_PAPAD": ["papad", "masala papad"],
}
GENERIC_REMARKS = ["🙏", "thanks bhaiya", "UPI", "Paid via app", "food", "👍", "bhola bhaiya", "nashta"]


def _aliases():
    """Owner-style keyword list for the pipeline: every word unique to one item, plus a
    default reading for the vague 'maggi' / 'badam milk'. 'shake', 'juice', 'sandwich'
    stay unread, as a real parser could not tell which one was meant."""
    seen = {}
    for iid, words in REMARK_WORDS.items():
        for w in words:
            seen.setdefault(w, set()).add(iid)
    out = {iid: [] for iid in REMARK_WORDS}
    for w, ids in seen.items():
        if len(ids) == 1:
            out[next(iter(ids))].append(w)
    out["MAGGI"].append("maggi")
    out["BADAM_MILK"].append("badam milk")
    return {k: "|".join(v) for k, v in out.items()}


# Basket rules: first rule whose items/categories match the main item applies.
# with: [(item, weight)], optionally by time slot or for hot days (tmax >= 36).
ADDONS = [
    dict(cats=("snack_fried",), p=0.55, p_hot=0.35,
         with_=[("MASALA_CHAI", 0.8), ("LEMON_TEA", 0.1), ("HOT_COFFEE", 0.1)],
         hot_with=[("MASALA_COLD_DRINK", 0.5), ("SHIKANJI", 0.5)]),
    dict(items=("FRUIT_CHAAT", "WATERMELON"), p=0.15, with_=[("SHIKANJI", 0.5), ("LEMON_SODA", 0.5)]),
    dict(cats=("chaat",), p=0.32,
         with_=[("MASALA_COLD_DRINK", 0.35), ("LEMON_SODA", 0.30), ("SHIKANJI", 0.20), ("MASALA_CHAI", 0.15)]),
    dict(cats=("meal", "breakfast"), p=0.45, p_hot=0.35,
         with_=[("MASALA_CHAI", 1.0)], hot_with=[("LASSI", 0.5), ("SHIKANJI", 0.5)]),
    dict(cats=("burger",), p=0.38,
         with_=[("COLD_COFFEE", 0.40), ("MASALA_COLD_DRINK", 0.25), ("CHOCO_SHAKE", 0.20), ("BANANA_SHAKE", 0.15)]),
    dict(cats=("sandwich",), p=0.30, with_=[("COLD_COFFEE", 0.60), ("ICE_TEA", 0.20), ("CHOCO_SHAKE", 0.20)]),
    dict(cats=("maggi",), p=0.28, p_hot=0.25, with_=[("MASALA_CHAI", 1.0)],
         by_slot={"evening": [("HOT_COFFEE", 0.5), ("MASALA_CHAI", 0.5)]},
         hot_with=[("MASALA_COLD_DRINK", 0.6), ("LEMON_SODA", 0.4)]),
    dict(items=("MASALA_CHAI", "LEMON_TEA", "HOT_COFFEE"), p=0.30,
         with_=[("SAMOSA", 0.5), ("BHUJIYA", 0.3), ("MASALA_PAPAD", 0.2)],
         by_slot={"morning": [("DAL_KACHORI", 0.35), ("BREAD_PAKODA", 0.30), ("POHA", 0.15), ("BHUJIYA", 0.20)],
                  "evening": [("SAMOSA", 0.45), ("MIRCHI_BHAJI", 0.20), ("BREAD_PAKODA", 0.15), ("BHUJIYA", 0.20)]}),
    dict(items=("COLD_COFFEE",), p=0.20, with_=[("BURGER", 0.4), ("CHEESE_BURGER", 0.3), ("SAM_SANDWICH", 0.3)]),
]
COMBO_RULES_TEXT = [
    "fried snack -> tea/coffee (55%, 35% when tmax>=36; cold drink or shikanji when hot)",
    "chaat -> masala cold drink / lemon soda / shikanji / tea (32%)",
    "chole kulcha / vada pav / poha -> tea (45%; lassi or shikanji when hot)",
    "burger -> cold coffee / masala cold drink / shake (38%)",
    "sandwich -> cold coffee / ice tea / chocolate shake (30%)",
    "maggi -> tea, or coffee in the evening (28%); cold drink when hot",
    "tea -> kachori / bread pakoda / poha (morning), samosa / mirchi bhaji (evening), bhujiya 30%",
    "cold coffee -> burger / sandwich (20%)",
]

OVERRIDES = dict(
    STALL={
        "name": "Bhola Redi Canteen",
        "owner": "Mohan Lal Kumawat",               # fictional
        "location": "Near hostel cluster, BITS Pilani campus (fictional redi, real menu card)",
        "open_hour": 9, "close_hour": 19,
        "masked_phone": "******2963", "masked_email": "bhola.redi****@gmail.com",
        "receive_account": "State Bank Of India - 07", "second_account": "Punjab National Bank - 52",
    },
    MENU=MENU, LAUNCHES=LAUNCHES, PRICE_CHANGES=PRICE_CHANGES, MILK_ITEMS=MILK_ITEMS, CURD_ITEMS={"LASSI": .25},
    BATCH_START={"SAMOSA": 150, "DAL_KACHORI": 45, "MIRCHI_BHAJI": 25, "BREAD_PAKODA": 35,
                 "ALOO_BONDA": 20, "MIX_VEG_PAKODA": 15, "POHA": 30, "LASSI": 12},
    STOCK_USES={"SAMOSA_CHAAT": "SAMOSA", "BUTTER_SAM_CHAAT": "SAMOSA", "CHOLE_SAMOSA": "SAMOSA",
                "SAMFRY": "SAMOSA", "SAM_SANDWICH": "SAMOSA",
                "KACHORI_CHAAT": "DAL_KACHORI", "CHOLE_KACHORI": "DAL_KACHORI"},
    SUBSTITUTES=("SAMOSA", "DAL_KACHORI", "MIRCHI_BHAJI", "BREAD_PAKODA", "ALOO_BONDA", "VADA_PAV"),
    ADDONS=ADDONS,
    EXTRA_MILK={"LASSI": 0.25},
    PACKAGED_ITEMS=["BHUJIYA", "MASALA_COLD_DRINK"],
    BAKERY_COST={"VADA_PAV": 4, "BURGER": 8, "CHEESE_BURGER": 8, "PANEER_BURGER": 8, "SAM_SANDWICH": 7,
                 "BUTTER_SANDWICH": 7, "TIKKI_SANDWICH": 7, "PB_SANDWICH": 7, "BREAD_PAKODA": 3,
                 "CHOLE_KULCHA": 6, "CHEESE_CHOLE_KULCHA": 6},
    KULHAD_COST={},
    REMARK_WORDS=REMARK_WORDS, GENERIC_REMARKS=GENERIC_REMARKS, MENU_ALIASES=_aliases(),
    COMBO_RULES_TEXT=COMBO_RULES_TEXT,
)
