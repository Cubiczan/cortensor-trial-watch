"""Generate two realistic synthetic statements (fixed seed, fully fictional data)."""
import csv, random
from datetime import date, timedelta

random.seed(5)


def monthly(start, n, day_shift=0):
    d = start
    for _ in range(n):
        yield d
        d = d + timedelta(days=30 + random.choice([0, 1, -1]) + day_shift)


# 1) Chase-style credit card export: Posting Date (MM/DD/YYYY), Description, Amount (negative = spend)
rows = []
s = date(2026, 4, 2)
for i, d in enumerate(monthly(s, 6)):
    rows.append((d, "ADOBE *CREATIVE CLD 800-833-6687", -1.00 if i == 0 else -59.99))   # $1 trial -> paid
for d in monthly(date(2026, 4, 9), 6):
    rows.append((d, "SPOTIFY USA 877-778-1161", -11.99))
for i, d in enumerate(monthly(date(2026, 4, 12), 6)):
    rows.append((d, "OPENAI *CHATGPT SUBSCR", -20.00))
for i, d in enumerate(monthly(date(2026, 4, 15), 6)):
    rows.append((d, "DROPBOX*PLUS 415-857-6800", -11.99 if i < 3 else -14.99))       # price hike
for d in monthly(date(2026, 4, 20), 3):                                                # stopped in June
    rows.append((d, "PELOTON MEMBERSHIP NY", -44.00))
for i in range(0, 182, 7):                                                             # weekly
    rows.append((date(2026, 4, 3) + timedelta(days=i), "NYT DIGITAL WEEKLY", -4.25))
rows.append((date(2026, 5, 1), "AMAZON PRIME ANNUAL", -139.00))
for _ in range(70):
    d = s + timedelta(days=random.randint(0, 186))
    m = random.choice(["WHOLE FOODS MKT #10234", "SHELL OIL 57442", "UBER *TRIP", "STARBUCKS STORE 0921",
                       "TARGET 00012345", "DOORDASH*CHIPOTLE", "CVS/PHARMACY #0441"])
    rows.append((d, m, -round(random.uniform(6, 140), 2)))
for d in monthly(date(2026, 4, 25), 6):
    rows.append((d, "AUTOMATIC PAYMENT - THANK YOU", 650.00))
rows.sort()
with open("samples/chase-style-card.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["Posting Date", "Description", "Amount"])
    for d, desc, amt in rows:
        w.writerow([d.strftime("%m/%d/%Y"), desc, f"{amt:.2f}"])

# 2) Small-business checking export: Date (YYYY/MM/DD), Payee, Debit, Credit
rows = []
s = date(2026, 4, 1)
for i, d in enumerate(monthly(s, 6)):
    rows.append((d, "NOTION LABS INC TEAM", 1.00 if i == 0 else 48.00, ""))            # trial -> team plan
for d in monthly(date(2026, 4, 3), 6):
    rows.append((d, "GOOGLE *WORKSPACE CUBIC", 14.00, ""))
for i, d in enumerate(monthly(date(2026, 4, 5), 6)):
    rows.append((d, "SLACK TECHNOLOGIES", 8.75 if i < 4 else 12.50, ""))               # price hike
for d in monthly(date(2026, 4, 7), 6):
    rows.append((d, "VERCEL INC PRO", 20.00, ""))
for d in monthly(date(2026, 4, 11), 2):                                                # forgotten SaaS
    rows.append((d, "ZOOM.US 888-799-9666", 15.99, ""))
for i, d in enumerate(monthly(date(2026, 4, 14), 6)):
    rows.append((d, "CUSTOMER.IO RECURRING", 1.00 if i < 1 else 100.00, ""))
rows.append((date(2026, 7, 1), "HISCOX INSURANCE QTR", 87.50, ""))
rows.append((date(2026, 9, 30), "HISCOX INSURANCE QTR", 87.50, ""))
for _ in range(25):
    d = s + timedelta(days=random.randint(0, 190))
    m = random.choice(["STAPLES 0042", "FEDEX OFFICE 1123", "AWS EMEA", "DELTA AIR 006", "WEWORK DAY PASS"])
    rows.append((d, m, round(random.uniform(9, 420), 2), ""))
for d in monthly(date(2026, 4, 15), 6):
    rows.append((d, "STRIPE TRANSFER PAYOUT", "", round(random.uniform(3000, 6500), 2)))
rows.sort(key=lambda r: r[0])
with open("samples/smb-checking-debit-credit.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["Date", "Payee", "Debit", "Credit"])
    for d, p, de, cr in rows:
        w.writerow([d.strftime("%Y/%m/%d"), p, f"{de:.2f}" if de != "" else "", f"{cr:.2f}" if cr != "" else ""])
print("wrote samples/chase-style-card.csv and samples/smb-checking-debit-credit.csv")
