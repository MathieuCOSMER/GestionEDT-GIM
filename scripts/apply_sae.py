# -*- coding: utf-8 -*-
"""Applique le contenu PN des SAÉ à la base (colonne courses.content_pn).

Ne touche QUE les lignes SAÉ (code commençant par « SAE ») : les fiches
Ressources ne sont jamais modifiées (leur PN est géré/édité côté serveur).

Champs repris depuis le PN : Compétences ciblées, Objectifs et problématique
professionnelle, Descriptif générique.

Correspondance code matière -> fiche PN (par semestre) :
  - nom commençant par « portfolio »  -> fiche PORTFOLIO du semestre
  - nom commençant par « stage »       -> fiche STAGE du semestre
  - sinon SAE{n}.{m}[lettre]            -> SAÉ numéro {m} du semestre
    (sous-SAÉ SAE3.1a/b/c -> même fiche)

Usage :
    python scripts/apply_sae.py                # base de l'année courante
    python scripts/apply_sae.py --year 2026-2027
    python scripts/apply_sae.py --db chemin.db
"""
import os, re, json, sqlite3, sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
    year = sys.argv[sys.argv.index("--year") + 1] if "--year" in sys.argv else current_year()
    return db_path_for_year(year) if year else os.path.join(BASE_DIR, "edt.db")

def sae_key(code, name):
    """Clé de la fiche SAÉ PN pour une matière SAÉ donnée."""
    nm = (name or "").strip().lower()
    if nm.startswith("portfolio"):
        return "portfolio"
    if nm.startswith("stage"):
        return "stage"
    m = re.match(r"SAE\d+\.(\d+)", code or "", re.I)
    return str(int(m.group(1))) if m else None

def main():
    db_path = db_path_from_args()
    print("Base       :", db_path)
    if not os.path.isfile(db_path):
        print("ERREUR : base introuvable.")
        sys.exit(1)

    with open(os.path.join(BASE_DIR, "data", "sae_content.json"), encoding="utf-8") as f:
        sae = json.load(f)

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        con.execute("ALTER TABLE courses ADD COLUMN content_pn TEXT")
        con.commit()
    except sqlite3.OperationalError:
        pass

    rows = con.execute(
        "SELECT c.id, c.code, c.name, s.code AS sem "
        "FROM courses c JOIN semesters s ON c.semester_id = s.id "
        "WHERE UPPER(c.code) LIKE 'SAE%' ORDER BY s.code, c.code"
    ).fetchall()

    matched, unmatched = 0, []
    for c in rows:
        key = sae_key(c["code"], c["name"])
        content = (sae.get(c["sem"]) or {}).get(key) if key else None
        if content is None:
            unmatched.append((c["sem"], c["code"], c["name"], key))
            continue
        con.execute("UPDATE courses SET content_pn=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (content, c["id"]))
        matched += 1
    con.commit()

    print("SAÉ remplies :", matched)
    if unmatched:
        print("Sans fiche PN (ignorées) :")
        for sem, code, name, key in unmatched:
            print("  - %-3s %-10s (clé %s)  %s" % (sem, code, key, name))
    con.close()
    print("Terminé. Les fiches Ressources n'ont pas été modifiées.")

if __name__ == "__main__":
    main()
