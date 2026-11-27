"""Optimisation de la répartition annuelle (weekly_hours) — PuLP + HiGHS.

Place les séances de chaque ligne de la Répartition annuelle (une séance, ou un groupe
de TD / TP) dans les semaines de l'année, en respectant les contraintes matière :

  imposé       semaines où la face est absente : vacances et stage FTP, entreprise ALT
               (une ligne MUT évite les deux) ; nombre de séances par semaine au plus
               (sessions_per_week_max) ;
  préférences  (coût, du plus fort au plus faible)
               • séance non placée (manque de semaines possibles) ;
               • ordonnancement (« A terminé avant B », écart minimum), côté FTP
                 (FTP + MUT) et côté ALT (ALT + MUT), chaque groupe d'après après la
                 fin de tous les groupes d'avant — mêmes règles que le repère 🔗 ;
               • répartition souhaitée (Contraintes Matière) : l'ordre des types qu'elle
                 décrit — même règle que le cadre rouge de la répartition ;
               • séance hors de la plage de semaines de la matière (semestre) ;
               • organisation de la répartition souhaitée : sa grille semaine par
                 semaine, posée à partir d'une semaine de début choisie par le calcul
                 (une colonne = une semaine disponible de la face) — chaque séance
                 décalée d'une semaine coûte (même mesure que le repère « vœu ») ;
               • surcharge d'une promotion (FTP au-delà de 30 h, ALT au-delà de 40 h par
                 semaine, groupe par groupe) et d'un enseignant (au-delà de 20 h, seuil du
                 Contrôle de la répartition) ;
               • matière interrompue (chaque bloc de semaines en plus) ;
               • séance déplacée (mode « bouger peu » : partir de la répartition actuelle).

Deux modes : « stable » garde le total placé de chaque ligne et ne déplace que ce qui
améliore le coût ; « zero » repart des totaux de la fiche Matières (nombre de séances).
Les lignes hors du périmètre (autres semestres, autre face) restent telles quelles mais
comptent dans les charges et les ordonnancements.

Rien n'est écrit ici : app.py renvoie la proposition, que l'écran pose dans le brouillon.
"""

from __future__ import annotations

import bisect
import time
from collections import defaultdict

try:
    import pulp
except ImportError:  # pragma: no cover
    pulp = None

POIDS = {
    'non_place': 100.0,    # par séance
    'ordre': 100.0,        # par semaine de retard sur un ordonnancement : autant qu'une séance
                           # non placée, plus qu'une grille de vœu tassée d'une semaine
    'voeu': 30.0,          # par semaine d'avance d'un groupe sur ce que le vœu met tout entier
                           # avant lui (un TP avant la fin des CM)
    'organisation': 5.0,   # par séance et par semaine de décalage sur la grille du vœu : plus
                           # qu'un déplacement (4), pour que la répartition rejoigne le vœu
    'hors_plage': 30.0,    # par séance hors des semaines de la matière (mode stable : ajoutée hors
                           # plage) : un CM de S2 ne part pas en S1 pour suivre un vœu
    'charge': 3.0,         # par heure au-delà du plafond d'une promotion
    'enseignant': 1.0,     # par heure au-delà de 20 h pour un enseignant
    'bloc': 3.0,           # par interruption d'une matière (bloc de semaines en plus) : la
                           # continuité d'une matière compte plus qu'une heure d'enseignant
    'deplacement': 2.0,    # par séance ajoutée ou retirée dans une semaine (mode stable) :
                           # 4 par séance déplacée, plus qu'une heure d'enseignant en trop,
                           # moins qu'1,5 h de surcharge d'une promotion
    'pic': 0.2,            # par heure de la semaine la plus chargée d'une promotion
}
# Poids réglables dans la fenêtre « Optimiser… » : (clé, libellé, unité, explication),
# dans l'ordre d'importance par défaut
POIDS_INFOS = [
    ('non_place', 'Séance non placée', 'par séance',
     'Faute de semaine possible (calendrier, séances par semaine). Gardez-le le plus fort.'),
    ('ordre', 'Ordonnancement non respecté', 'par semaine de retard',
     '« A terminé avant B » de Contraintes Matière, écart minimum compris.'),
    ('voeu', 'Ordre de la répartition souhaitée', "par semaine d'avance",
     "Un groupe qui commence avant la fin de ce que le vœu met tout entier avant lui (un TP avant la fin des CM)."),
    ('organisation', 'Grille de la répartition souhaitée', 'par séance, par semaine de décalage',
     "Écart à la grille du vœu, semaine par semaine, depuis la semaine de début la plus favorable."),
    ('hors_plage', 'Séance hors des semaines de la matière', 'par séance',
     "Hors de son semestre. En mode « bouger le moins possible », ce qui y est déjà reste sans coût."),
    ('charge', "Surcharge d'une promotion", 'par heure', 'Au-delà de 30 h (FTP) ou 40 h (ALT) par semaine.'),
    ('enseignant', "Surcharge d'un enseignant", 'par heure', 'Au-delà de 20 h par semaine.'),
    ('bloc', 'Matière interrompue', 'par interruption', 'Chaque bloc de semaines en plus.'),
    ('deplacement', 'Séance déplacée', 'par séance ajoutée ou retirée',
     "Mode « bouger le moins possible » : une séance changée de semaine compte deux fois."),
    ('pic', "Semaine la plus chargée d'une promotion", 'par heure', 'Lisse la charge des semaines.'),
]
POIDS_MAX = 1000.0


def lire_poids(poids):
    """Poids valides {clé: float} d'après un dict ; ValueError sinon."""
    if not isinstance(poids, dict):
        raise ValueError('poids : objet {nom: valeur} attendu')
    out = {}
    for cle, val in poids.items():
        if cle not in POIDS:
            raise ValueError(f'Poids inconnu : {cle}')
        try:
            v = float(val)
        except (TypeError, ValueError):
            raise ValueError(f'Poids {cle} : nombre attendu') from None
        if not (0 <= v <= POIDS_MAX):     # rejette aussi NaN
            raise ValueError(f'Poids {cle} : entre 0 et {POIDS_MAX:g}')
        out[cle] = v
    return out


PLAFOND = {'FTP': 30.0, 'ALT': 40.0}
PLAFOND_ENSEIGNANT = 20.0
# DS : ligne DS d'une matière (Répartition Calendaire), que la répartition souhaitée place
# dans l'enchaînement des séances (Contraintes Matières) ; la ligne AaR n'a pas de vœu
TYPES = ('CM', 'TD', 'TP', 'PT', 'DS')
FT_CODE = {'FTP': 0, 'ALT': 1, 'MUT': 2}


def _type(r):
    return (r.get('type') or '').upper().replace(' ', '')


def _cle(r):
    return (r['session_id'], r.get('group_index') or 1)


def _faces(r):
    return {'FTP': ('FTP',), 'ALT': ('ALT',), 'MUT': ('FTP', 'ALT')}.get(r['formation'], ())


class Probleme:
    """Données de l'optimisation (lignes, calendrier, contraintes), indépendantes du modèle.

    ctx : annee {sem: année d'étude}, semaines {année: [semaines, ordre de l'année]},
    speciales {sem: {vacation_ftp, stage_ftp, company_alt}}, plages {course_id: set | None},
    spw {session_id: max par semaine}, ordres [...], voeux {course_id: {n_weeks, rows}},
    publics {(sid, g): ((année, face, min, max), …)}."""

    def __init__(self, lignes, ctx, params):
        self.ctx = ctx
        self.mode = params.get('mode', 'stable')
        self.placer_vides = params.get('placer_vides', True)
        sems = set(params.get('semestres') or [])
        face = params.get('faces') or ''
        self.lignes = [r for r in lignes if r['formation'] in FT_CODE]
        self.par_cle = {_cle(r): r for r in self.lignes}

        def dans_perimetre(r):
            if r['semester'] not in sems:
                return False
            return face == '' or r['formation'] == 'MUT' or r['formation'] == face.upper()
        self.libres = [r for r in self.lignes if dans_perimetre(r)]
        self.cles_libres = {_cle(r) for r in self.libres}
        # Placement actuel en séances : {clé: {semaine: n}}
        self.actuel = {}
        for r in self.lignes:
            slot = r.get('slot_duration') or 1.5
            self.actuel[_cle(r)] = {int(w): int(round(h / slot)) for w, h in (r.get('by_week') or {}).items()
                                    if h and round(h / slot) > 0}
        self.rang = {}           # {année: {semaine: rang dans l'année}}
        for an, ws in ctx['semaines'].items():
            self.rang[an] = {w: i for i, w in enumerate(ws)}

    def annee(self, r):
        return self.ctx['annee'].get(r['semester'])

    def k(self, r, w):
        return self.rang.get(self.annee(r), {}).get(w)

    def permises(self, r):
        """Semaines où la ligne peut avoir cours (calendrier de sa face), ordre de l'année."""
        an = self.annee(r)
        sp = self.ctx['speciales'].get(r['semester'], {})
        interdit = set()
        if r['formation'] in ('FTP', 'MUT'):
            interdit |= set(sp.get('vacation_ftp') or ()) | set(sp.get('stage_ftp') or ())
        if r['formation'] in ('ALT', 'MUT'):
            interdit |= set(sp.get('company_alt') or ())
        return [w for w in self.ctx['semaines'].get(an, []) if w not in interdit]

    def plage(self, r):
        return self.ctx['plages'].get(r['course_id'])

    def candidates(self, r):
        """Semaines que le calcul peut donner à la ligne : ses semaines permises dans la
        plage de la matière (son semestre), plus — mode stable — celles où elle a déjà
        des séances. Une séance ne part donc jamais dans un autre semestre ; à défaut de
        plage, toutes les semaines permises."""
        perm = self.permises(r)
        plage = self.plage(r)
        if not plage:
            return perm
        deja = set(self.actuel[_cle(r)]) if self.mode == 'stable' else set()
        return [w for w in perm if w in plage or w in deja] or perm

    def cible(self, r):
        """Séances à placer : total actuel (mode stable, ligne déjà placée) ou fiche Matières."""
        slot = r.get('slot_duration') or 1.5
        fiche = int(r.get('nb_sessions') or 0) or int(round((r.get('total_hours') or 0) / slot))
        if self.mode == 'stable':
            n0 = sum(self.actuel[_cle(r)].values())
            if n0 > 0:
                return n0
            if not self.placer_vides:      # ligne encore vide : laissée vide
                return 0
        return fiche

    def spw(self, r):
        return max(1, int(self.ctx['spw'].get(r['session_id']) or 1))


# ───────────────────────── évaluation (avant / après) ─────────────────────────

def evaluer(pb, placement):
    """Bilan d'un placement {clé: {semaine: n}} : ordonnancements et vœux non suivis,
    séances hors plage ou en semaine interdite, surcharges, séances non placées.
    Ne regarde que ce qui touche le périmètre. Les interruptions ne comptent pas pour une
    ligne qui suit la grille d'un vœu : c'est lui qui en fixe le rythme."""
    res = {'ordres': [], 'voeux': 0, 'grille': 0, 'grille_matieres': [], 'hors_plage': 0, 'interdites': 0, 'non_places': 0,
           'surcharges': [], 'enseignants': [], 'blocs_en_plus': 0,
           'heures_surcharge': 0.0, 'heures_enseignants': 0.0}
    orgs = _organisation(pb)
    suit_grille = {_cle(L['r']) for org in orgs for L in org['lignes']}
    for r in pb.libres:
        c = _cle(r)
        pl = placement.get(c, {})
        perm = set(pb.permises(r))
        plage = pb.plage(r)
        res['interdites'] += sum(n for w, n in pl.items() if w not in perm)
        if plage:
            res['hors_plage'] += sum(n for w, n in pl.items() if w not in plage)
        fiche = pb.cible(r)
        res['non_places'] += max(0, fiche - sum(pl.values()))
        actives = sorted(pb.k(r, w) for w in pl if pl[w] > 0 and pb.k(r, w) is not None)
        perm_k = sorted(pb.k(r, w) for w in perm if pb.k(r, w) is not None)
        if actives and c not in suit_grille:
            idx = [perm_k.index(a) for a in actives if a in perm_k]
            res['blocs_en_plus'] += sum(1 for a, b in zip(idx, idx[1:]) if b > a + 1)
    # Ordonnancements
    for o, cote, pred, succ in _ordres(pb):
        if not ({_cle(r) for r in pred + succ} & pb.cles_libres):
            continue
        kp = [pb.k(r, w) for r in pred for w, n in placement.get(_cle(r), {}).items() if n > 0]
        ks = [pb.k(r, w) for r in succ for w, n in placement.get(_cle(r), {}).items() if n > 0]
        kp, ks = [x for x in kp if x is not None], [x for x in ks if x is not None]
        if kp and ks and min(ks) <= max(kp) + (o.get('gap') or 0):
            res['ordres'].append(f"{o['texte']}{(' (' + cote + ')') if cote else ''}")
    # Vœux (même règle que l'écran : la i-e séance de t, à sa semaine, attend `need`
    # séances de u placées au plus tard cette semaine-là, dans l'ordre de l'année)
    for v in _voeux(pb):
        for (r_t, i, need, rows_u) in v['regles']:
            if not ({_cle(r_t)} | {_cle(u) for u in rows_u}) & pb.cles_libres:
                continue
            w_i = _semaine_de_rang(pb, r_t, placement, i)
            if w_i is None:
                continue
            if any(_cumul_a(pb, r_u, placement, pb.k(r_t, w_i)) < need for r_u in rows_u):
                res['voeux'] += 1
    # Grille des vœux : décalages (séance × semaine), matière par matière
    codes = {r['course_id']: r.get('course_code') or '' for r in pb.lignes}
    eg = _ecarts_grille(pb, placement, orgs)
    res['grille'] = sum(e for e, _ in eg.values())
    res['grille_matieres'] = sorted(((codes.get(cid, ''), e, s) for cid, (e, s) in eg.items() if e > 0),
                                    key=lambda x: (-x[1], x[0]))
    # Charges
    for (an, face, lo, hi), membres in _atomes(pb).items():
        plafond = PLAFOND.get(face)
        if not plafond or not any(m in pb.cles_libres for m in membres):
            continue
        charge = defaultdict(float)
        for m in membres:
            r = pb.par_cle[m]
            for w, n in placement.get(m, {}).items():
                charge[w] += n * (r.get('slot_duration') or 1.5)
        for w, h in charge.items():
            if h > plafond + 1e-6:
                res['surcharges'].append((an, face, w, h))
    for nom, rows in _enseignants(pb).items():
        if not any(_cle(r) in pb.cles_libres for r, _ in rows):
            continue
        charge = defaultdict(float)
        for r, mult in rows:
            for w, n in placement.get(_cle(r), {}).items():
                charge[w] += n * (r.get('slot_duration') or 1.5) * mult
        for w, h in charge.items():
            if h > PLAFOND_ENSEIGNANT + 1e-6:
                res['enseignants'].append((nom, w, h))
                res['heures_enseignants'] += h - PLAFOND_ENSEIGNANT
    # Surcharges uniques par (année, face, semaine) : la pire partie de la promotion
    pire = {}
    for an, face, w, h in res['surcharges']:
        pire[(an, face, w)] = max(pire.get((an, face, w), 0), h)
    res['surcharges'] = sorted((an, face, w, h) for (an, face, w), h in pire.items())
    res['heures_surcharge'] = sum(h - PLAFOND[face] for an, face, w, h in res['surcharges'])
    return res


def _cumul_a(pb, r, placement, kw):
    """Séances de la ligne placées jusqu'au rang de semaine kw compris (ordre de l'année)."""
    return sum(v for x, v in placement.get(_cle(r), {}).items()
               if v > 0 and pb.k(r, x) is not None and pb.k(r, x) <= kw)


def _semaine_de_rang(pb, r, placement, i):
    """Semaine de la i-e séance de la ligne (ordre de l'année), ou None."""
    acc = 0
    for w, v in sorted(((w, v) for w, v in placement.get(_cle(r), {}).items()
                        if v > 0 and pb.k(r, w) is not None), key=lambda x: pb.k(r, x[0])):
        acc += v
        if acc >= i:
            return w
    return None


def _ordres(pb):
    """(ordre, côté, lignes d'avant, lignes d'après) — côté FTP (FTP + MUT) et ALT (ALT + MUT)."""
    par_cours = defaultdict(list)
    for r in pb.lignes:
        par_cours[r['course_id']].append(r)
    out = []
    for o in pb.ctx['ordres']:
        for cote, faces in (('FTP', ('FTP', 'MUT')), ('ALT', ('ALT', 'MUT'))):
            def pick(cid, part):
                return [r for r in par_cours.get(cid, []) if r['formation'] in faces
                        and (not part or _type(r) == part)]
            pred, succ = pick(o['pred_id'], o['pred_part']), pick(o['succ_id'], o['succ_part'])
            if not pred or not succ:
                continue
            tout_mut = all(r['formation'] == 'MUT' for r in pred + succ)
            if cote == 'ALT' and tout_mut:
                continue
            out.append((o, '' if tout_mut else cote, pred, succ))
    return out


def _periode_libre_possible(t, n_groupes):
    """Type dont les séances peuvent être libres dans leur période : le TP, et le TD
    quand la face n'a qu'un groupe de TD."""
    return t == 'TP' or (t == 'TD' and n_groupes == 1)


def _periodes_libres(arr, n_cols, t, n_groupes=0):
    """Périodes « libres » d'une ligne du vœu : colonnes de TP (ou de TD à un seul
    groupe, `n_groupes`) qui se suivent dont au moins une a plus d'une séance — leurs
    séances se placent n'importe où dans la période. [(début, fin)] (colonnes)."""
    if not _periode_libre_possible(t, n_groupes):
        return []
    v = [int((arr[c] if c < len(arr) else 0) or 0) for c in range(n_cols)]
    out, c = [], 0
    while c < n_cols:
        if v[c] <= 0:
            c += 1
            continue
        d = c
        while d + 1 < n_cols and v[d + 1] > 0:
            d += 1
        if max(v[c:d + 1]) > 1:
            out.append((c, d))
        c = d + 1
    return out


def _ancres(arr, n_cols, t, n_groupes=0):
    """Colonne de référence de chaque colonne : le début de sa période libre, sinon elle-même."""
    a = list(range(n_cols))
    for debut, fin in _periodes_libres(arr, n_cols, t, n_groupes):
        for c in range(debut, fin + 1):
            a[c] = debut
    return a


def _voeux(pb):
    """Règles de la répartition souhaitée, comme la répartition (repWishEvaluate) : la
    i-e séance d'un type t d'une ligne attend, au plus tard la même semaine, `need`
    séances de chaque autre type u que le vœu met avant elle — dans chaque groupe de u.
    Période libre (_periodes_libres : TP, TD d'un seul groupe) : ses séances n'attendent
    que ce qui la précède, ce qui est placé pendant la période n'attend aucune d'elles,
    ce qui la suit les attend toutes.
    → [{course_id, regles: [(ligne t, i, need, [lignes u])]}]"""
    par_cours = defaultdict(list)
    for r in pb.lignes:
        par_cours[r['course_id']].append(r)
    out = []
    for cid, w in (pb.ctx.get('voeux') or {}).items():
        rows = par_cours.get(cid, [])
        if not w or not w.get('n_weeks') or not rows:
            continue
        regles = []
        for side, ft in (('FTP', 0), ('ALT', 1)):
            type_cle = {}
            for k in (w.get('rows') or {}):
                f, t = k.split(':')
                if int(f) != ft and int(f) != 2:
                    continue
                if t not in type_cle or int(f) != 2:
                    type_cle[t] = k
            types = [t for t in TYPES if t in type_cle]
            if not types:
                continue
            if side == 'ALT' and all(type_cle[t].startswith('2:') for t in types):
                continue
            lignes_t = {t: [r for r in rows if r['formation'] in (side, 'MUT') and _type(r) == t] for t in types}
            cum, col, anc = {}, {}, {}
            for t in types:
                arr = w['rows'].get(type_cle[t]) or []
                anc[t] = _ancres(arr, w['n_weeks'], t, len(lignes_t[t]))
                cum[t], col[t], acc = [], [], 0
                for c in range(w['n_weeks']):
                    cum[t].append(acc)
                    v = arr[c] if c < len(arr) else 0
                    col[t].extend([c] * int(v or 0))
                    acc += int(v or 0)
            nb = {t: max([int(r.get('nb_sessions') or 0) for r in lignes_t[t]] or [0]) for t in types}
            for t in types:
                for r_t in lignes_t[t]:
                    for i, c0 in enumerate(col[t], start=1):
                        c = anc[t][c0]                      # séance d'une période libre : son début
                        for u in types:
                            if u == t or not lignes_t[u]:
                                continue
                            cu = cum[u][anc[u][c]]          # u en période libre : ce qui la précède
                            need = min(cu, nb[u] or cu)
                            if need > 0:
                                regles.append((r_t, i, need, lignes_t[u]))
        if regles:
            out.append({'course_id': cid, 'regles': regles})
    return out


def _phases(pb):
    """Ordre des types que le vœu sépare tout à fait : u fini avant que t commence (toutes
    les colonnes de u avant la première de t), côté FTP (FTP + MUT) et côté ALT (ALT +
    MUT), comme _voeux. → [(course_id, lignes de u, lignes de t)]"""
    par_cours = defaultdict(list)
    for r in pb.lignes:
        par_cours[r['course_id']].append(r)
    out = []
    for cid, w in (pb.ctx.get('voeux') or {}).items():
        rows = par_cours.get(cid, [])
        if not w or not w.get('n_weeks') or not rows:
            continue
        for side, ft in (('FTP', 0), ('ALT', 1)):
            type_cle = {}
            for k in (w.get('rows') or {}):
                f, t = k.split(':')
                if int(f) != ft and int(f) != 2:
                    continue
                if t not in type_cle or int(f) != 2:
                    type_cle[t] = k
            types = [t for t in TYPES if t in type_cle]
            if not types or (side == 'ALT' and all(type_cle[t].startswith('2:') for t in types)):
                continue
            cols = {}
            for t in types:
                arr = w['rows'].get(type_cle[t]) or []
                nz = [c for c in range(w['n_weeks']) if c < len(arr) and int(arr[c] or 0) > 0]
                if nz:
                    cols[t] = (nz[0], nz[-1])
            lignes_t = {t: [r for r in rows if r['formation'] in (side, 'MUT') and _type(r) == t] for t in cols}
            for u in cols:
                for t in cols:
                    if u != t and cols[u][1] < cols[t][0] and lignes_t[u] and lignes_t[t]:
                        out.append((cid, lignes_t[u], lignes_t[t]))
    return out


# ───────────────────────── grille de la répartition souhaitée ─────────────────────────
# Le vœu se lit aussi semaine par semaine : une colonne = une semaine disponible de la
# face (semaines du semestre moins vacances et stage pour les FTP, moins entreprise pour
# les ALT, communes aux deux pour le mutualisé), la colonne 0 étant la première de ces
# semaines à partir de la semaine de début de la matière — la même pour toutes ses
# lignes, choisie au mieux. L'écart d'une ligne est la somme, sur ses semaines
# disponibles, de l'écart entre les séances placées jusque-là (cumul) et celles que la
# grille y veut : une séance décalée de d semaines compte d. Une période libre (TP, TD
# d'un seul groupe) ne fixe que son total, à sa fin. Même mesure à l'écran
# (wishOrganisation, index.html).

def _cle_voeu(rows_voeu, formation, t):
    """Ligne du vœu que suit une ligne de la répartition : celle de sa face, sinon celle
    du mutualisé ; une ligne MUT suit le mutualisé, sinon le FTP, sinon l'ALT."""
    for f in {'FTP': (0, 2), 'ALT': (1, 2), 'MUT': (2, 0, 1)}.get(formation, ()):
        if f'{f}:{t}' in rows_voeu:
            return f'{f}:{t}'
    return None


def _bande(arr, n_cols, t, n_groupes, cap):
    """m ↦ (au moins, au plus) : séances voulues en cumul à la fin de la colonne m du vœu
    (avant la colonne 0 : aucune ; après la dernière séance : toutes, et le reste de la
    ligne si elle en a plus que le vœu) ; plafonné à cap, le total de la ligne."""
    wc, acc = [], 0
    for c in range(n_cols):
        acc += arr[c]
        wc.append(acc)
    der = max((c for c in range(n_cols) if arr[c] > 0), default=-1)
    libre = {}
    for d, f in _periodes_libres(arr, n_cols, t, n_groupes):
        for m in range(d, f):
            libre[m] = (wc[d - 1] if d else 0, wc[f])

    def b(m):
        if m < 0:
            lo = hi = 0
        elif m > der:
            lo, hi = acc, max(acc, cap)
        elif m in libre:
            lo, hi = libre[m]
        else:
            lo = hi = wc[m]
        return min(lo, cap), min(hi, cap)
    return b


def _organisation(pb):
    """Matières à vœu et lignes qui suivent sa grille, par semaine de début : une pour les
    FTP (et le mutualisé), une pour les ALT — les ALT peuvent commencer plus tard.
    [{course_id, code, n, groupe: 'FTP' | 'ALT', debuts: [semaines de début possibles],
      lignes: [{r, arr, t, groupes, semaines: [semaines disponibles de sa face], j0: [rang
      de la colonne 0 dans `semaines`, pour chaque début]}]}]"""
    par_cours = defaultdict(list)
    for r in pb.lignes:
        par_cours[r['course_id']].append(r)
    sv = pb.ctx.get('semaines_voeu') or {}
    out = []
    for cid, w in (pb.ctx.get('voeux') or {}).items():
        rows = par_cours.get(cid, [])
        n = int((w or {}).get('n_weeks') or 0)
        if not rows or not n:
            continue
        listes = sv.get(rows[0]['semester']) or {}
        suivies = []
        for r in rows:
            t = _type(r)
            k = _cle_voeu(w.get('rows') or {}, r['formation'], t)
            if not k:
                continue
            brut = w['rows'][k] or []
            arr = [max(0, int((brut[c] if c < len(brut) else 0) or 0)) for c in range(n)]
            ws = [x for x in (listes.get(r['formation']) or []) if pb.k(r, x) is not None]
            if sum(arr) > 0 and ws:
                suivies.append((r, k, t, arr, ws))
        if not suivies:
            continue
        groupes = defaultdict(int)          # lignes qui suivent la même ligne du vœu
        for _, k, *_ in suivies:
            groupes[k] += 1

        def reste(r, ws, s):
            return sum(1 for x in ws if pb.k(r, x) >= pb.k(r, s))

        def longueur(arr):
            return max(c for c in range(n) if arr[c] > 0) + 1
        for gnom in ('FTP', 'ALT'):
            part = [x for x in suivies if (x[0]['formation'] == 'ALT') == (gnom == 'ALT')]
            if not part:
                continue
            r0 = part[0][0]
            tous = sorted({x for *_, ws in part for x in ws}, key=lambda x: pb.k(r0, x))
            debuts = [s for s in tous if all(reste(r, ws, s) >= longueur(arr) for r, _, _, arr, ws in part)] or tous[:1]
            lignes = [{'r': r, 'arr': arr, 't': t, 'groupes': groupes[k], 'semaines': ws,
                       'j0': [sum(1 for x in ws if pb.k(r, x) < pb.k(r, s)) for s in debuts]}
                      for r, k, t, arr, ws in part]
            out.append({'course_id': cid, 'code': rows[0].get('course_code') or '', 'n': n, 'groupe': gnom,
                        'debuts': debuts, 'lignes': lignes})
    return out


def _ecart_grille(pb, org, L, placement, i):
    """Écart d'une ligne à la grille pour le i-e début, placement {clé: {semaine: n}}."""
    r = L['r']
    cap = sum(v for v in placement.get(_cle(r), {}).values() if v > 0)
    if cap <= 0:
        return 0                     # ligne pas encore placée : rien à comparer
    b = _bande(L['arr'], org['n'], L['t'], L['groupes'], cap)
    tot = 0
    for j, x in enumerate(L['semaines']):
        X = _cumul_a(pb, r, placement, pb.k(r, x))
        lo, hi = b(j - L['j0'][i])
        tot += max(0, X - hi, lo - X)
    return tot


def _ecarts_grille(pb, placement, orgs=None):
    """{course_id: (écart au mieux, {'FTP' | 'ALT': semaine de début})} des matières du
    périmètre : chaque semaine de début choisie au mieux."""
    out = {}
    for org in (orgs if orgs is not None else _organisation(pb)):
        if not any(_cle(L['r']) in pb.cles_libres for L in org['lignes']):
            continue
        meilleur = None
        for i, s in enumerate(org['debuts']):
            e = sum(_ecart_grille(pb, org, L, placement, i) for L in org['lignes'])
            if meilleur is None or e < meilleur[0]:
                meilleur = (e, s)
        tot, debuts = out.get(org['course_id'], (0, {}))
        out[org['course_id']] = (tot + meilleur[0], {**debuts, org['groupe']: meilleur[1]})
    return out


def _atomes(pb):
    """Parties indivisibles de chaque promotion : {(année, face, min, max): {clés des lignes}}."""
    bornes = defaultdict(set)
    pubs = {}
    for r in pb.lignes:
        p = pb.ctx['publics'].get(_cle(r)) or ()
        pubs[_cle(r)] = p
        for an, face, lo, hi in p:
            bornes[(an, face)].update((lo, hi))
    out = {}
    for (an, face), bs in bornes.items():
        bs = sorted(bs)
        for lo, hi in zip(bs, bs[1:]):
            membres = frozenset(c for c, p in pubs.items()
                                if any(a == an and f == face and l < hi and h > lo for a, f, l, h in p))
            if membres:
                out[(an, face, lo, hi)] = membres
    # Seules les parties maximales comptent (une partie incluse a moins d'heures)
    return {k: m for k, m in out.items() if not any(m < m2 for m2 in out.values())}


def _enseignants(pb):
    """{nom: [(ligne, nombre de groupes qu'il y assure)]} — une ligne de CM / PT à
    plusieurs groupes compte autant de fois qu'il en assure (comme le Contrôle)."""
    out = defaultdict(list)
    for r in pb.lignes:
        noms = [n for n in (r.get('teachers') or []) if n]
        for nom in set(noms):
            out[nom].append((r, noms.count(nom)))
    return out


def _voisinages(pb):
    """Morceaux de l'optimisation par voisinages : ensembles de matières du périmètre
    (course_id) libérées ensemble. D'abord des paquets de matières voisines, qui couvrent
    tout le périmètre ; puis les deux matières de chaque ordonnancement, les matières de
    chaque enseignant, et un second découpage en paquets, décalé."""
    cours = []
    for r in sorted(pb.libres, key=lambda r: (r['semester'], r['course_code'])):
        if r['course_id'] not in cours:
            cours.append(r['course_id'])
    libres = set(cours)
    vs = []

    def ajouter(s):
        s = set(s) & libres
        if s and s not in vs:
            vs.append(s)
    # Petits morceaux d'abord : une matière seule se recalcule en une fraction de seconde
    # et rapporte le plus (grille du vœu, ordre de ses types) ; les paquets, plus lents,
    # servent ensuite à déplacer des matières qui se gênent
    for cid in cours:
        ajouter({cid})
    for o in pb.ctx['ordres']:
        ajouter({o['pred_id'], o['succ_id']})
    for nom, rows in sorted(_enseignants(pb).items()):
        cs = sorted({r['course_id'] for r, _ in rows if r['course_id'] in libres})
        if 2 <= len(cs) <= 8:
            ajouter(cs)
    taille = 4
    for i in range(0, len(cours), taille):
        ajouter(cours[i:i + taille])
    for i in range(taille // 2, len(cours), taille):
        ajouter(cours[i:i + taille])
    return vs


# ───────────────────────── départ glouton ─────────────────────────

def _depart_glouton(pb, a_placer, fixe):
    """Placement de départ des lignes `a_placer` (mode zéro, ou lignes vides) : chaque
    ligne en un bloc de semaines consécutives de sa plage (à défaut, de ses semaines
    permises), là où sa promotion est la moins chargée ; les matières d'avant un
    ordonnancement d'abord, et celles d'après seulement après leur fin (+ écart).
    `fixe` : placement déjà connu {clé: {semaine: n}} (lignes gardées).
    → {clé: {semaine: n}}"""
    charge = defaultdict(float)          # (année, face, semaine) → heures

    def poser(r, pl):
        slot = r.get('slot_duration') or 1.5
        for w, v in pl.items():
            for f in _faces(r):
                charge[(pb.annee(r), f, w)] += v * slot
    for c, pl in fixe.items():
        poser(pb.par_cle[c], pl)
    # Rang topologique des matières (ordonnancements) : d'avant avant d'après
    rang = defaultdict(int)
    for _ in range(len(pb.ctx['ordres']) + 1):
        bouge = False
        for o in pb.ctx['ordres']:
            if rang[o['succ_id']] <= rang[o['pred_id']]:
                rang[o['succ_id']] = rang[o['pred_id']] + 1
                bouge = True
        if not bouge:
            break
    ordre_type = {t: i for i, t in enumerate(TYPES)}
    lignes = sorted(a_placer, key=lambda r: (rang[r['course_id']], r['course_id'],
                                             ordre_type.get(_type(r), 9), len(pb.permises(r))))
    places = dict(fixe)
    out = {}
    for r in lignes:
        perm = pb.permises(r)
        plage = pb.plage(r)
        ws = [w for w in perm if not plage or w in plage] or perm
        n_cible = pb.cible(r)
        if not ws or n_cible <= 0:
            out[_cle(r)] = {}
            continue
        # Au plus tôt après la fin des matières qui doivent la précéder (même face)
        kmin = -1
        for o in pb.ctx['ordres']:
            if o['succ_id'] != r['course_id'] or (o['succ_part'] and o['succ_part'] != _type(r)):
                continue
            for c, pl in places.items():
                rp = pb.par_cle[c]
                if rp['course_id'] != o['pred_id'] or (o['pred_part'] and o['pred_part'] != _type(rp)):
                    continue
                if not (set(_faces(rp)) & set(_faces(r))):
                    continue
                ks = [pb.k(rp, w) for w, v in pl.items() if v > 0 and pb.k(rp, w) is not None]
                if ks:
                    kmin = max(kmin, max(ks) + (o.get('gap') or 0))
        ws2 = [w for w in ws if pb.k(r, w) is not None and pb.k(r, w) > kmin] or ws
        cap = pb.spw(r)
        long = min(len(ws2), max(1, -(-n_cible // cap)))
        meilleur = None
        for s in range(0, len(ws2) - long + 1):
            fen = ws2[s:s + long]
            pire = max(charge[(pb.annee(r), f, w)] for w in fen for f in _faces(r))
            if meilleur is None or pire < meilleur[0] - 1e-9:
                meilleur = (pire, fen)
        fen = meilleur[1]
        pl = defaultdict(int)
        reste = n_cible
        for w in fen:                       # une séance par semaine, puis on complète
            if reste <= 0:
                break
            pl[w] += 1
            reste -= 1
        i = 0
        while reste > 0 and i < 50 * len(fen):
            w = fen[i % len(fen)]
            if pl[w] < cap:
                pl[w] += 1
                reste -= 1
            i += 1
        pl = dict(pl)
        out[_cle(r)] = pl
        places[_cle(r)] = pl
        poser(r, pl)
    return out


# ───────────────────────── modèle ─────────────────────────

_HIGHS_GARDE = None


def _solveur_garde(temps, ecart, depart):
    """HiGHS (API highspy) qui garde le modèle d'un calcul à l'autre sur le même problème :
    la recherche par morceaux ne change que des bornes de variables, et PuLP repasse sinon
    tout le modèle à HiGHS, coefficient par coefficient, à chaque morceau (~3 s pour un
    semestre). Ici le modèle est lu une fois (getLp), puis chaque calcul part d'un HiGHS
    neuf (son horloge, sa limite de temps) qui le reçoit d'un bloc (passModel) avec les
    bornes du moment. Solution de départ transmise (setSolution). None sans highspy."""
    global _HIGHS_GARDE
    try:
        from pulp.apis import highs_api
        highspy = highs_api.highspy
        import numpy as np
    except Exception:
        return None
    if highspy is None:
        return None
    if _HIGHS_GARDE is None:
        class _HiGHSGarde(pulp.HiGHS):
            def __init__(self, depart=None, **kw):
                super().__init__(**kw)
                self.depart = depart or {}

            def actualSolve(self, lp):
                vs = getattr(lp, '_highs_vars', None)
                self.createAndConfigureSolver(lp)          # HiGHS neuf : options, temps de ce calcul
                h = lp.solverModel
                if vs is None:
                    self.buildSolverModel(lp)
                    lp._highs_modele, lp._highs_vars = h.getLp(), list(lp.variables())
                else:
                    inf, m = highspy.kHighsInf, lp._highs_modele
                    m.col_lower_ = np.array([-inf if v.lowBound is None else v.lowBound for v in vs], dtype=np.float64)
                    m.col_upper_ = np.array([inf if v.upBound is None else v.upBound for v in vs], dtype=np.float64)
                    h.passModel(m)
                if self.depart:
                    cols = [(v.index, float(self.depart[v.name])) for v in lp._highs_vars if v.name in self.depart]
                    if cols:
                        idx, val = zip(*cols)
                        h.setSolution(len(idx), np.array(idx, dtype=np.int32), np.array(val, dtype=np.float64))
                h.run()
                status, sol_status = self.findSolutionValues(lp)
                lp.assignStatus(status, sol_status)
                return status
        _HIGHS_GARDE = _HiGHSGarde
    return _HIGHS_GARDE(depart=depart, msg=False, timeLimit=temps, gapRel=ecart)


def optimiser(lignes, ctx, params, nom_solveur='HiGHS', solveur_factory=None):
    """→ {propositions: {(sid, g): {semaine: heures}}, avant, apres, statut, duree_s, ...}"""
    t0 = time.monotonic()
    pb = Probleme(lignes, ctx, params)
    P = dict(POIDS, **(params.get('poids') or {}))
    if not pb.libres:
        return {'propositions': {}, 'statut': 'rien à optimiser', 'duree_s': 0, 'lignes': 0}
    stable = pb.mode == 'stable'
    prob = pulp.LpProblem('repartition', pulp.LpMinimize)
    # Lignes qui suivent la grille d'un vœu : leurs interruptions sont voulues, sans coût
    orgs = _organisation(pb) if P.get('organisation', 0) > 0 else []
    suit_grille = {_cle(L['r']) for org in orgs for L in org['lignes']}
    n, y, perm_de, termes = {}, {}, {}, []      # termes : [(catégorie, expression)]
    cumv, rangs_de = {}, {}                      # cumul par (ligne, semaine) ; rangs des semaines permises
    depart = {}
    # Départ : la répartition actuelle (mode stable ; les lignes vides, au glouton) ou
    # un placement glouton de tout le périmètre (mode zéro)
    fixe = {c: pl for c, pl in pb.actuel.items() if c not in pb.cles_libres}
    if stable:
        gardees = {c: dict(pb.actuel[c]) for c in pb.cles_libres if pb.actuel[c]}
        vides = [r for r in pb.libres if not pb.actuel[_cle(r)]]
        dep_tout = dict(gardees)
        dep_tout.update(_depart_glouton(pb, vides, {**fixe, **gardees}))
    else:
        dep_tout = _depart_glouton(pb, pb.libres, fixe)

    for r in pb.libres:
        c = _cle(r)
        perm = pb.candidates(r)
        perm_de[c] = perm
        a0 = pb.actuel[c]
        cap = pb.spw(r)
        tag = f'{c[0]}_{c[1]}'
        for w in perm:
            ub = max(cap, a0.get(w, 0)) if stable else cap
            n[c, w] = pulp.LpVariable(f'n_{tag}_{w}', lowBound=0, upBound=ub, cat='Integer')
            y[c, w] = pulp.LpVariable(f'y_{tag}_{w}', cat='Binary')
            prob += n[c, w] <= ub * y[c, w]
            prob += y[c, w] <= n[c, w]
        # Cumul des séances placées jusqu'à chaque semaine (ordre de l'année) : une
        # variable par semaine, que les règles du vœu reprennent au lieu de la somme
        # (le modèle garde ainsi peu de coefficients, ce qui accélère HiGHS)
        prec = None
        for w in perm:
            C = pulp.LpVariable(f'C_{tag}_{w}', lowBound=0)
            prob += C == (prec + n[c, w] if prec is not None else n[c, w])
            cumv[c, w] = C
            prec = C
        rangs_de[c] = [pb.k(r, w) for w in perm]
        # Total : la cible, ce qui manque est payé (manque de semaines possibles)
        manque = pulp.LpVariable(f'manque_{tag}', lowBound=0)
        prob += pulp.lpSum(n[c, w] for w in perm) + manque == pb.cible(r)
        termes.append(('non_place', P['non_place'] * manque))
        plage = pb.plage(r)
        if plage:
            for w in perm:
                if w in plage:
                    continue
                if stable and a0.get(w, 0):
                    # Mode « bouger peu » : ce que l'admin a déjà mis hors de la plage y
                    # reste sans coût ; seule une séance de plus cette semaine-là coûte
                    hp = pulp.LpVariable(f'hp_{tag}_{w}', lowBound=0)
                    prob += hp >= n[c, w] - a0[w]
                    termes.append(('hors_plage', P['hors_plage'] * hp))
                else:
                    termes.append(('hors_plage', P['hors_plage'] * n[c, w]))
        if stable:
            for w in perm:
                d = pulp.LpVariable(f'd_{tag}_{w}', lowBound=0)
                prob += d >= n[c, w] - a0.get(w, 0)
                prob += d >= a0.get(w, 0) - n[c, w]
                termes.append(('deplacement', P['deplacement'] * d))
        # Interruptions : un bloc de semaines (permises consécutives) en plus coûte
        for j, w in enumerate(perm if c not in suit_grille else []):
            b = pulp.LpVariable(f'b_{tag}_{w}', lowBound=0)
            prob += b >= y[c, w] - (y[c, perm[j - 1]] if j else 0)
            termes.append(('bloc', P['bloc'] * b))
        dep = {w: v for w, v in dep_tout.get(c, {}).items() if w in perm}
        for w in perm:
            v = min(dep.get(w, 0), n[c, w].upBound)
            depart[n[c, w].name] = v
            depart[y[c, w].name] = 1 if v > 0 else 0

    def heures(c, w):
        """Heures de la ligne c la semaine w : variable si libre, constante sinon."""
        r = pb.par_cle[c]
        slot = r.get('slot_duration') or 1.5
        if c in pb.cles_libres:
            return slot * n[c, w] if (c, w) in n else 0
        return slot * pb.actuel[c].get(w, 0)

    # Charges des promotions (partie par partie) et des enseignants
    for (an, face, lo, hi), membres in _atomes(pb).items():
        plafond = PLAFOND.get(face)
        libres = [m for m in membres if m in pb.cles_libres]
        if not plafond or not libres:
            continue
        semaines = {w for m in libres for w in perm_de[m]}
        pic = pulp.LpVariable(f'pic_{an}_{face}_{lo.numerator}_{lo.denominator}', lowBound=0)
        termes.append(('pic', P['pic'] * pic))
        for w in semaines:
            charge = pulp.lpSum(heures(m, w) for m in membres)
            sur = pulp.LpVariable(f'sur_{an}_{face}_{lo.numerator}_{lo.denominator}_{w}', lowBound=0)
            prob += sur >= charge - plafond
            prob += pic >= charge
            termes.append(('charge', P['charge'] * sur))
    for i, (nom, rows) in enumerate(sorted(_enseignants(pb).items())):
        libres = [(r, m) for r, m in rows if _cle(r) in pb.cles_libres]
        if not libres:
            continue
        semaines = {w for r, _ in libres for w in perm_de[_cle(r)]}
        for w in semaines:
            charge = pulp.lpSum(m * heures(_cle(r), w) for r, m in rows)
            sur = pulp.LpVariable(f'ens_{i}_{w}', lowBound=0)
            prob += sur >= charge - PLAFOND_ENSEIGNANT
            termes.append(('enseignant', P['enseignant'] * sur))

    # Ordonnancements : première semaine d'après > dernière semaine d'avant + écart
    for j, (o, cote, pred, succ) in enumerate(_ordres(pb)):
        if not ({_cle(r) for r in pred + succ} & pb.cles_libres):
            continue
        K = max(len(v) for v in pb.rang.values()) + (o.get('gap') or 0) + 2
        L = pulp.LpVariable(f'L_{j}', lowBound=0)
        F = pulp.LpVariable(f'F_{j}', lowBound=0, upBound=K)
        for r in pred:
            c = _cle(r)
            if c in pb.cles_libres:
                for w in perm_de[c]:
                    prob += L >= pb.k(r, w) * y[c, w]
            else:
                ks = [pb.k(r, w) for w, v in pb.actuel[c].items() if v > 0 and pb.k(r, w) is not None]
                if ks:
                    prob += L >= max(ks)
        for r in succ:
            c = _cle(r)
            if c in pb.cles_libres:
                for w in perm_de[c]:
                    prob += F <= pb.k(r, w) + K * (1 - y[c, w])
            else:
                ks = [pb.k(r, w) for w, v in pb.actuel[c].items() if v > 0 and pb.k(r, w) is not None]
                if ks:
                    prob += F <= min(ks)
        retard = pulp.LpVariable(f'retard_{j}', lowBound=0)
        prob += retard >= L + (o.get('gap') or 0) + 1 - F
        termes.append(('ordre', P['ordre'] * retard))

    def cumul_expr(r, w):
        """Séances de la ligne placées jusqu'à la semaine w comprise (variable de cumul)."""
        c = _cle(r)
        kw = pb.k(r, w)
        if c in pb.cles_libres:
            j = bisect.bisect_right(rangs_de[c], kw) - 1      # dernière semaine permise ≤ w
            return cumv[c, perm_de[c][j]] if j >= 0 else 0
        return sum(v for x, v in pb.actuel[c].items() if pb.k(r, x) is not None and pb.k(r, x) <= kw)

    # Répartition souhaitée, ordre des types (_phases) : quand le vœu met toutes les
    # séances de u avant celles de t (les TP après les CM, par exemple), chaque ligne de t
    # commence au plus tôt la semaine où la dernière ligne de u finit — même semaine
    # tolérée, comme le cadre rouge ; chaque semaine d'avance coûte. Les alternances plus
    # fines (CM et TD semaine après semaine) passent par la grille ci-dessous.
    K = max(len(v) for v in pb.rang.values()) + 2
    for j, (cid, rows_u, rows_t) in enumerate(_phases(pb) if P.get('voeu', 0) > 0 else []):
        if not ({_cle(r) for r in rows_u + rows_t} & pb.cles_libres):
            continue
        L = pulp.LpVariable(f'vL_{j}', lowBound=0)
        for r in rows_u:
            c = _cle(r)
            if c in pb.cles_libres:
                for w in perm_de[c]:
                    prob += L >= pb.k(r, w) * y[c, w]
            else:
                ks = [pb.k(r, w) for w, v in pb.actuel[c].items() if v > 0 and pb.k(r, w) is not None]
                if ks:
                    prob += L >= max(ks)
        for r in rows_t:
            c = _cle(r)
            if c in pb.cles_libres:
                F = pulp.LpVariable(f'vF_{j}_{c[0]}_{c[1]}', lowBound=0, upBound=K)
                for w in perm_de[c]:
                    prob += F <= pb.k(r, w) + K * (1 - y[c, w])
            else:
                ks = [pb.k(r, w) for w, v in pb.actuel[c].items() if v > 0 and pb.k(r, w) is not None]
                if not ks:
                    continue
                F = min(ks)
            avance = pulp.LpVariable(f'va_{j}_{c[0]}_{c[1]}', lowBound=0)
            prob += avance >= L - F
            termes.append(('voeu', P['voeu'] * avance))

    # Grille de la répartition souhaitée (_organisation) : une semaine de début par
    # matière (binaires d), et pour chaque semaine disponible d'une ligne, l'écart
    # g ≥ cumul placé − au plus voulu, g ≥ au moins voulu − cumul placé
    dv = {}                                  # ((course_id, FTP|ALT), i) → binaire « début = i-e semaine »
    if P.get('organisation', 0) > 0:
        pl_depart = {c: dict(pl) for c, pl in pb.actuel.items()}
        for r in pb.libres:
            c = _cle(r)
            pl_depart[c] = {w: depart[n[c, w].name] for w in perm_de[c] if depart.get(n[c, w].name, 0) > 0}
        ng = 0
        for org in orgs:
            if not any(_cle(L['r']) in pb.cles_libres for L in org['lignes']):
                continue
            cid = (org['course_id'], org['groupe'])
            nd = len(org['debuts'])
            for i in range(nd):
                dv[cid, i] = pulp.LpVariable(f'deb_{cid[0]}_{cid[1]}_{i}', cat='Binary')
            prob += pulp.lpSum(dv[cid, i] for i in range(nd)) == 1
            for L in org['lignes']:
                r = L['r']
                c = _cle(r)
                if c not in pb.cles_libres:           # ligne figée : écart connu pour chaque début
                    termes.append(('organisation', P['organisation'] * pulp.lpSum(
                        _ecart_grille(pb, org, L, pb.actuel, i) * dv[cid, i] for i in range(nd))))
                    continue
                cap = pb.cible(r)
                if cap <= 0:
                    continue
                b = _bande(L['arr'], org['n'], L['t'], L['groupes'], cap)
                for j, x in enumerate(L['semaines']):
                    bandes = [b(j - L['j0'][i]) for i in range(nd)]
                    X = cumul_expr(r, x)
                    haut_utile = any(hi < cap for _, hi in bandes)     # sinon X ≤ cap suffit
                    bas_utile = any(lo > 0 for lo, _ in bandes)
                    if not (haut_utile or bas_utile):
                        continue
                    ng += 1
                    g = pulp.LpVariable(f'g_{ng}', lowBound=0)
                    if haut_utile:
                        prob += g >= X - pulp.lpSum(hi * dv[cid, i] for i, (_, hi) in enumerate(bandes))
                    if bas_utile:
                        prob += g >= pulp.lpSum(lo * dv[cid, i] for i, (lo, _) in enumerate(bandes)) - X
                    termes.append(('organisation', P['organisation'] * g))
            # Départ : le meilleur début pour le placement de départ
            ecarts = [sum(_ecart_grille(pb, org, L, pl_depart, i) for L in org['lignes']) for i in range(nd)]
            best = min(range(nd), key=lambda i: ecarts[i])
            for i in range(nd):
                depart[dv[cid, i].name] = 1 if i == best else 0

    prob.setObjective(pulp.lpSum(e for _, e in termes))
    fin = t0 + float(params.get('temps') or 30)
    ecart = float(params.get('ecart') or 0.01)
    discrets = {v.name: v for v in list(n.values()) + list(y.values()) + list(dv.values())}
    bornes = {nm: (v.lowBound, v.upBound) for nm, v in discrets.items()}

    def resoudre(limite, dep):
        s = _solveur_garde(limite, ecart, dep) if nom_solveur == 'HiGHS' else None
        if s is None and solveur_factory:
            s = solveur_factory(nom_solveur, limite, ecart, dep,
                                {k: v for k, v in list(n.items()) + list(y.items())})
        st = prob.solve(s)
        if any(v.varValue is None for v in n.values()):
            return st, None, None
        return st, {nm: int(round(v.varValue)) for nm, v in discrets.items()}, pulp.value(prob.objective) or 0.0

    # 1. Calcul complet, sur une partie du temps. Comme pour l'EDT, le modèle entier est
    #    trop gros pour que HiGHS l'améliore longtemps : il cale vite (racine, coupes).
    #    Les semaines de début des grilles y sont figées (meilleur début du départ) :
    #    libres, elles affaiblissent trop la relaxation ; chaque morceau les libère
    #    pour ses matières.
    for d in dv.values():
        d.lowBound = d.upBound = depart[d.name]
    part = float(params.get('part_complet', 0.3))
    statut, courant, valeur = resoudre(max(2.0, (fin - time.monotonic()) * part), depart)
    for nm, d in ((d.name, d) for d in dv.values()):
        d.lowBound, d.upBound = bornes[nm]
    trace = [('complet', len(n), valeur, round(time.monotonic() - t0, 1))]
    tours = 0
    if courant is not None:
        # 2. Par morceaux (« fix-and-optimize ») : quelques matières libres — celles d'un
        #    ordonnancement, d'un enseignant, un paquet de matières voisines —, tout le
        #    reste figé à la solution courante ; gardé s'il ne coûte pas plus.
        voisinages = _voisinages(pb)
        noms_de = defaultdict(list)          # matière → variables discrètes de ses lignes
        for (c, w), v in n.items():
            noms_de[pb.par_cle[c]['course_id']] += [v.name, y[c, w].name]
        for ((cid, _), i), d in dv.items():
            noms_de[cid].append(d.name)
        sans_gain, k = 0, 0
        while voisinages and sans_gain < len(voisinages):
            reste = fin - time.monotonic()
            if reste < 2:
                break
            libres_noms = set()
            for cid in voisinages[k % len(voisinages)]:
                libres_noms.update(noms_de[cid])
            k += 1
            for nm, v in discrets.items():
                if nm in libres_noms:
                    v.lowBound, v.upBound = bornes[nm]
                else:
                    v.lowBound = v.upBound = courant[nm]
            st, sol, val = resoudre(min(reste - 0.5, max(3.0, reste / 4)), courant)
            trace.append((len(voisinages[(k - 1) % len(voisinages)]), len(libres_noms), val,
                          round(time.monotonic() - t0, 1)))
            tours += 1
            if sol is not None and val <= valeur + 1e-6:
                sans_gain = 0 if val < valeur - 1e-6 else sans_gain + 1
                courant, valeur, statut = sol, val, st
            else:
                sans_gain += 1
        # Valeurs cohérentes avec la solution retenue (le dernier essai a pu être refusé)
        for nm, v in discrets.items():
            v.lowBound = v.upBound = courant[nm]
        resoudre(5.0, courant)
        couts = defaultdict(float)
        for cat, e in termes:
            couts[cat] += pulp.value(e) or 0.0
        trace.append(('couts', {c: round(v, 1) for c, v in sorted(couts.items())}))
        for nm, v in discrets.items():
            v.lowBound, v.upBound = bornes[nm]
    ok = courant is not None
    placement = {c: dict(pb.actuel[c]) for c in pb.actuel}
    if ok:
        for r in pb.libres:
            c = _cle(r)
            placement[c] = {w: courant[n[c, w].name] for w in perm_de[c] if courant[n[c, w].name] > 0}
    avant = evaluer(pb, pb.actuel)
    apres = evaluer(pb, placement) if ok else None
    props, deplacees, ajoutees = {}, 0, 0
    for r in pb.libres:
        c = _cle(r)
        slot = r.get('slot_duration') or 1.5
        props[c] = {w: v * slot for w, v in placement[c].items()}
        a0 = pb.actuel[c]
        plus = sum(max(0, v - a0.get(w, 0)) for w, v in placement[c].items())
        if a0:
            deplacees += plus          # séance changée de semaine
        else:
            ajoutees += plus           # ligne qui était vide
    return {'propositions': props if ok else {}, 'avant': avant, 'apres': apres,
            'statut': getattr(prob, 'sol_status', None), 'statut_pulp': pulp.LpStatus.get(statut, str(statut)),
            'duree_s': round(time.monotonic() - t0, 1), 'lignes': len(pb.libres),
            'seances_deplacees': deplacees, 'seances_ajoutees': ajoutees,
            'lignes_vides_laissees': sum(1 for r in pb.libres if not pb.actuel[_cle(r)] and not placement[_cle(r)]),
            'cout': valeur, 'morceaux_calcules': tours, 'trace': trace, 'variables': len(prob.variables()),
            'contraintes': len(prob.constraints), 'ok': ok}
