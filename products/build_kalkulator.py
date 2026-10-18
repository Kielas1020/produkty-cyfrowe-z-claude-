"""Buduje content/output/produkt_A/kalkulator_cytaty.xlsx.

Kalkulator wycen dla firm pressure washing + gutter cleaning (rynek US, USD).
Zakładki: START (wejścia i wynik), RATES (stawki + źródła), CALC (obliczenia),
COPY (gotowy tekst wyceny dla klienta). Wszystko na prawdziwych formułach.

    python3 products/build_kalkulator.py [ścieżka.xlsx]
"""
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule

OUT = Path(__file__).resolve().parent.parent / "content/output/produkt_A/kalkulator_cytaty.xlsx"

# Wartości startowe = scenariusz pokazowy (zrzut nr 1 w listing_etsy.md).
DEFAULT_INPUTS = {
    "customer": "Sample Customer",
    "driveway": 600,
    "house": 1800,
    "roof": 0,
    "gutters": 150,
    "stories": 2,
    "tier": "MID",
    "miles": 15,
    "per_mile": 0.70,
    "chemicals": 45,
    "hours": 8,
    "labor": 40,
    "target": 0.40,
}

# (klucz, usługa, jednostka, LOW, MID, HIGH, źródło)
RATES = [
    ("driveway", "Driveway / concrete", "$ / sq ft", 0.15, 0.25, 0.40,
     "Housecall Pro 2026: concrete $0.10-0.40/sq ft; driveway jobs $100-300"),
    ("house", "House wash (siding)", "$ / sq ft", 0.20, 0.30, 0.45,
     "2026 cost guides: siding $0.20-0.60/sq ft; Housecall Pro house wash $250-800"),
    ("roof", "Roof soft wash", "$ / sq ft", 0.25, 0.40, 0.90,
     "2026 cost guides: roof soft wash $0.15-0.90/sq ft, avg ~$0.35"),
    ("gutters", "Gutter cleaning (1 story)", "$ / linear ft", 0.90, 1.20, 1.60,
     "LeafFilter: $0.70-1.30/ft 1-story; Housecall Pro $0.80-2.00/ft"),
]
STORY_MULT = [(1, 1.00), (2, 1.35), (3, 1.70)]  # LeafFilter: 2-story $1.25-2.50/ft vs 1-story $0.70-1.30
MIN_JOB = 150  # Housecall Pro: typical jobs $150-500

YELLOW = PatternFill("solid", fgColor="FFF4C2")
GREY = PatternFill("solid", fgColor="EEEEEE")
HEAD = Font(bold=True, size=14)
BOLD = Font(bold=True)
THIN = Border(*(Side(style="thin", color="BBBBBB"),) * 4)


def build(path=OUT, inputs=None):
    v = {**DEFAULT_INPUTS, **(inputs or {})}
    wb = Workbook()
    start = wb.active
    start.title = "START"
    rates = wb.create_sheet("RATES")
    calc = wb.create_sheet("CALC")
    copy = wb.create_sheet("COPY")

    # ---------- RATES ----------
    rates["A1"] = "Rates — edit to match your local market"
    rates["A1"].font = HEAD
    for col, h in zip("ABCDEFG", ["Key", "Service", "Unit", "LOW", "MID", "HIGH", "Source (2026)"]):
        rates[f"{col}3"] = h
        rates[f"{col}3"].font = BOLD
    for i, (key, name, unit, lo, mid, hi, src) in enumerate(RATES, start=4):
        for col, val in zip("ABCDEFG", [key, name, unit, lo, mid, hi, src]):
            rates[f"{col}{i}"] = val
        for col in "DEF":
            rates[f"{col}{i}"].fill = YELLOW
            rates[f"{col}{i}"].number_format = "$0.00"
    rates["A10"] = "Height multiplier (house wash + gutters)"
    rates["A10"].font = BOLD
    rates["A11"], rates["B11"] = "Stories", "Multiplier"
    for i, (s, m) in enumerate(STORY_MULT, start=12):
        rates[f"A{i}"], rates[f"B{i}"] = s, m
        rates[f"B{i}"].fill = YELLOW
    rates["C12"] = "LeafFilter 2026: 2-story gutters cost ~1.3-1.9x 1-story"
    rates["A16"], rates["B16"] = "Minimum job charge", MIN_JOB
    rates["B16"].number_format = "$0"
    rates["B16"].fill = YELLOW
    rates["C16"] = "Housecall Pro 2026: most jobs $150-500"
    rates["A18"] = ("Ranges are national averages. Replace them with what your area pays — "
                    "the calculator uses whatever you type here.")
    for col, w in zip("ABCDEFG", [12, 28, 14, 9, 9, 9, 70]):
        rates.column_dimensions[col].width = w

    # ---------- START ----------
    start["A1"] = "QUOTE CALCULATOR — Pressure Washing + Gutters"
    start["A1"].font = HEAD
    start["A2"] = "Fill the yellow cells. Everything else calculates itself."
    rows = [
        (4, "Customer name", "customer", "@"),
        (5, "Driveway / concrete (sq ft)", "driveway", "0"),
        (6, "House siding (sq ft)", "house", "0"),
        (7, "Roof soft wash (sq ft)", "roof", "0"),
        (8, "Gutters (linear ft)", "gutters", "0"),
        (9, "Stories (1-3)", "stories", "0"),
        (10, "Price level (LOW / MID / HIGH)", "tier", "@"),
        (12, "Round-trip miles", "miles", "0"),
        (13, "Vehicle cost per mile ($)", "per_mile", "$0.00"),
        (14, "Chemicals & supplies ($)", "chemicals", "$0.00"),
        (15, "Crew hours (total, all people)", "hours", "0.0"),
        (16, "Labor cost per hour ($)", "labor", "$0.00"),
        (17, "Target profit margin", "target", "0%"),
    ]
    start["A11"] = "Your costs"
    start["A11"].font = BOLD
    for r, label, key, fmt in rows:
        start[f"A{r}"] = label
        start[f"B{r}"] = v[key]
        start[f"B{r}"].fill = YELLOW
        start[f"B{r}"].border = THIN
        start[f"B{r}"].number_format = fmt

    dv_tier = DataValidation(type="list", formula1='"LOW,MID,HIGH"', allow_blank=False)
    dv_story = DataValidation(type="whole", operator="between", formula1="1", formula2="3")
    start.add_data_validation(dv_tier)
    start.add_data_validation(dv_story)
    dv_tier.add("B10")
    dv_story.add("B9")

    start["A20"] = "RESULT"
    start["A20"].font = HEAD
    out = [
        (21, "Quote price", "=CALC!B15", "$#,##0"),
        (22, "Your total cost", "=CALC!B21", "$#,##0"),
        (23, "Profit", "=B21-B22", "$#,##0"),
        (24, "Profit margin", "=IF(B21=0,0,B23/B21)", "0%"),
        (25, "Price needed for target margin", "=IF(B17>=1,0,ROUNDUP(B22/(1-B17),-1))", "$#,##0"),
    ]
    for r, label, f, fmt in out:
        start[f"A{r}"] = label
        start[f"B{r}"] = f
        start[f"B{r}"].number_format = fmt
        start[f"B{r}"].font = BOLD
    start["A27"] = "VERDICT"
    start["A27"].font = HEAD
    start["B27"] = ('=IF(B21=0,"Enter job sizes above",'
                    'IF(B24>=B17,"OK - take the job",'
                    'IF(B24>=B17-0.1,"LOW - quote "&TEXT(B25,"$#,##0")&" instead",'
                    '"REJECT - margin too thin, quote "&TEXT(B25,"$#,##0")&" or walk away")))')
    start["B27"].font = Font(bold=True, size=14)
    green = PatternFill("solid", fgColor="C6EFCE")
    amber = PatternFill("solid", fgColor="FFEB9C")
    red = PatternFill("solid", fgColor="FFC7CE")
    start.conditional_formatting.add("B27", FormulaRule(formula=['LEFT($B$27,2)="OK"'], fill=green))
    start.conditional_formatting.add("B27", FormulaRule(formula=['LEFT($B$27,3)="LOW"'], fill=amber))
    start.conditional_formatting.add("B27", FormulaRule(formula=['LEFT($B$27,3)="REJ"'], fill=red))
    start["A29"] = "Customer-ready quote text is on the COPY tab."
    start.column_dimensions["A"].width = 34
    start.column_dimensions["B"].width = 48

    # ---------- CALC ----------
    calc["A1"] = "Calculations (no need to edit)"
    calc["A1"].font = HEAD
    calc["A3"], calc["B3"] = "Price column", '=MATCH(START!B10,RATES!D3:F3,0)'
    calc["A4"], calc["B4"] = "Height multiplier", "=VLOOKUP(START!B9,RATES!A12:B14,2,FALSE)"
    calc["A6"], calc["B6"], calc["C6"], calc["D6"] = "Line item", "Amount", "Rate", "Qty"
    for c in "ABCD":
        calc[f"{c}6"].font = BOLD
    items = [
        (7, "Driveway / concrete", 4, "START!B5", False),
        (8, "House wash", 5, "START!B6", True),
        (9, "Roof soft wash", 6, "START!B7", False),
        (10, "Gutter cleaning", 7, "START!B8", True),
    ]
    for r, name, rate_row, qty, height in items:
        calc[f"A{r}"] = name
        calc[f"C{r}"] = f"=INDEX(RATES!D{rate_row}:F{rate_row},1,$B$3)"
        calc[f"D{r}"] = f"={qty}"
        calc[f"B{r}"] = f"=ROUND(C{r}*D{r}{'*$B$4' if height else ''},2)"
        calc[f"B{r}"].number_format = "$#,##0.00"
        calc[f"C{r}"].number_format = "$0.00"
    calc["A12"], calc["B12"] = "Subtotal", "=SUM(B7:B10)"
    calc["A13"], calc["B13"] = "Minimum job charge", "=RATES!B16"
    calc["A14"], calc["B14"] = "Minimum applied?", '=IF(AND(B12>0,B12<B13),"YES","no")'
    calc["A15"], calc["B15"] = "QUOTE PRICE", "=IF(B12=0,0,ROUND(MAX(B12,B13),0))"
    calc["A15"].font = calc["B15"].font = BOLD
    calc["A17"], calc["B17"] = "Labor", "=START!B15*START!B16"
    calc["A18"], calc["B18"] = "Travel", "=START!B12*START!B13"
    calc["A19"], calc["B19"] = "Chemicals & supplies", "=START!B14"
    calc["A21"], calc["B21"] = "TOTAL COST", "=SUM(B17:B19)"
    calc["A21"].font = calc["B21"].font = BOLD
    for r in (12, 13, 15, 17, 18, 19, 21):
        calc[f"B{r}"].number_format = "$#,##0.00"
    calc.column_dimensions["A"].width = 24
    calc.column_dimensions["B"].width = 14

    # ---------- COPY ----------
    copy["A1"] = "Customer quote — copy into your text / email"
    copy["A1"].font = HEAD
    lines = [
        '="Hi "&START!B4&","',
        '="Thanks for reaching out. Here is your quote:"',
        '=IF(CALC!B7>0,"- Driveway / concrete ("&START!B5&" sq ft): "&TEXT(CALC!B7,"$#,##0"),"")',
        '=IF(CALC!B8>0,"- House wash ("&START!B6&" sq ft, "&START!B9&"-story): "&TEXT(CALC!B8,"$#,##0"),"")',
        '=IF(CALC!B9>0,"- Roof soft wash ("&START!B7&" sq ft): "&TEXT(CALC!B9,"$#,##0"),"")',
        '=IF(CALC!B10>0,"- Gutter cleaning ("&START!B8&" ft): "&TEXT(CALC!B10,"$#,##0"),"")',
        '=IF(CALC!B14="YES","- Minimum service charge applies","")',
        '="TOTAL: "&TEXT(CALC!B15,"$#,##0")',
        '="This quote is valid for 30 days. Reply YES and I will send available dates."',
    ]
    for i, f in enumerate(lines, start=3):
        copy[f"A{i}"] = f
    copy.column_dimensions["A"].width = 90
    for ws in (calc, copy):
        ws.sheet_properties.tabColor = "BBBBBB"
    start.sheet_properties.tabColor = "F4B400"

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else OUT))
