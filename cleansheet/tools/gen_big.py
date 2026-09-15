"""Generate a large messy lead-list CSV for stress testing."""

import csv
import random

random.seed(20260913)
N = 3000

firsts = ["John", "Maria", "Andrei", "Elena", "Bob", "Alice", "Vlad", "Ioana", "David",
          "Grace", "Mihai", "Ana", "Radu", "Simona", "Cristi", "Diana", "Florin", "Gina"]
lasts = ["Smith", "Popescu", "Ionescu", "Stan", "Wilson", "Brown", "Dumitru", "Marin",
         "Lee", "Hall", "Constantin", "Florescu", "Georgescu", "Iliescu", "Voicu", "Stoica"]
companies = ["Acme Ltd.", "Globex Corp", "Initech", "Hooli", "Umbrella Corp",
             "Stark Industries", "Massive Dynamic", "Tyrell Corp", "Oscorp", "Pied Piper"]
domains = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "company.com", "aol.com"]
typo_domains = ["gmial.com", "yaho.com", "hotmial.com", "outlok.com", "gmal.com"]
dates = ["2026-01-15", "01/15/2026", "January 15, 2026", "2026-03-04", "03/04/2026",
         "2026-05-19", "05/19/2026", "2026-07-02", "2026-11-11", "11/11/2026"]
statuses = ["Active", "Inactive", "Pending"]
markers = ["N/A", "NULL", "-", "none", ""]

rows = [["First Name", "Last Name", "Email", "Company", "Phone", "Signup Date", "Status", "Notes"]]
pool = []
for _ in range(N):
    fn, ln = random.choice(firsts), random.choice(lasts)
    pool.append([
        fn, ln,
        f"{fn.lower()}.{ln.lower()}{random.randint(1, 9999)}@{random.choice(domains)}",
        random.choice(companies),
        f"555-{random.randint(1000, 9999)}",
        random.choice(dates),
        random.choice(statuses),
        random.choice(["New lead", "Called twice", "VIP", "Referred", ""]),
    ])

for p in pool:
    r = list(p)
    roll = random.random()
    if roll < 0.18:
        r = [c.upper() for c in r]
    elif roll < 0.36:
        r = [c.lower() for c in r]
    if random.random() < 0.25:
        j = random.randrange(len(r))
        r[j] = "  " + r[j] + "  "
    if random.random() < 0.12:
        r[2] = r[2].split("@")[0] + "@" + random.choice(typo_domains)
    if random.random() < 0.05:
        r[2] = random.choice([r[2].replace("@", ""), r[2] + "@", "not-an-email"])
    if random.random() < 0.10:
        j = random.randrange(len(r))
        r[j] = random.choice(markers)
    rows.append(r)
    if random.random() < 0.18:
        rows.append(list(r))  # exact duplicate
    if random.random() < 0.08:
        dup = list(r)  # same email, different case
        dup[2] = dup[2].upper()
        rows.append(dup)

rows.append(["", "", "", "", "", "", "", ""])
rows.append(["N/A", "-", "NULL", "n/a", "--", "none", "", "N/A"])

out = r"C:\Users\maias\Desktop\messy_leads_BIG.csv"
with open(out, "w", newline="", encoding="utf-8") as f:
    csv.writer(f).writerows(rows)

print(f"wrote {out} ({len(rows) - 1} data rows)")
