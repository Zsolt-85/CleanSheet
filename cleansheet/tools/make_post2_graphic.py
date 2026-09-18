"""Post 2 proof graphic: REAL big-file run rendered in app styling.

Portrait 1080x1350 for LinkedIn feed. All numbers computed live from the
pipeline — never hardcoded. Saved into the Post 2 content folder.
"""

from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from cleaning_engine import load_spreadsheet_from_bytes
from cleaning_engine.modes import build_pipeline

BASE = Path(__file__).resolve().parent.parent

BG = (246, 248, 252)
WHITE = (255, 255, 255)
INK = (15, 30, 51)
MUTED = (91, 107, 130)
LINE = (228, 234, 243)
BRAND = (37, 99, 235)
BRAND_SOFT = (232, 239, 254)
OK = (5, 150, 105)
OK_SOFT = (230, 246, 240)
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


def fmt(n: int) -> str:
    return f"{n:,}"


def main() -> Path:
    raw = (BASE / "tests" / "fixtures" / "input" / "messy_leads_big.csv").read_bytes()
    ss = load_spreadsheet_from_bytes(raw, "messy_leads_big.csv")
    n_before = ss.dataframe.shape[0]
    cleaned, tracker = build_pipeline("default").run(ss)
    n_after = cleaned.dataframe.shape[0]
    applied = tracker.get_applied_changes()
    n_applied = len(applied)
    by_rule = Counter(ch.rule_name for ch in applied)
    n_pending = len(tracker.get_pending_changes())

    rows_removed = n_before - n_after

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # header
    d.rounded_rectangle([40, 26, 84, 70], radius=12, fill=BRAND)
    d.rectangle([52, 36, 72, 44], fill=WHITE)
    d.rectangle([52, 48, 72, 52], fill=WHITE)
    d.rectangle([52, 56, 72, 60], fill=WHITE)
    d.rectangle([58, 36, 62, 60], fill=WHITE)
    d.text((96, 28), "CleanSheet", font=font(30, "ExtraBold"), fill=INK)
    tag = "private beta · real run"
    d.text((W - 40 - d.textlength(tag, font=font(22)), 34), tag, font=font(22), fill=MUTED)

    # headline
    d.text((40, 104), f"{fmt(n_before)} rows in.", font=font(72, "ExtraBold"), fill=INK)
    d.text((40, 192), f"{fmt(n_after)} rows out.", font=font(72, "ExtraBold"), fill=OK)
    d.text(
        (40, 288),
        "Real contact list, default mode, finished in seconds.",
        font=font(25),
        fill=MUTED,
    )

    # before / after cards
    cy, ch = 372, 210
    d.rounded_rectangle([40, cy, 480, cy + ch], radius=18, fill=WHITE, outline=LINE, width=2)
    d.text((70, cy + 18), "BEFORE", font=font(20, "Bold"), fill=MUTED)
    d.text((70, cy + 52), fmt(n_before), font=font(76, "ExtraBold"), fill=INK)
    d.text((70, cy + 146), "rows", font=font(24, "SemiBold"), fill=MUTED)
    d.text((505, cy + 72), "→", font=font(64, "Bold"), fill=BRAND)
    d.rounded_rectangle([600, cy, 1040, cy + ch], radius=18, fill=OK_SOFT, outline=(191, 230, 214), width=2)
    d.text((630, cy + 18), "AFTER", font=font(20, "Bold"), fill=OK)
    d.text((630, cy + 52), fmt(n_after), font=font(76, "ExtraBold"), fill=OK)
    d.text((630, cy + 146), "rows", font=font(24, "SemiBold"), fill=MUTED)
    pill = f"{fmt(rows_removed)} rows removed"
    pw = d.textlength(pill, font=font(20, "Bold"))
    d.rounded_rectangle([(W - pw) / 2 - 16, cy + ch + 14, (W + pw) / 2 + 16, cy + ch + 52], radius=14, fill=BRAND_SOFT)
    d.text(((W - pw) / 2, cy + ch + 20), pill, font=font(20, "Bold"), fill=BRAND)

    # hero stat
    hy = 672
    hero = f"{fmt(n_applied)} changes applied"
    hw = d.textlength(hero, font=font(52, "ExtraBold"))
    d.text(((W - hw) / 2, hy), hero, font=font(52, "ExtraBold"), fill=INK)

    # fix rows (most meaningful first, then biggest)
    picks = [
        ("Exact-duplicate rows removed", by_rule.get("remove_duplicate_rows", 0)),
        ("Duplicate emails removed", by_rule.get("remove_duplicate_emails", 0)),
        ("Capitalization fixed", by_rule.get("normalize_capitalization", 0)),
        ("Phone numbers normalized", by_rule.get("normalize_phones", 0)),
        ("Emails validated", by_rule.get("validate_emails", 0)),
    ]
    y = 772
    for label, count in picks:
        d.rounded_rectangle([40, y, 1040, y + 62], radius=14, fill=WHITE, outline=LINE, width=2)
        d.text((66, y + 16), label, font=font(25, "SemiBold"), fill=INK)
        val = fmt(count)
        vw = d.textlength(val, font=font(27, "ExtraBold"))
        d.text((1014 - vw, y + 14), val, font=font(27, "ExtraBold"), fill=BRAND)
        y += 76

    # differentiator card
    dy = y + 6
    d.rounded_rectangle([40, dy, 1040, dy + 96], radius=16, fill=NAVY)
    line1 = f"{fmt(n_pending)} edge cases flagged for a human —"
    line2 = "never silently guessed."
    d.text((70, dy + 14), line1, font=font(27, "Bold"), fill=WHITE)
    d.text((70, dy + 50), line2, font=font(27), fill=(180, 195, 215))

    # footer
    d.rectangle([0, H - 84, W, H], fill=NAVY)
    foot = "CleanSheet · free private beta · every change logged"
    fw = d.textlength(foot, font=font(24, "SemiBold"))
    d.text(((W - fw) / 2, H - 60), foot, font=font(24, "SemiBold"), fill=WHITE)

    out = BASE / "content" / "2026-09-18-cleansheet-proof-post" / "image.png"
    img.save(out)
    print(f"saved {out} ({W}x{H}) before={n_before} after={n_after} applied={n_applied}")
    return out


if __name__ == "__main__":
    main()
