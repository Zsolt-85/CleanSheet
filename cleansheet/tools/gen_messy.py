"""Generate a realistic messy lead-list CSV for manual upload testing."""

import csv
import random

random.seed(20260912)

firsts = ["John", "Maria", "Andrei", "Elena", "Bob", "Alice", "Vlad", "Ioana", "David", "Grace"]
lasts = ["Smith", "Popescu", "Ionescu", "Stan", "Wilson", "Brown", "Dumitru", "Marin", "Lee", "Hall"]
companies = ["Acme Ltd.", "Globex Corp", "Initech", "Hooli", "Umbrella Corp", "Stark Industries"]
domains = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "company.com"]
typo_domains = ["gmial.com", "yaho.com", "hotmial.com", "outlok.com"]
dates = ["2026-03-04", "03/04/2026", "March 4, 2026", "2026-05-19", "05/19/2026", "2026-07-02"]

rows = [["First Name", "Last Name", "Email", "Company", "Phone", "Signup Date", "Status"]]

base_people = []
for i in range(25):
    fn, ln = random.choice(firsts), random.choice(lasts)
    base_people.append(
        [fn, ln, f"{fn.lower()}.{ln.lower()}@{random.choice(domains)}",
         random.choice(companies), f"555-{random.randint(1000, 9999)}",
         random.choice(dates), random.choice(["Active", "Inactive", "Pending"])]
    )

for p in base_people:
    r = list(p)
    roll = random.random()
    if roll < 0.25:  # ALL CAPS row
        r = [c.upper() for c in r]
    elif roll < 0.45:  # all lowercase row
        r = [c.lower() for c in r]
    if random.random() < 0.3:  # padding whitespace
        j = random.randrange(len(r))
        r[j] = "  " + r[j] + " "
    if random.random() < 0.2:  # email typo domain
        local = r[2].split("@")[0]
        r[2] = local + "@" + random.choice(typo_domains)
    if random.random() < 0.12:  # broken email
        r[2] = random.choice([r[2].replace("@", ""), r[2] + "@", "not-an-email"])
    rows.append(r)
    if random.random() < 0.3:  # exact duplicate row
        rows.append(list(r))
    if random.random() < 0.15:  # same email, different casing/row
        dup = list(r)
        dup[2] = dup[2].upper()
        rows.append(dup)

rows.append(["", "", "", "", "", "", ""])  # empty row
rows.append(["  ", " ", "", "   ", "", "", ""])  # whitespace-only row

out = r"C:\Users\maias\Desktop\messy_leads_test.csv"
with open(out, "w", newline="", encoding="utf-8") as f:
    csv.writer(f).writerows(rows)

print(f"wrote {out} ({len(rows) - 1} data rows)")
