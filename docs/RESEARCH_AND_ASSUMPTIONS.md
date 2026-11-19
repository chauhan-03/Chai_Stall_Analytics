# Research and modelling assumptions

Every behaviour in the synthetic data is listed here with its source or the reason it was assumed.
Values live in `src/generator/config.py`; change them and rerun the generator.

Confidence: **H** = from a cited source, **M** = from sources with conflicts or adjacent evidence,
**A** = assumption (reasonable, unverified).

## Statement format (H)

Copied from a real Paytm UPI statement (Nov 2025 – Nov 2026), structure only. No values, names or
IDs from it are used. Two sheets: `Summary` and `Passbook Payment History` with 11 columns:
`Date | Time | Transaction Details | Other Transaction Details (UPI ID or A/c No) | Your Account | Amount |
UPI Ref No. | Order ID | Remarks | Tags | Comment`.

Real quirks reproduced:
- `+1,500.00` / `-50.00` amount strings with thousands separators
- `Received from <name>` for incoming money, a bare name for CRED payers (account `Other UPI App - CRED`)
- UPI IDs suffixed with the app (`… on PhonePe`), phone handles masked as `******1234@ybl`
- names in KYC capitals, with double spaces or with surnames truncated
- UPI reference numbers that start with year digit + day of year (`6319…` = 15 Nov 2026)
- emoji tags (`#💵 Money Received`, `#🛒 Groceries`, `#💵 Self Transfer`)
- self-transfers excluded from summary totals

## Campus calendar, BITS Pilani 2025-26 (M)

| Event | Dates used | Basis |
|---|---|---|
| Sem I compre | 1–16 Dec 2025 | BITS-UB / BITS-ISU calendars (H) |
| Winter break | 17 Dec 2025 – 4 Jan 2026 | BITS-UB lists 18 Dec – 4 Jan (H); Pilani start date approximate |
| Sem II mid-sems | 9–14 Mar 2026 | BITS-ISU (H), RMIT lists 8–15 Mar |
| Sem II compre ends | 16 May 2026 | BITS-UB (H) |
| Summer term | May – Jul 2026 | Pilani summer timetable: midsem 18–20 Jun, compre 15–18 Jul (H) |
| Holi | 3–5 Mar 2026 | festival date (H) |
| APOGEE | 2–5 Apr 2026 | APOGEE 2024 started 4 Apr; 2026 dates not found (A) |
| BOSM | 17–20 Sep 2026 | usually mid-September (M) |
| Oasis | 29 Oct – 1 Nov 2026 | Oasis 2025 ended 11 Nov; 2026 dates not found (A) |
| Sem I 2026-27 start | 1 Aug 2026 | assumed (A) |
| Diwali | 8 Nov 2026 | festival date (H) |

**Replace with the official Pilani calendar** if available: edit `CALENDAR` in `config.py` or
`data/raw/campus_calendar.csv` for the pipeline.

## Climate, Pilani (M)

Semi-arid (Köppen BSh). January is the coldest month (avg ~13.5 °C, lows ~6 °C), May–June the hottest
(highs 40–45 °C; 47.2 °C recorded on 22 May 2024). July is the wettest (~127 mm); annual ~540 mm,
mostly July–September; November is driest. Sources disagree on exact means, so monthly targets are
approximate. Fog in late Dec – Jan is assumed (A).

## Payments (M)

- **UPI app shares** (H): NPCI 2025 volume shares were PhonePe ~46%, Google Pay ~35.5%, Paytm ~7%, with
  Navi and super.money growing. Students are assumed to skew slightly to Google Pay.
- **Merchant ticket size** (H): average P2M UPI ticket ₹589–592 in 2025, falling as small payments
  digitise; ~85% of transactions are under ₹500. A ₹45–55 chai-stall ticket is consistent.
- **Cash share** (M): no survey measures tea stalls specifically. Evidence: 94% of small merchants accept
  UPI; RBI estimates cash at 50–60% of household spend overall; some vendors moved back to cash in 2025
  over GST-notice fears. The model uses ~23% cash for a campus stall (students mostly pay UPI) and falls
  22% over the year. Small bills (≤₹15) are more often cash. The pipeline assumes 25% (range 18–32%).
- **UPI outages** (H): real outages on 26 Mar, 2 Apr and 12 Apr 2025 (one to three hours, evenings).
  Three synthetic outages are placed in 2026.

## Stall economics (M)

- Chai cost ₹4.5–11 per cup against ₹10–30 prices, a 50–70% gross margin (industry write-ups; kulhad chai
  ~₹7 cost / ₹15 price, roughly 52% margin).
- Well-located stalls take ₹2,000–5,000 a day (street) to ~₹5,000 (busy roadside). A campus stall
  serving ~2,400 students is set at ~₹11.5k a day in term and ~₹3k in vacations (A).
- Milk ₹56 a litre, rising ~6% in April (typical dairy revision, A). A 19 kg commercial LPG cylinder is
  ~₹1,750–1,800 (A).
- Prices are typical of North Indian campus canteens (an IIT Mandi list shows samosa ₹10, maggi ₹20–35;
  Pilani menus are unpublished). Rajasthani items (pyaaz kachori, mirchi bada) are included (A).

## Behaviour baked into the simulation (A, documented so the pipeline can be scored)

| Effect | How |
|---|---|
| Habitual customers | 2,400 students + 140 staff; lognormal visit rates (a few heavy regulars) |
| Opening hours | 09:00–19:00 daily; every statement row falls inside these hours |
| Chronotypes | early birds, normal, night owls (come late in the day); exam weeks and fests push demand into 17:00–19:00 |
| Cohort churn | 22% of students graduate after May compre; 26% freshers join in August |
| Breaks | only 12% (winter) / 20% (summer) of students stay; staff mostly stay |
| Fests | outsider footfall x7, bigger groups, more cold drinks and sandwiches |
| Weather | heat raises cold drinks, cuts hot items and afternoon footfall; rain lifts fried snacks and chai; fog lifts morning chai |
| Complements | fried snack → chai, poha/omelette → chai, sandwich → cold coffee, maggi → coffee after 17:00 |
| Combo SKU | Chai Samosa Combo ₹25 from 1 Feb 2026 replaces 75% of masala chai + samosa pairs |
| Price elasticity | maggi 1.4, others 0.8 (true values, for scoring the estimator) |
| Price changes | Kulhad ₹25→30 (15 Jan), Maggi ₹40→50 and Masala Maggi ₹55→60 (1 Sep) |
| Launch | Cold Coffee from 15 Mar 2026 |
| Batches & stockouts | owner preps fried snacks/poha/lassi by a "last 2 same weekdays x1.22" habit; sell-outs lose or substitute sales |
| Competitor | second tea stall opens nearby 21 Sep 2026: evening (16:00–19:00) demand x0.72, rest of day x0.95 |
| Payment noise | split bills, duplicate payments + refunds, typo payments (₹450 for ₹45) + partial refund, deferred payments after outages, customer remarks in ~5% of payments |
| Owner's own rows | dairy, gas, kirana, bakery, distributor, kulhad supplier, licence fee, electricity, helper wages, family transfers, recharges, weekly self-transfers, money from relatives, cashback |

## Sources

- [BITS-UB academic calendar](https://admissions.bits-pilani.ac.in/BITS-UB/downloads/BITS-UB_AcademicCalendar.pdf)
- [BITS-ISU academic calendar](https://admissions.bits-pilani.ac.in/BITS-ISU/downloads/BITS-ISU_AcademicCalendar.pdf)
- [BITS-RMIT academic calendar](https://admissions.bits-pilani.ac.in/BITS-RMIT/downloads/BITS-RMIT_AcademicCalendar.pdf)
- [BITS Pilani Sem II 2025-26 timetable](https://www.bits-pilani.ac.in/wp-content/uploads/ACADEMIC-CALENDER-TIMETABLE-II-SEMESTER-2025-26.pdf)
- [Pilani summer term timetable 2026](https://academic.bits-pilani.ac.in/Downloads/Summer_Term/Summer_Term_Timetable_06_Jun_2026_42c36337-53f0-4478-a157-46b734080f60.pdf)
- [Oasis 2025 coverage](https://youthincmag.com/oasis-2025-celebrates-cultural-excellence-student-creativity-and-24x4-fest-spirit-at-bits-pilani), [BOSM](https://en.wikipedia.org/wiki/BOSM)
- [Pilani climate (climate-data.org)](https://en.climate-data.org/asia/india/rajasthan/pilani-24741/), [Pilani (Wikipedia)](https://wikiwand.com/en/articles/Pilani)
- [UPI market share June 2025 (Business Standard)](https://www.business-standard.com/amp/companies/start-ups/phonepe-market-share-upi-46-46-percent-june-125071101033_1.html), [July 2025](https://www.business-standard.com/amp/companies/news/phonepe-processes-9-bn-upi-transactions-in-july-125081401462_1.html), [December 2025](https://www.angelone.in/news/economy/phonepe-and-google-pay-lead-upi-ecosystem-in-december-2025)
- [Worldline India Digital Payments 2025](https://worldline.com/en-in/home/top-navigation/media-relations/press-releases/worldline-reports-that-india-digital-payments-cross-new-milestones-as-upi-reaches-228-billion-transactions-in-2025), [Worldline 1H 2025 report](https://worldline.com/content/dam/worldline/local/en-in/documents/main-page11111/Worldline-India-Digital-Payment-Report-1H-2025-1.pdf)
- [Bengaluru vendors return to cash (Business Standard)](https://www.business-standard.com/finance/news/bengaluru-vendors-abandon-upi-opt-for-cash-amid-gst-fears-125071600953_1.html), [ISB street-vendor survey (Deccan Chronicle)](https://www.deccanchronicle.com/amp/southern-states/telangana/mdr-on-upi-payments-likely-to-force-street-vendors-to-switch-to-cash-says-isb-survey-2002380), [Retail payments in India (Data for India)](https://www.dataforindia.com/retail-payments/)
- [UPI outages 2025 (Outlook Business)](https://www.outlookbusiness.com/news/upi-outage-restored-google-pay-phonepe-transactions-fail-for-over-an-hour), [third outage in a fortnight (Hitavada)](https://www.thehitavada.com/Encyc/2025/4/13/UPI-faces-third-outage-in-less-than-a-fortnight.html)
- [Tea stall economics (Business Today)](https://www.businesstoday.in/visualstories/money/how-one-tea-stall-can-earn-18-lakh-a-year-the-simple-math-behind-it-236034-23-05-2025), [chai per-cup costs (Think Tank)](https://think-tank-55e4a2.beehiiv.com/p/india-runs-on-chai-but-who-s-building-the-starbucks-of-it), [chai tapri margins (DineOpen)](https://www.dineopen.com/blog/how-to-start-chai-tapri-business)
- [IIT Mandi canteen price list](https://intranet.iitmandi.ac.in/notifications/2462/view)
