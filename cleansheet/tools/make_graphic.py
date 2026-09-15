"""Before/after LinkedIn graphic from the REAL test file + REAL pipeline counts."""

import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from cleaning_engine import create_default_pipeline, load_spreadsheet

W, H = 1200, 627
BG = (246, 248, 252)
WHITE = (255, 255, 255)
INK = (15, 30, 51)
MUTED = (91, 107, 130)
BRAND = (37, 99, 235)
RED_BG, RED_BD, RED_TX = (253, 240, 240), (240, 202, 202), (185, 28, 28)
GRN_BG, GRN_BD, GRN_TX = (234, 250, 243), (191, 230, 214), (5, 105, 90)
NAVY = (15, 30, 51)

FONTS = Path(r"C:\Windows\Fonts")


def font(name: str, size: int):
    try:
        return ImageFont.truetype(str(FONTS / name), size)
    except OSError:
        return ImageFont.load_default()


F_TITLE = font("arialbd.ttf", 54)
F_SUB = font("arial.ttf", 24)
F_HEAD = font("arialbd.ttf", 26)
F_ROW = font("arial.ttf", 21)
F_PILL = font("arialbd.ttf", 15)
F_STAT = font("arialbd.ttf", 30)
F_BRAND = font("arialbd.ttf", 28)


def pill(draw, xy, text: str, bg, fg):
    x, y = xy
    w = draw.textlength(text, font=F_PILL) + 20
    draw.rounded_rectangle([x, y, x + w, y + 26], radius=13, fill=bg)
    draw.text((x + 10, y + 4), text, font=F_PILL, fill=fg)
    return w


def mess_score(row: dict) -> int:
    s = 0
    for v in row.values():
        if v != v.strip():
            s += 2
        if v.isupper() and len(v) > 2:
            s += 2
        if v.islower() and "@" in v:
            s += 1
    if "gmial" in row.get("Email", "") or "yaho" in row.get("Email", ""):
        s += 3
    if row.get("Email", "") in ("not-an-email",) or "@" not in row.get("Email", ""):
        s += 3
    return s


BASE = Path(__file__).resolve().parent.parent
src = BASE / "tests" / "fixtures" / "input" / "messy_leads_demo.csv"
data = load_spreadsheet(src)
cleaned, tracker = create_default_pipeline().run(data)
report = tracker.to_report()
applied = sum(1 for c in report.changes if c.applied)
n_before, n_after = data.dataframe.shape[0], cleaned.dataframe.shape[0]

raw_rows = list(data.dataframe.to_dict("records"))
nonempty = [r for r in raw_rows if any(str(v).strip() for v in r.values())]
messy = sorted(nonempty, key=mess_score, reverse=True)[:4]
clean_rows = cleaned.dataframe.head(4).to_dict("records")


_MEASURER = Image.new("RGB", (8, 8))
_MEASURE = ImageDraw.Draw(_MEASURER)


def _fit(text: str, max_px: int) -> str:
    full = len(text)
    while text and _MEASURE.textlength(text, font=F_ROW) > max_px:
        text = text[:-1]
    text = text.rstrip()
    return text + "…" if len(text) < full else text


def short_person(r: dict) -> str:
    fn = r.get("First Name", "?")[:12]
    ln = r.get("Last Name", "?")[:12]
    em = r.get("Email", "?")[:26]
    co = r.get("Company", "?")[:16]
    return _fit(f"{fn} {ln} | {em} | {co}", 440)


def badges(r: dict) -> list[str]:
    out = []
    em = r.get("Email", "")
    if "@" not in em or em.endswith("@") or " " in em.strip().rstrip("@"):
        out.append("BAD EMAIL")
    if any(v != v.strip() for v in r.values()):
        out.append("SPACES")
    if any(v.isupper() and len(v) > 2 for v in r.values()):
        out.append("ALL CAPS")
    if any(d in em for d in ("gmial", "yaho", "hotmial", "outlok", "gmal")):
        out.append("TYPO")
    return out[:2]


img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

# header
d.rectangle([0, 0, W, 84], fill=WHITE)
d.text((40, 24), "CleanSheet", font=F_BRAND, fill=INK)
d.text((880, 30), "cleansheet · private beta", font=F_SUB, fill=MUTED)

# title
d.text((40, 108), "Messy in. Clean out.", font=F_TITLE, fill=INK)
d.text((40, 172), f"Real file, real run: {n_before} rows in, {n_after} out, {applied} changes logged.",
       font=F_SUB, fill=MUTED)

# panels
PW, PH, PY = 505, 300, 230
for (px, title, bg, bd, tx) in ((40, "BEFORE", RED_BG, RED_BD, RED_TX),
                                (655, "AFTER", GRN_BG, GRN_BD, GRN_TX)):
    d.rounded_rectangle([px, PY, px + PW, PY + PH], radius=16, fill=bg, outline=bd, width=2)
    d.text((px + 20, PY + 12), title, font=F_HEAD, fill=tx)

# center arrow
d.text((578, 340), "→", font=font("arialbd.ttf", 64), fill=BRAND)

# before rows
y = PY + 52
for r in messy:
    line = short_person(r)[:52]
    d.text((60, y), line, font=F_ROW, fill=INK)
    x = 60
    for b in badges(r):
        w = pill(d, (x, y + 26), b, (255, 255, 255), RED_TX)
        x += w + 8
    y += 58
    if y > PY + PH - 40:
        break

# after rows
y = PY + 52
for r in clean_rows:
    line = short_person(r)[:52]
    d.text((675, y), line, font=F_ROW, fill=INK)
    pill(d, (675, y + 26), "FIXED + LOGGED", WHITE, GRN_TX)
    y += 58

# footer stats band
d.rectangle([0, H - 88, W, H], fill=NAVY)
stat = f"{n_before} rows in  →  {n_after} rows out   ·   {applied} changes applied   ·   every change logged"
tw = d.textlength(stat, font=F_STAT)
d.text(((W - tw) / 2, H - 66), stat, font=F_STAT, fill=WHITE)

out = BASE / "assets" / "cleansheet_before_after.png"
img.save(out)
print(f"saved {out} ({W}x{H}), before={n_before} after={n_after} applied={applied}")
