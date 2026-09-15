"""Paired before/after LinkedIn montage from REAL file + REAL pipeline run.

Same records on both sides (matched by name key), changed fields highlighted,
site palette + Inter, portrait 1080x1350 for feed presence.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from cleaning_engine import create_default_pipeline, load_spreadsheet

BASE = Path(__file__).resolve().parent.parent

# ---- site palette ----
BG = (246, 248, 252)
WHITE = (255, 255, 255)
INK = (15, 30, 51)
MUTED = (91, 107, 130)
LINE = (228, 234, 243)
BRAND = (37, 99, 235)
OK = (5, 150, 105)
OK_SOFT = (230, 246, 240)
ERR = (220, 38, 38)
ERR_SOFT = (253, 240, 240)
NAVY = (15, 30, 51)

W, H = 1080, 1350
INTER = BASE / "assets" / "fonts" / "Inter.ttf"
_cache: dict = {}


def font(size: int, weight: str = "Regular"):
    key = (size, weight)
    if key not in _cache:
        f = ImageFont.truetype(str(INTER), size)
        try:
            f.set_variation_by_name(weight.encode())
        except Exception:
            pass
        _cache[key] = f
    return _cache[key]


F_TITLE = lambda: font(66, "ExtraBold")  # noqa: E731
F_SUB = lambda: font(25, "Regular")  # noqa: E731
F_BRAND = lambda: font(30, "ExtraBold")  # noqa: E731
F_TAG = lambda: font(22, "Regular")  # noqa: E731
F_REF = lambda: font(16, "SemiBold")  # noqa: E731
F_NAME = lambda: font(25, "Bold")  # noqa: E731
F_FIELD = lambda: font(21, "Regular")  # noqa: E731
F_FIX = lambda: font(17, "Bold")  # noqa: E731
F_STAT = lambda: font(29, "Bold")  # noqa: E731

FIELDS = ["Name", "Email", "Company"]


def name_of(r: dict) -> str:
    return f"{r.get('First Name', '').strip()} {r.get('Last Name', '').strip()}".strip()


def key_of(r: dict) -> tuple:
    return (r.get("First Name", "").strip().lower(), r.get("Last Name", "").strip().lower())


def shown(r: dict) -> dict:
    return {
        "Name": name_of(r) or "—",
        "Email": r.get("Email", "").strip() or "—",
        "Company": r.get("Company", "").strip() or "—",
    }


def main() -> Path:
    data = load_spreadsheet(BASE / "tests" / "fixtures" / "input" / "messy_leads_demo.csv")
    cleaned, tracker = create_default_pipeline().run(data)
    report = tracker.to_report()
    applied = sum(1 for c in report.changes if c.applied)
    n_before, n_after = data.dataframe.shape[0], cleaned.dataframe.shape[0]

    raw_rows = list(data.dataframe.to_dict("records"))
    clean_rows = list(cleaned.dataframe.to_dict("records"))
    clean_by_key: dict = {}
    for r in clean_rows:
        k = key_of(r)
        if k != ("", "") and k not in clean_by_key:
            clean_by_key[k] = r

    pairs = []
    used = set()
    for j, m in enumerate(raw_rows):
        k = key_of(m)
        if k == ("", "") or k not in clean_by_key or k in used:
            continue
        used.add(k)
        c = clean_by_key[k]
        sm, sc = shown(m), shown(c)
        diffs = [f for f in FIELDS if sm[f] != sc[f]]
        if diffs:
            pairs.append((len(diffs), j + 2, sm, sc, diffs))
    pairs.sort(reverse=True)
    pairs = pairs[:5]

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # header
    d.rounded_rectangle([40, 26, 84, 70], radius=12, fill=BRAND)
    d.rectangle([52, 36, 72, 44], fill=WHITE)
    d.rectangle([52, 48, 72, 52], fill=WHITE)
    d.rectangle([52, 56, 72, 60], fill=WHITE)
    d.rectangle([58, 36, 62, 60], fill=WHITE)
    d.text((96, 28), "CleanSheet", font=F_BRAND(), fill=INK)
    tag = "private beta"
    d.text((W - 40 - d.textlength(tag, font=F_TAG()), 34), tag, font=F_TAG(), fill=MUTED)

    # title
    d.text((40, 104), "Messy in. Clean out.", font=F_TITLE(), fill=INK)
    d.text(
        (40, 184),
        "Same 5 records, before and after. Real file, real run.",
        font=F_SUB(),
        fill=MUTED,
    )

    # pairs
    y = 252
    LW, CW = 460, 460
    LX, RX = 40, 580
    AX = 500  # arrow column center
    for _ndiffs, rownum, sm, sc, diffs in pairs:
        # before card
        d.rounded_rectangle([LX, y, LX + LW, y + 158], radius=14, fill=WHITE, outline=LINE, width=2)
        d.text((LX + 18, y + 10), f"BEFORE · CSV ROW {rownum}", font=F_REF(), fill=ERR)
        d.text((LX + 18, y + 36), sm["Name"][:34], font=F_NAME(), fill=INK)
        d.text((LX + 18, y + 70), sm["Email"][:36], font=F_FIELD(), fill=MUTED)
        d.text((LX + 18, y + 100), sm["Company"][:36], font=F_FIELD(), fill=MUTED)
        # arrow + fix count
        d.text((AX - 16, y + 52), "→", font=font(44, "Bold"), fill=BRAND)
        label = f"{len(diffs)} fix" + ("es" if len(diffs) > 1 else "")
        tw = d.textlength(label, font=F_FIX())
        d.rounded_rectangle([AX - tw / 2 - 10, y + 108, AX + tw / 2 + 10, y + 132], radius=12, fill=(232, 239, 254))
        d.text((AX - tw / 2, y + 110), label, font=F_FIX(), fill=BRAND)
        # after card
        d.rounded_rectangle([RX, y, RX + CW, y + 158], radius=14, fill=WHITE, outline=LINE, width=2)
        d.text((RX + 18, y + 10), "AFTER", font=F_REF(), fill=OK)
        name_val = sc["Name"][:34]
        if "Name" in diffs:
            w = d.textlength(name_val, font=F_NAME())
            d.rounded_rectangle(
                [RX + 12, y + 33, RX + 24 + w, y + 63], radius=8, fill=OK_SOFT
            )
        d.text((RX + 18, y + 36), name_val, font=F_NAME(), fill=INK)
        for i, f in enumerate(("Email", "Company")):
            tx, ty = RX + 18, y + 70 + i * 30
            val = sc[f][:36]
            if f in diffs:
                w = d.textlength(val, font=F_FIELD())
                d.rounded_rectangle([tx - 6, ty - 3, tx + w + 6, ty + 25], radius=8, fill=OK_SOFT)
            d.text((tx, ty), val, font=F_FIELD(), fill=MUTED)
        y += 178

    # footer stats band
    d.rectangle([0, H - 96, W, H], fill=NAVY)
    stat = f"{n_before} rows in  →  {n_after} rows out   ·   {applied} changes applied   ·   every change logged"
    tw = d.textlength(stat, font=F_STAT())
    d.text(((W - tw) / 2, H - 68), stat, font=F_STAT(), fill=WHITE)

    out = BASE / "assets" / "cleansheet_before_after.png"
    img.save(out)
    print(f"saved {out} ({W}x{H}), pairs={len(pairs)}, before={n_before} after={n_after} applied={applied}")
    return out


if __name__ == "__main__":
    main()
