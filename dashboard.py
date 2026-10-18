"""Generator materiałów promocyjnych (szablony, działa offline).

    python3 dashboard.py materialy --produkt "Pressure washing quote calculator" \
        --odbiorca "pressure washing business owners" \
        --problem "Canva templates you have to fill in by hand"

Wynik: content/output/<slug>/ — skrypty_wideo.md, opis_oferty.md, maile.md, kalendarz_30_dni.md.
Teksty to szkic: przeczytaj, popraw liczby i ton, dopiero potem publikuj.
"""
import argparse
import re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "content" / "output"

HOOKS = [
    ("Problem", "Still pricing jobs on a napkin? This is for {odbiorca}."),
    ("Wynik", "From square footage to a finished quote in 20 seconds."),
    ("Błąd", "The pricing mistake that makes a 'busy' week lose money."),
    ("Porównanie", "{problem_cap} vs. a file that does the math."),
    ("Werdykt", "This spreadsheet tells me when NOT to take a job."),
    ("Klient", "What I send a customer 2 minutes after they ask for a price."),
    ("Liczby", "Driveway, house, gutters: here is how the price adds up."),
    ("Mit", "'Just charge what the other guy charges' — here's why that fails."),
    ("Start", "If you just bought your first pressure washer, price like this."),
    ("Dowód", "I ran 4 real jobs through it. One said REJECT. Here's why."),
]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40]


def materialy(produkt, odbiorca, problem, start=None):
    out = ROOT / slug(produkt)
    out.mkdir(parents=True, exist_ok=True)
    ctx = dict(produkt=produkt, odbiorca=odbiorca, problem=problem,
               problem_cap=problem[:1].upper() + problem[1:])

    v = [f"# 10 skryptów wideo (20–30 s) — {produkt}\n",
         "Format: ekran telefonu/komputera + głos. Pokazuj produkt w użyciu, nie mów o nim.\n"]
    for i, (typ, hook) in enumerate(HOOKS, 1):
        v.append(f"## {i}. {typ}\n"
                 f"- **0–3 s (hook):** {hook.format(**ctx)}\n"
                 f"- **3–20 s:** wpisz jedno konkretne zlecenie; pokaż cenę, marżę i werdykt.\n"
                 f"- **20–30 s (CTA):** \"Link in bio — it's a one-time download, no subscription.\"\n")
    (out / "skrypty_wideo.md").write_text("\n".join(v))

    (out / "opis_oferty.md").write_text(
        f"# Opis oferty — {produkt}\n\n"
        f"**Pierwsze zdanie (rozwiązuje skargę):** Works right away — no {problem}.\n\n"
        f"**Dla kogo:** {odbiorca}.\n\n"
        "**Co dostajesz:** (lista plików)\n\n**Jak to działa:** 3 kroki.\n\n"
        "**Ujawnienie AI (wymagane przez Etsy, w pierwszych akapitach):** "
        "Designed with the help of AI tools, checked and tested by hand.\n")

    maile = [f"# Sekwencje maili — {produkt}\n",
             "## A. Po zakupie (3 maile)",
             "1. **Dzień 0 — Your file + 2-minute setup:** link, jak otworzyć w Google Sheets.",
             "2. **Dzień 3 — Did your first quote work?** poproś o odpowiedź, nie o recenzję.",
             "3. **Dzień 7 — Quick favour:** prośba o recenzję, jeśli plik pomógł.\n",
             "## B. Lead magnet (darmowa ściąga → zakup, 3 maile)",
             f"1. **Free pricing cheat sheet for {odbiorca}.**",
             f"2. **The mistake behind '{problem}'.** Historia + liczby.",
             f"3. **The full tool.** Link do oferty.\n",
             "## C. Porzucony koszyk / ulubione (Etsy: oferta dla „favorites\", 1 wiadomość)",
             "- 10% kod ważny 48 h. Bez presji, jedno zdanie o tym, co plik robi.\n"]
    (out / "maile.md").write_text("\n".join(maile))

    start = start or date.today()
    kanaly = ["Reddit/FB: odpowiedź w wątku wyceny", "TikTok/Reels: skrypt #{n}",
              "Pinterest: 1 pin ze zrzutu", "Odpoczynek / czytanie recenzji konkurencji",
              "Reddit/FB: odpowiedź w wątku wyceny", "TikTok/Reels: skrypt #{n}",
              "Przegląd Etsy Stats (wyświetlenia, CTR, zamówienia)"]
    k = [f"# Kalendarz 30 dni — {produkt}\n", "| Data | Kanał / zadanie |", "|---|---|"]
    n = 1
    for d in range(30):
        task = kanaly[d % 7]
        if "{n}" in task:
            task = task.format(n=(n - 1) % 10 + 1)
            n += 1
        k.append(f"| {(start + timedelta(days=d)).isoformat()} | {task} |")
    (out / "kalendarz_30_dni.md").write_text("\n".join(k) + "\n")
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("materialy", help="wygeneruj materiały promocyjne")
    m.add_argument("--produkt", required=True)
    m.add_argument("--odbiorca", required=True)
    m.add_argument("--problem", required=True)
    a = p.parse_args()
    out = materialy(a.produkt, a.odbiorca, a.problem)
    for f in sorted(out.iterdir()):
        print(f.relative_to(Path(__file__).resolve().parent))


if __name__ == "__main__":
    main()
