"""Generate 10 printable digital products (PDF) in US Letter and A4, plus PNG previews.

Usage: python3 products/generate.py
Output: products/output/<slug>/<slug>-letter.pdf, <slug>-a4.pdf, preview.png
"""

import json
import os
import subprocess

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output")
FONT_DIR = "/usr/share/fonts/truetype/dejavu"

pdfmetrics.registerFont(TTFont("Sans", os.path.join(FONT_DIR, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("Sans-Bold", os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFont(TTFont("Serif-Bold", os.path.join(FONT_DIR, "DejaVuSerif-Bold.ttf")))

INK = HexColor("#2B2B2B")
MUTED = HexColor("#8A8A8A")
RULE = HexColor("#C9C9C9")
MARGIN = 36  # 0.5 inch


class Page:
    """Drawing helpers on one page; y grows downward from the top margin."""

    def __init__(self, c, size, accent, tint):
        self.c, self.w, self.h = c, size[0], size[1]
        self.accent, self.tint = HexColor(accent), HexColor(tint)
        self.left, self.right = MARGIN, self.w - MARGIN
        self.width = self.right - self.left
        self.top, self.bottom = self.h - MARGIN, MARGIN + 14

    def Y(self, y):
        return self.h - y

    def header(self, title, subtitle=None, fields=("DATE",)):
        c = self.c
        c.setFillColor(self.accent)
        c.rect(0, self.h - 8, self.w, 8, stroke=0, fill=1)
        c.setFillColor(INK)
        room = self.width - 145 * len(fields) - 10
        size = 24
        while size > 14 and pdfmetrics.stringWidth(title, "Serif-Bold", size) > room:
            size -= 1
        c.setFont("Serif-Bold", size)
        c.drawString(self.left, self.Y(MARGIN + 26), title)
        if subtitle:
            c.setFillColor(MUTED)
            c.setFont("Sans", 9)
            c.drawString(self.left, self.Y(MARGIN + 42), subtitle)
        x = self.right
        for f in reversed(fields):
            self.field_line(x - 130, MARGIN + 24, 130, f)
            x -= 145
        return MARGIN + 58

    def footer(self, text):
        self.c.setFillColor(MUTED)
        self.c.setFont("Sans", 7)
        self.c.drawCentredString(self.w / 2, MARGIN - 14, text)

    def field_line(self, x, y, w, label):
        c = self.c
        c.setFillColor(MUTED)
        c.setFont("Sans-Bold", 7)
        c.drawString(x, self.Y(y - 4), label)
        c.setStrokeColor(RULE)
        c.setLineWidth(0.7)
        c.line(x, self.Y(y + 10), x + w, self.Y(y + 10))

    def section(self, x, y, w, label):
        c = self.c
        c.setFillColor(self.tint)
        c.roundRect(x, self.Y(y + 18), w, 18, 4, stroke=0, fill=1)
        c.setFillColor(self.accent)
        c.setFont("Sans-Bold", 8.5)
        c.drawString(x + 8, self.Y(y + 12.5), label.upper())
        return y + 24

    def lines(self, x, y, w, n, gap=20, checkbox=False, numbered=False):
        c = self.c
        c.setStrokeColor(RULE)
        c.setLineWidth(0.6)
        for i in range(n):
            ly = y + gap * (i + 1)
            tx = x
            if checkbox:
                c.rect(x + 2, self.Y(ly - 3), 9, 9, stroke=1, fill=0)
                tx = x + 18
            if numbered:
                c.setFillColor(MUTED)
                c.setFont("Sans", 8)
                c.drawString(x, self.Y(ly - 4), f"{i + 1}.")
                tx = x + 16
            c.line(tx, self.Y(ly), x + w, self.Y(ly))
        return y + gap * n + 8

    def box(self, x, y, w, h, label=None, ruled=0):
        c = self.c
        c.setStrokeColor(RULE)
        c.setLineWidth(0.8)
        c.roundRect(x, self.Y(y + h), w, h, 6, stroke=1, fill=0)
        if label:
            c.setFillColor(self.accent)
            c.setFont("Sans-Bold", 8)
            c.drawString(x + 8, self.Y(y + 14), label.upper())
        if ruled:
            ruled = max(ruled, int((h - 24) // 22))
            gap = (h - 24) / ruled
            c.setStrokeColor(RULE)
            c.setLineWidth(0.5)
            for i in range(1, ruled + 1):
                ly = y + 20 + gap * i
                c.line(x + 8, self.Y(ly), x + w - 8, self.Y(ly))
        return y + h

    def table(self, x, y, w, headers, rows, row_h=20, weights=None, first_col=None):
        c = self.c
        weights = weights or [1] * len(headers)
        total = float(sum(weights))
        widths = [w * k / total for k in weights]
        c.setFillColor(self.accent)
        c.rect(x, self.Y(y + row_h), w, row_h, stroke=0, fill=1)
        c.setFillColor(white)
        c.setFont("Sans-Bold", 7.5)
        cx = x
        for head, cw in zip(headers, widths):
            c.drawCentredString(cx + cw / 2, self.Y(y + row_h * 0.65), head)
            cx += cw
        c.setStrokeColor(RULE)
        c.setLineWidth(0.5)
        for r in range(rows):
            ry = y + row_h * (r + 1)
            if r % 2:
                c.setFillColor(self.tint)
                c.rect(x, self.Y(ry + row_h), w, row_h, stroke=0, fill=1)
            if first_col:
                c.setFillColor(INK)
                c.setFont("Sans", 7.5)
                c.drawString(x + 5, self.Y(ry + row_h * 0.65), first_col[r % len(first_col)])
        bottom = y + row_h * (rows + 1)
        for r in range(rows + 2):
            c.line(x, self.Y(y + row_h * r), x + w, self.Y(y + row_h * r))
        cx = x
        for cw in widths + [0]:
            c.line(cx, self.Y(y), cx, self.Y(bottom))
            cx += cw
        return bottom + 10

    def checklist_grid(self, x, y, w, labels, cols, row_h, day_cols):
        """Rows of labels with a box per day (habit / cleaning trackers)."""
        c = self.c
        label_w = w * 0.3
        cell = (w - label_w) / day_cols
        c.setFont("Sans-Bold", 6.5)
        c.setFillColor(self.accent)
        for d in range(day_cols):
            c.drawCentredString(x + label_w + cell * (d + 0.5), self.Y(y + 10), cols[d])
        y += 16
        c.setLineWidth(0.5)
        for i, lab in enumerate(labels):
            ry = y + row_h * i
            if i % 2 == 0:
                c.setFillColor(self.tint)
                c.rect(x, self.Y(ry + row_h), w, row_h, stroke=0, fill=1)
            c.setFillColor(INK)
            c.setFont("Sans", 7.5)
            c.drawString(x + 4, self.Y(ry + row_h * 0.65), lab)
            if not lab:
                c.setStrokeColor(RULE)
                c.line(x + 4, self.Y(ry + row_h - 4), x + label_w - 6, self.Y(ry + row_h - 4))
            for d in range(day_cols):
                s = min(cell, row_h) - 6
                cx = x + label_w + cell * d + (cell - s) / 2
                c.setStrokeColor(MUTED)
                c.circle(cx + s / 2, self.Y(ry + row_h / 2), s / 2, stroke=1, fill=0)
        return y + row_h * len(labels) + 10

    def note(self, x, y, text, size=8):
        self.c.setFillColor(MUTED)
        self.c.setFont("Sans", size)
        self.c.drawString(x, self.Y(y), text)
        return y + size + 6


def two_cols(p, gap=14):
    cw = (p.width - gap) / 2
    return cw, p.left, p.left + cw + gap


# ---------------------------------------------------------------- products


def daily_planner(p):
    y = p.header("Daily Planner", "Plan with intention. Finish with focus.", ("DATE", "DAY"))
    cw, x1, x2 = two_cols(p)
    y0 = y
    p.section(x1, y0, cw, "Schedule")
    yy = y0 + 24
    p.c.setFont("Sans", 7.5)
    hours = range(6, 23)
    gap = (p.h - MARGIN - 20 - yy) / len(hours)
    for i, hour in enumerate(hours):
        ly = yy + gap * (i + 1)
        p.c.setFillColor(MUTED)
        p.c.drawString(x1, p.Y(ly - 5), f"{hour % 12 or 12}{'am' if hour < 12 else 'pm'}")
        p.c.setStrokeColor(RULE)
        p.c.line(x1 + 30, p.Y(ly), x1 + cw, p.Y(ly))
    y2 = p.section(x2, y0, cw, "Top 3 priorities")
    y2 = p.lines(x2, y2, cw, 3, gap=22, numbered=True)
    y2 = p.section(x2, y2, cw, "To do")
    y2 = p.lines(x2, y2, cw, 9, checkbox=True)
    y2 = p.section(x2, y2, cw, "Water")
    for i in range(8):
        p.c.setStrokeColor(p.accent)
        p.c.roundRect(x2 + 6 + i * 30, p.Y(y2 + 22), 18, 22, 3, stroke=1, fill=0)
    y2 += 34
    p.box(x2, y2, cw, p.h - MARGIN - 20 - y2, "Notes & gratitude", ruled=4)
    p.footer("Daily Planner · print as many pages as you need")


def weekly_planner(p):
    y = p.header("Weekly Planner", "One week at a glance.", ("WEEK OF",))
    cw, x1, x2 = two_cols(p)
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "Focus this week"]
    bh = (p.h - MARGIN - 20 - y - 3 * 10) / 4
    for i, d in enumerate(days):
        x = x1 if i % 2 == 0 else x2
        by = y + (i // 2) * (bh + 10)
        p.box(x, by, cw, bh, d, ruled=5)
    p.footer("Weekly Planner")


def budget_planner(p):
    y = p.header("Monthly Budget", "Tell every dollar where to go.", ("MONTH", "YEAR"))
    cw, x1, x2 = two_cols(p)
    y1 = p.section(x1, y, cw, "Income")
    y1 = p.table(x1, y1, cw, ["SOURCE", "EXPECTED", "ACTUAL"], 5, weights=[2, 1, 1])
    y1 = p.section(x1, y1, cw, "Savings & debt")
    y1 = p.table(x1, y1, cw, ["GOAL", "PLANNED", "PAID"], 5, weights=[2, 1, 1])
    y1 = p.section(x1, y1, cw, "Summary")
    p.table(x1, y1, cw, ["", "AMOUNT"], 4, weights=[2, 1],
            first_col=["Total income", "Total expenses", "Savings & debt", "Left over"])
    y2 = p.section(x2, y, cw, "Expenses")
    cats = ["Rent / mortgage", "Utilities", "Phone & internet", "Groceries", "Transport", "Insurance",
            "Subscriptions", "Eating out", "Health", "Clothing", "Gifts", "Fun", "Other", "", "", ""]
    p.table(x2, y2, cw, ["CATEGORY", "BUDGET", "ACTUAL", "DIFF"], len(cats), weights=[2, 1, 1, 1],
            first_col=cats)
    p.footer("Monthly Budget Planner")


def habit_tracker(p):
    y = p.header("Habit Tracker", "Small steps, every day.", ("MONTH",))
    habits = [""] * 15
    p.checklist_grid(p.left, y, p.width, habits, [str(d) for d in range(1, 32)], 22, 31)
    yb = y + 16 + 22 * 15 + 18
    cw, x1, x2 = two_cols(p)
    hb = p.h - MARGIN - 20 - yb
    p.box(x1, yb, cw, hb, "What worked", ruled=4)
    p.box(x2, yb, cw, hb, "Next month I will", ruled=4)
    p.footer("Habit Tracker · write a habit on each line, fill a circle each day you do it")


def meal_planner(p):
    y = p.header("Meal Planner", "Plan the week, shop once.", ("WEEK OF",))
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    y = p.table(p.left, y, p.width, ["", "BREAKFAST", "LUNCH", "DINNER", "SNACKS"], 7, row_h=40,
                weights=[0.6, 2, 2, 2, 1.4], first_col=days)
    y = p.section(p.left, y + 4, p.width, "Grocery list")
    groups = ["Produce", "Protein", "Dairy", "Pantry", "Frozen", "Other"]
    gw = (p.width - 2 * 12) / 3
    gh = (p.h - MARGIN - 20 - y - 10) / 2
    for i, g in enumerate(groups):
        x = p.left + (i % 3) * (gw + 12)
        gy = y + (i // 3) * (gh + 10)
        p.box(x, gy, gw, gh, g)
        p.lines(x + 8, gy + 14, gw - 16, int((gh - 24) // 18), gap=18, checkbox=True)
    p.footer("Meal Planner & Grocery List")


def reading_log(p):
    y = p.header("Reading Log", "Every book you finish, in one place.", ("YEAR",))
    y = p.table(p.left, y, p.width, ["#", "TITLE", "AUTHOR", "GENRE", "PAGES", "FINISHED", "RATING"], 18,
                row_h=22, weights=[0.4, 3, 2, 1.3, 0.8, 1.1, 1.1],
                first_col=[str(i) for i in range(1, 19)])
    cw, x1, x2 = two_cols(p)
    h = p.h - MARGIN - 20 - y
    p.box(x1, y, cw, h, "Books to read next", ruled=5)
    p.box(x2, y, cw, h, "Favourite quotes", ruled=5)
    p.footer("Reading Log · rate with ★ to ★★★★★")


def workout_log(p):
    y = p.header("Workout Log", "Track it to improve it.", ("DATE", "WEEK"))
    y = p.note(p.left, y, "Workout type:  ☐ Strength   ☐ Cardio   ☐ HIIT   ☐ Mobility   ☐ Other ________")
    y = p.table(p.left, y + 4, p.width, ["EXERCISE", "SET 1", "SET 2", "SET 3", "SET 4", "NOTES"], 12,
                row_h=24, weights=[2.4, 1, 1, 1, 1, 2])
    y = p.note(p.left, y, "Write reps × weight in each set (e.g. 10 × 40 kg).", 7)
    y = p.section(p.left, y, p.width, "Cardio")
    y = p.table(p.left, y, p.width, ["ACTIVITY", "TIME", "DISTANCE", "AVG HR", "CALORIES"], 3,
                weights=[2.4, 1, 1, 1, 1])
    cw, x1, x2 = two_cols(p)
    h = p.h - MARGIN - 20 - y
    p.box(x1, y, cw, h, "Energy · sleep · mood", ruled=3)
    p.box(x2, y, cw, h, "Personal bests", ruled=3)
    p.footer("Workout Log")


def goal_planner(p):
    y = p.header("Goal Planner", "Turn a big goal into this week's actions.", ("QUARTER", "DEADLINE"))
    y = p.box(p.left, y, p.width, 60, "My goal (specific & measurable)", ruled=2) + 10
    cw, x1, x2 = two_cols(p)
    p.box(x1, y, cw, 80, "Why it matters", ruled=3)
    p.box(x2, y, cw, 80, "Possible obstacles & fixes", ruled=3)
    y += 90
    y = p.section(p.left, y, p.width, "Milestones")
    y = p.table(p.left, y, p.width, ["MILESTONE", "DUE", "DONE"], 5, weights=[5, 1.2, 0.8])
    y = p.section(p.left, y, p.width, "Weekly actions")
    y = p.table(p.left, y, p.width, ["WEEK", "ACTION", "✓"], 6, weights=[0.8, 5.4, 0.8],
                first_col=[f"Week {i}" for i in range(1, 7)])
    p.box(p.left, y, p.width, p.h - MARGIN - 20 - y, "Reward when I reach it", ruled=2)
    p.footer("Goal Planner")


def debt_tracker(p):
    y = p.header("Debt Payoff Tracker", "Colour in a box for every payment.", ("DEBT", "START DATE"))
    cw, x1, x2 = two_cols(p)
    p.table(x1, y, cw, ["DETAIL", "AMOUNT"], 4, weights=[1.3, 1],
            first_col=["Starting balance", "Interest rate", "Minimum payment", "Target payoff date"])
    p.box(x2, y, cw, 100, "Why I'm paying this off", ruled=3)
    y += 112
    y = p.section(p.left, y, p.width, "Progress — each box = 1/100 of the balance")
    cell = p.width / 20
    p.c.setStrokeColor(p.accent)
    p.c.setLineWidth(0.6)
    for i in range(100):
        p.c.rect(p.left + (i % 20) * cell + 2, p.Y(y + (i // 20) * cell + cell - 2),
                 cell - 4, cell - 4, stroke=1, fill=0)
    y += 5 * cell + 10
    y = p.section(p.left, y, p.width, "Payments")
    rows = int((p.h - MARGIN - 20 - y) // 20) - 2
    p.table(p.left, y, p.width, ["DATE", "PAYMENT", "INTEREST", "NEW BALANCE", "NOTES"], rows,
            weights=[1, 1, 1, 1.2, 2])
    p.footer("Debt Payoff Tracker · one page per debt")


def cleaning_schedule(p):
    y = p.header("Cleaning Schedule", "A tidy home in 15 minutes a day.", ("WEEK OF",))
    days = ["M", "T", "W", "T", "F", "S", "S"]
    y = p.section(p.left, y, p.width, "Daily")
    daily = ["Make beds", "Dishes & wipe counters", "Quick tidy (10 min)", "Laundry load",
             "Check mail & paperwork", "Take out trash if full"]
    y = p.checklist_grid(p.left, y, p.width, daily, days, 20, 7)
    cw, x1, x2 = two_cols(p)
    weekly = ["Vacuum all floors", "Mop kitchen & bath", "Clean toilets", "Clean sinks & mirrors",
              "Change bed sheets", "Dust surfaces", "Wipe appliances", "Empty all bins", "Meal prep & fridge check"]
    monthly = ["Clean oven & microwave", "Wash windows", "Clean inside fridge", "Wipe doors & switches",
               "Wash pillows & throws", "Declutter one drawer", "Clean vents & filters", "Deep clean shower",
               "Vacuum sofa & mattress"]
    ya = p.section(x1, y, cw, "Weekly")
    p.c.setFont("Sans", 8)
    for i, t in enumerate(weekly):
        yy = ya + 20 * i + 14
        p.c.setStrokeColor(MUTED)
        p.c.rect(x1 + 4, p.Y(yy), 9, 9, stroke=1, fill=0)
        p.c.setFillColor(INK)
        p.c.drawString(x1 + 20, p.Y(yy - 1), t)
    yb = p.section(x2, y, cw, "Monthly")
    p.c.setFont("Sans", 8)
    for i, t in enumerate(monthly):
        yy = yb + 20 * i + 14
        p.c.setStrokeColor(MUTED)
        p.c.rect(x2 + 4, p.Y(yy), 9, 9, stroke=1, fill=0)
        p.c.setFillColor(INK)
        p.c.drawString(x2 + 20, p.Y(yy - 1), t)
    y = ya + 20 * len(weekly) + 14
    p.box(p.left, y, p.width, p.h - MARGIN - 20 - y, "Notes / extra tasks", ruled=3)
    p.footer("Cleaning Schedule")


PRODUCTS = [
    ("01-daily-planner", "Daily Planner", "#6C8EAD", "#EEF3F8", [daily_planner]),
    ("02-weekly-planner", "Weekly Planner", "#7A9E7E", "#EEF5EF", [weekly_planner]),
    ("03-monthly-budget-planner", "Monthly Budget Planner", "#C08457", "#FBF1E9", [budget_planner]),
    ("04-habit-tracker", "Habit Tracker", "#9C7CB8", "#F4EFF8", [habit_tracker]),
    ("05-meal-planner-grocery-list", "Meal Planner & Grocery List", "#D08C60", "#FBF0E8", [meal_planner]),
    ("06-reading-log", "Reading Log", "#8B6F5C", "#F5F0EC", [reading_log]),
    ("07-workout-log", "Workout Log", "#4F8A8B", "#EAF4F4", [workout_log]),
    ("08-goal-planner", "Goal Planner", "#C9A227", "#FBF6E4", [goal_planner]),
    ("09-debt-payoff-tracker", "Debt Payoff Tracker", "#5B7DB1", "#EDF2F9", [debt_tracker]),
    ("10-cleaning-schedule", "Cleaning Schedule", "#5FA59A", "#EAF5F3", [cleaning_schedule]),
]


def build(slug, title, accent, tint, pages, size, suffix):
    folder = os.path.join(OUT, slug)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{slug}-{suffix}.pdf")
    c = canvas.Canvas(path, pagesize=size)
    c.setTitle(title)
    c.setAuthor("Produkty cyfrowe z Claude")
    c.setSubject(f"Printable {title}")
    for draw in pages:
        draw(Page(c, size, accent, tint))
        c.showPage()
    c.save()
    return path


DESCRIPTION = """{hook}

WHAT YOU GET
• 1 PDF in US Letter (8.5 x 11 in)
• 1 PDF in A4 (210 x 297 mm)
• Clean, minimalist design that saves printer ink

HOW IT WORKS
1. Buy and download the files instantly from your purchases page.
2. Print at home or at a print shop, as many times as you like for personal use.
3. Fill it in by hand, or use it in a note-taking app (GoodNotes, Notability, Xodo).

PLEASE NOTE
• This is a digital download. No physical item will be shipped.
• Colours may look slightly different depending on your screen and printer.
• For personal use only. Reselling or sharing the files is not permitted."""


def write_listings():
    """Validate listings.json against Etsy limits and render LISTINGS.md."""
    with open(os.path.join(HERE, "listings.json")) as f:
        listings = json.load(f)
    out = ["# Listings (Etsy / Shopify)", "",
           "Generated from `listings.json` by `generate.py`. Copy each block into the listing form.", ""]
    for item in listings:
        assert len(item["title"]) <= 140, item["slug"]
        assert len(item["tags"]) == 13 and len(set(item["tags"])) == 13, item["slug"]
        assert all(len(t) <= 20 for t in item["tags"]), item["slug"]
        out += [f"## {item['slug']}", "",
                f"![preview](output/{item['slug']}/preview.png)", "",
                f"**Title** ({len(item['title'])}/140)", "", item["title"], "",
                f"**Price:** ${item['price_usd']:.2f}", "",
                "**Tags:** " + ", ".join(item["tags"]), "",
                "**Description**", "", "```", DESCRIPTION.format(hook=item["hook"]), "```", "",
                f"**Files:** `output/{item['slug']}/{item['slug']}-letter.pdf`, "
                f"`output/{item['slug']}/{item['slug']}-a4.pdf`", ""]
    with open(os.path.join(HERE, "LISTINGS.md"), "w") as f:
        f.write("\n".join(out))


def main():
    for slug, title, accent, tint, pages in PRODUCTS:
        letter = build(slug, title, accent, tint, pages, LETTER, "letter")
        build(slug, title, accent, tint, pages, A4, "a4")
        preview = os.path.join(OUT, slug, "preview")
        subprocess.run(["pdftoppm", "-png", "-r", "60", "-singlefile", letter, preview], check=True)
        print("built", slug)
    write_listings()


if __name__ == "__main__":
    main()
