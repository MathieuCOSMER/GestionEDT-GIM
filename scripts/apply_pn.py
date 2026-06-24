# -*- coding: utf-8 -*-
"""Applique le contenu du Programme national (PN) à la base.

Lit data/pn_content.json (PN code -> contenu) et remplit la colonne
courses.content_pn de chaque matière, en faisant correspondre le code de la
matière à sa fiche PN (sous-ressources R1.01a/b -> R1.01, codes ISP, etc.).

Usage :
    python scripts/apply_pn.py                # base de l'année courante (edt_settings.json)
    python scripts/apply_pn.py --db chemin.db # base explicite
    python scripts/apply_pn.py --year 2026-2027

À lancer sur le serveur (console PythonAnywhere) puis recharger la web app.
"""
import os, re, json, sqlite3, sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Codes ISP qui diffèrent du code matière (parcours Ingénierie des systèmes pluritechniques)
SPECIAL = {
    "R4.05": "R4.ISP.05", "R4.06": "R4.ISP.06",
    "R5.06": "R5.ISP.06", "R5.07": "R5.ISP.07", "R5.08": "R5.ISP.08",
    "R6.05": "R6.ISP.05",
}

def resolve(code):
    """Code matière -> code fiche PN (enlève le suffixe sous-ressource, applique ISP)."""
    base = re.sub(r"[a-z]$", "", code or "")
    return SPECIAL.get(base, base)

def current_year():
    try:
        with open(os.path.join(BASE_DIR, "edt_settings.json"), encoding="utf-8") as f:
            return (json.load(f) or {}).get("current_year", "")
    except Exception:
        return ""

def db_path_for_year(year):
    # Bases rangées dans databases/<année>/edt_<année>.db (EDT_DB_DIR pour surcharger)
    db_dir = os.environ.get("EDT_DB_DIR") or os.path.join(BASE_DIR, "databases")
    return os.path.join(db_dir, year, f"edt_{year}.db")

def db_path_from_args():
    if "--db" in sys.argv:
        return sys.argv[sys.argv.index("--db") + 1]
    if "--year" in sys.argv:
        year = sys.argv[sys.argv.index("--year") + 1]
    else:
        year = current_year()
    if year:
        return db_path_for_year(year)
    return os.path.join(BASE_DIR, "edt.db")

def main():
    db_path = db_path_from_args()
    print("Base       :", db_path)
    if not os.path.isfile(db_path):
        print("ERREUR : base introuvable.")
        sys.exit(1)

    with open(os.path.join(BASE_DIR, "data", "pn_content.json"), encoding="utf-8") as f:
        pn = json.load(f)
    print("Fiches PN  :", len(pn))

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    # Colonne content_pn (idempotent)
    try:
        con.execute("ALTER TABLE courses ADD COLUMN content_pn TEXT")
        con.commit()
    except sqlite3.OperationalError:
        pass

    courses = con.execute("SELECT id, code, name FROM courses ORDER BY code").fetchall()
    matched, unmatched = 0, []
    for c in courses:
        code = c["code"] or ""
        if code.upper().startswith("SAE") or (c["name"] or "").strip().lower().startswith("aar"):
            continue
        key = resolve(code)
        content = pn.get(key)
        if content is None:
            unmatched.append((code, key))
            continue
        con.execute("UPDATE courses SET content_pn=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (content, c["id"]))
        matched += 1
    con.commit()

    print("Remplies   :", matched)
    if unmatched:
        print("Sans fiche PN (ignorées) :")
        for code, key in unmatched:
            print("  - %-10s (cherché %s)" % (code, key))
    con.close()
    print("Terminé. Rechargez la web app si nécessaire.")

if __name__ == "__main__":
    main()
