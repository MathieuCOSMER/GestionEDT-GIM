# -*- coding: utf-8 -*-
"""Supprime les heures de répartition posées sur un groupe que le semestre ne déclare pas.

Une séance de TD ou de TP a des heures semaine par semaine pour chacun de ses groupes
(weekly_hours.group_index). Le nombre de groupes vient de Promotions › Groupes. Des
heures sur un numéro de groupe au-delà (par exemple le groupe 5 d'une séance TP FTP
quand le semestre ne déclare que 4 groupes FTP) ne s'affichent plus dans la Répartition
Calendaire, et l'appli ne les place plus. Elles viennent typiquement du passage des TP
d'un semestre mutualisé de « communs » à « distincts » : le groupe des apprentis restait
sur la séance devenue FTP, en double de la séance ALT.

Par défaut, le script LISTE seulement ce qu'il supprimerait. Avec --appliquer, il
sauvegarde d'abord chaque base touchée (databases/<année>/backups/, au nom des
sauvegardes de l'appli, restaurable depuis Journal › Sauvegardes), puis supprime.

Usage :
    python scripts/purge_groupes_non_declares.py                      # toutes les années, simulation
    python scripts/purge_groupes_non_declares.py --year 2026-2027     # une année, simulation
    python scripts/purge_groupes_non_declares.py --year 2026-2027 --appliquer

À lancer sur le serveur (console PythonAnywhere : python3.13), puis recharger la web app.
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACES = {0: 'FTP', 1: 'ALT', 2: 'MUT'}


def nb_groupes(sg, mut, tpsep, sem, ft, tt, tp_type):
    """Nombre de groupes d'une séance — même règle que app._group_multiplier."""
    tt = (tt or '').upper().replace(' ', '')
    if tt == 'CM':
        return 1
    if sem in mut and not (tt.startswith('TP') and sem in tpsep):
        ft = 2
    g = sg.get((sem, ft))
    if not g:
        return 1
    if tt.startswith('TP'):
        tt = 'TP8' if (tp_type or '').upper().replace(' ', '') == 'TP8' else 'TP'
    return g.get(tt) or 1


def traiter(chemin, annee, appliquer):
    db = sqlite3.connect(chemin, timeout=20)
    db.row_factory = sqlite3.Row
    try:
        sg = {(r['semester_code'], r['formation_type']): {'TD': r['td_groups'], 'TP': r['tp_groups'],
                                                           'TP8': r['tp8_groups'], 'PT': r['pt_groups']}
              for r in db.execute('SELECT * FROM semester_groups')}
        mut, tpsep = set(), set()
        for r in db.execute('SELECT code, mutualized, tp_separate FROM semesters'):
            if r['mutualized']:
                mut.add(r['code'])
            if r['tp_separate'] is None or r['tp_separate']:
                tpsep.add(r['code'])
        lignes = []
        for r in db.execute('''SELECT wh.id, wh.week_number, wh.group_index, wh.hours, cs.formation_type,
                                      cs.teaching_type, c.code, c.tp_type, s.code AS sem
                               FROM weekly_hours wh JOIN course_sessions cs ON cs.id = wh.course_session_id
                               JOIN courses c ON c.id = cs.course_id JOIN semesters s ON s.id = c.semester_id'''):
            tt = (r['teaching_type'] or '').upper().replace(' ', '')
            if not (tt.startswith('TP') or tt == 'TD'):
                continue
            n = nb_groupes(sg, mut, tpsep, r['sem'], r['formation_type'], tt, r['tp_type'])
            if (r['group_index'] or 1) > n:
                lignes.append((r, n))
    except sqlite3.OperationalError as e:
        print(f'{annee} : base illisible ({e})')
        db.close()
        return 0
    if not lignes:
        print(f'{annee} : rien à supprimer')
        db.close()
        return 0
    par = {}
    for r, n in lignes:
        k = (r['sem'], r['code'], r['teaching_type'], FACES.get(r['formation_type'], '?'), n, r['group_index'])
        par.setdefault(k, []).append((r['week_number'], r['hours']))
    print(f'{annee} : {len(lignes)} ligne(s) d\'heures sur {len(par)} groupe(s) non déclaré(s)')
    for k, v in sorted(par.items()):
        print(f'   {k[0]} {k[1]:8} {k[2]} {k[3]} ({k[4]} groupe(s) déclaré(s)) gr{k[5]} : {len(v)} semaine(s), '
              f'{sum(h or 0 for _, h in v):g} h — S{", S".join(str(w) for w, _ in sorted(v))}')
    if appliquer:
        bdir = os.path.join(os.path.dirname(chemin), 'backups')
        os.makedirs(bdir, exist_ok=True)
        dest = os.path.join(bdir, f"edt_{annee}_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}_avant-purge-groupes.db")
        cible = sqlite3.connect(dest)
        db.backup(cible)
        cible.close()
        db.executemany('DELETE FROM weekly_hours WHERE id = ?', [(r['id'],) for r, _ in lignes])
        db.commit()
        print(f'   sauvegarde : {dest}')
        print(f'   {len(lignes)} ligne(s) supprimée(s)')
    db.close()
    return len(lignes)


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--year', help='année universitaire (ex. 2026-2027) ; toutes par défaut')
    p.add_argument('--dbdir', default=os.environ.get('EDT_DB_DIR') or os.path.join(RACINE, 'databases'),
                   help='dossier des bases (databases/ du projet par défaut)')
    p.add_argument('--appliquer', action='store_true', help='supprimer pour de bon (sinon : simulation)')
    a = p.parse_args()
    annees = [a.year] if a.year else sorted(d for d in os.listdir(a.dbdir)
                                            if os.path.isfile(os.path.join(a.dbdir, d, f'edt_{d}.db')))
    total = 0
    for annee in annees:
        chemin = os.path.join(a.dbdir, annee, f'edt_{annee}.db')
        if not os.path.isfile(chemin):
            print(f'{annee} : pas de base ({chemin})')
            continue
        total += traiter(chemin, annee, a.appliquer)
    if total and not a.appliquer:
        print('\nSimulation : rien n\'est supprimé. Relancez avec --appliquer pour supprimer (après sauvegarde).')
    elif total:
        print('\nTerminé : rechargez la web app (onglet Web › Reload).')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
