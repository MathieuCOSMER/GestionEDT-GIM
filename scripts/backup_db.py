# -*- coding: utf-8 -*-
"""Sauvegarde quotidienne des bases — à planifier vers 4h du matin.

Crée une sauvegarde UNIQUEMENT si la base a été modifiée depuis la dernière
sauvegarde (sinon ne fait rien). Les backups vont dans
databases/<année>/backups/ et les plus anciens sont purgés (30 conservés).

Planification sur PythonAnywhere (onglet « Tasks », tâche quotidienne 04:00) :
    python3 /home/<user>/<projet>/scripts/backup_db.py
"""
import os, sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import app  # noqa: E402  (importer après avoir ajusté sys.path)

def main():
    created = app.backup_all_if_modified()
    if created:
        print("Sauvegardes créées :")
        for p in created:
            print("  -", p)
    else:
        print("Aucune modification depuis la dernière sauvegarde : aucun backup créé.")

if __name__ == "__main__":
    main()
