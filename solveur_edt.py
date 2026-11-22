"""Solveur d'emploi du temps hebdomadaire — programmation linéaire en nombres entiers (PuLP).

Place, semaine par semaine, les heures de la répartition (`weekly_hours`) sur une
grille au pas de 30 min — lundi → vendredi de 8 h à 20 h, samedi de 8 h à 12 h 30,
soirées (après 18 h) et samedi pris en dernier —, puis attribue les salles.
Règles du département : jeudi après-midi (dès 12 h 30) libre pour les FTP, sauf la
semaine d'un jour férié ou d'un pont ; jours fériés et ponts fermés à tous les cours.
Ces jours se définissent par année (app_settings['jours_fermes'], écran « Jours
fériés et ponts ») ; tant que la liste n'est pas enregistrée, les jours fériés
légaux (fixes et mobiles, calculés) sont pris, sans pont.

La modélisation suit celle de flop! (https://framagit.org/flopedt/flopedt) : une
variable binaire « la séance e commence au créneau s », des contraintes dures, et
des préférences pondérées dans l'objectif. Le code est écrit pour GestionEDT :
aucune ligne de flop! (AGPL) n'est reprise, seule la méthode l'est.

Correspondance avec les contraintes de flop! :

  flop!                            ici
  -------------------------------  ---------------------------------------------------
  ScheduleAllCourses               chaque séance placée au plus une fois, forte
                                   pénalité si elle ne l'est pas (signalée en conflit)
  NoSimultaneousAssigneeCourses    un enseignant n'a qu'une séance à la fois
  ConsiderTutorsUnavailability     créneaux indisponibles exclus (teacher_availability)
  MinNonPreferredTutorsSlot        coût des créneaux de priorité > 1
  RespectTutorsMaxTimePerDay       teachers.max_hours_day d'heures de CM/TD par jour
  MinTutorsHalfDays                moins de demi-journées de présence (enseignants)
  TutorsLunchBreak                 pause déjeuner (enseignants)
  NoSimultaneousGroupCourses       pas de chevauchement pour un même groupe d'étudiants
  MinGroupsHalfDays                demi-journées regroupées (étudiants)
  GroupsLunchBreak                 pause déjeuner (étudiants)
  LimitSimultaneousRoomCourses     une salle, une séance ; « STD » = pool de N salles
  ConsiderRoomSorts                salle info fixe (123) préférée à la salle mobile
  ConsiderDependencies             CM avant TD avant TP d'une matière, au jour près ;
                                   course_sequences (même semaine)
  CourseStartTimeConstraint        heures de début autorisées par durée de séance
  fixed courses / other depts      créneaux déjà posés des années non recalculées
  (règle du département)           espacement d'une matière pour les mêmes étudiants :
                                   pas deux séances le même jour, si possible pas deux
                                   jours de suite — idéal : 2 ou 3 jours d'écart

Les poids des préférences (POIDS_DEFAUT) se règlent dans la fenêtre « Générer
l'EDT » (réglage du site « edt_poids », lu par app.py) ou dans la requête (poids).

Conventions de données (celles d'app.py) :
  * formation_type : 0 = FTP, 1 = ALT, 2 = MUT (FTP + ALT ensemble), 3 = autre.
  * Nombre de groupes d'une séance : même règle que `_group_multiplier` d'app.py
    (semestre mutualisé → groupes « promo », sauf TP distincts ; TP8/TP12).
  * TD et TP : une ligne weekly_hours par groupe (group_index) ; CM et PT : une
    seule ligne (groupe 1), rejouée pour chacun de leurs groupes.
  * Séances MUT : groupes mixtes FTP + ALT (chacun prend sa part des deux faces),
    sauf les TP mutualisés à TP communs (semestre mutualisé, TP non distincts),
    dont les `alt_groups` DERNIERS groupes sont les apprentis — même règle que
    /api/repartition (alt_group) dans app.py.
  * Deux groupes d'une même face se chevauchent si leurs parts de l'effectif se
    recouvrent : le groupe g sur n couvre [(g-1)/n, g/n[ (TD1 sur 2 = TP1+TP2 sur 4).
  * teacher_availability.day_of_week : 0 = lundi … 4 = vendredi ; priority 1 = le
    mieux ; available = 0 → indisponible. Dès qu'un enseignant a déclaré des
    créneaux disponibles, le reste de la semaine lui est fermé (« liste de dispos »).
  * Salles : room_name « STD » = n'importe quelle salle banale (types standard, TD,
    Amphi) ; « 123 » = salle info fixe + salle info mobile, la mobile occupant en
    plus une salle banale ; autre nom = cette salle précise ; vide = pas de salle.

Résolution, semaine par semaine, en deux phases : (1) modèle réduit aux contraintes
dures, qui place le plus d'heures possible ; (2) modèle complet, ce niveau de
placement imposé, qui optimise les préférences en partant de la solution (1).
Environ 20 s par semaine chargée avec HiGHS ; une requête s'arrête à `temps_total`
(100 s, gunicorn coupe à 120 s) et renvoie les `semaines_restantes` à relancer.

Utilisation :
  * depuis Flask : POST /api/generate-timetable, corps JSON par ex.
        {"semaines": [46, 47], "annees": [1], "simulation": true}
    (voir lire_reglages pour tous les réglages) ;
  * en ligne de commande, sur une COPIE de base :
        python solveur_edt.py copie.db --semaines 46 47 [--ecrire]
"""

from __future__ import annotations

import json
import math
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from fractions import Fraction

try:
    import pulp
except ImportError:  # PuLP absent : app.py retombe sur l'ancien générateur
    pulp = None


JOURS = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi']
FACES = {0: 'FTP', 1: 'ALT'}
RANG_TYPE = {'CM': 0, 'TD': 1, 'TP': 2}
TYPES_SALLE_BANALE = {'standard', 'td', 'amphi'}
NOMS_HORS_POOL = {'STD', 'SITE'}
SOLVEURS = ('HiGHS', 'PULP_CBC_CMD', 'COIN_CMD', 'GUROBI_CMD')

# Coûts par pas de 30 min, sauf demi-journées (par demi-journée) et ordre (par paire).
# Échelle inspirée de flop! : une séance non placée coûte bien plus que toute préférence.
POIDS_DEFAUT = {
    'non_place': 100.0,             # séance non placée (par 30 min)
    'pref_enseignant': 1.0,         # créneau non préféré (coût normalisé, moyenne 1)
    'demi_journee_enseignant': 3.0,
    'demi_journee_groupe': 1.0,
    'dejeuner': 4.0,                # par 30 min de pause déjeuner manquante
    'salle_info_mobile': 0.5,       # par 30 min passées en salle info mobile
    'ordre_cm_td_tp': 5.0,          # par paire inversée (TD un jour avant son CM, TP avant son TD)
    'enchainement': 20.0,           # idem pour course_sequences (même semaine)
    # Espacement d'une matière pour un même groupe d'étudiants (CM, TD et TP confondus)
    'matiere_meme_jour': 10.0,      # par séance en trop le même jour
    'matiere_lendemain': 3.0,       # par paire de jours consécutifs (lundi puis mardi)
    'matiere_ecart_long': 1.0,      # 4 jours ou plus sans elle entre deux séances (lundi puis vendredi)
    'soir_samedi': 1.0,             # par 30 min de cours après 18 h ou le samedi (permis, mais en dernier)
}
# Ancien nom → nouveau (requêtes ou réglages enregistrés avant le renommage)
POIDS_ALIAS = {'etalement': 'matiere_meme_jour'}

# Poids réglables dans la fenêtre « Générer l'EDT » : (clé, libellé, unité, explication).
# « non_place » n'y figure pas : le placement passe toujours avant les préférences
# (phase 1 du calcul, puis niveau imposé à la phase 2), son poids n'y change rien.
POIDS_INFOS = [
    ('matiere_meme_jour', 'Même matière deux fois le même jour', 'par séance en trop',
     "Pour un même groupe d'étudiants, CM, TD et TP confondus. Poids fort : c'est le minimum d'un jour d'écart."),
    ('matiere_lendemain', 'Même matière deux jours de suite', 'par paire de jours',
     "Lundi puis mardi, par exemple. L'idéal est 2 ou 3 jours d'écart."),
    ('matiere_ecart_long', 'Même matière à 4 jours ou plus d’écart', 'par écart',
     'Lundi puis vendredi, sans séance entre les deux.'),
    ('pref_enseignant', "Créneau non préféré d'un enseignant", 'par 30 min',
     'Créneaux de niveau 2 à 4 de sa grille de dispos (coût moyen 1).'),
    ('demi_journee_enseignant', "Demi-journée de présence d'un enseignant", 'par demi-journée',
     'Plus il est fort, plus les cours de chacun sont regroupés.'),
    ('demi_journee_groupe', "Demi-journée de présence d'un groupe", 'par demi-journée',
     'Idem pour les étudiants.'),
    ('dejeuner', 'Pause déjeuner manquante', 'par 30 min', "Moins d'une heure libre entre 12 h et 14 h."),
    ('ordre_cm_td_tp', 'Ordre CM → TD → TP non respecté', 'par paire', 'TD placé un jour avant son CM, TP avant son TD.'),
    ('enchainement', 'Enchaînement imposé non respecté', 'par paire', 'Ordres saisis dans Contraintes Matière.'),
    ('salle_info_mobile', 'Salle info mobile plutôt que fixe', 'par 30 min', ''),
    ('soir_samedi', 'Cours après 18 h ou le samedi', 'par 30 min', 'Permis, mais pris en dernier.'),
]
POIDS_MAX = 1000.0


# ───────────────────────── outils ─────────────────────────

def solveur_disponible():
    """Nom du premier solveur PuLP utilisable, ou None."""
    if pulp is None:
        return None
    try:
        dispo = set(pulp.listSolvers(onlyAvailable=True))
    except Exception:
        return None
    return next((s for s in SOLVEURS if s in dispo), None)


def _minutes(hhmm):
    h, m = str(hhmm).strip().split(':')[:2]
    return int(h) * 60 + int(m)


def _hhmm(minutes):
    return f'{minutes // 60:02d}:{minutes % 60:02d}'


def _rows(db, sql, args=()):
    cur = db.execute(sql, args)
    noms = [c[0] for c in cur.description]
    return [dict(zip(noms, r)) for r in cur.fetchall()]


def _table_existe(db, nom):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nom,)).fetchone() is not None


def _norm_type(tt):
    return (tt or '').upper().replace(' ', '')


def _par_groupe(tt):
    """TD et TP : une ligne de répartition par groupe (cf. app._placed_by_group)."""
    tt = _norm_type(tt)
    return tt.startswith('TP') or tt == 'TD'


def _nb_groupes(sg, mut, tpsep, sem, ft, tt, tp_type):
    """Nombre de groupes d'une séance — même règle que app._group_multiplier."""
    tt = _norm_type(tt)
    if tt == 'CM':
        return 1
    if sem in mut and not (tt.startswith('TP') and sem in tpsep):
        ft = 2
    groupes = sg.get((sem, ft))
    if not groupes:
        return 1
    if tt.startswith('TP'):
        tt = 'TP8' if _norm_type(tp_type) == 'TP8' else 'TP'
    return max(1, int(groupes.get(tt) or 1))


def _norm_salle(nom):
    nom = (nom or '').strip().upper()
    return (nom.lstrip('0') or nom) if nom.isdigit() else nom


# ───────────────────────── réglages ─────────────────────────

@dataclass
class Reglages:
    semaines: list
    debut: int = 8 * 60
    fin: int = 20 * 60           # lundi → vendredi, 8 h → 20 h
    pas: int = 30
    jours: list = field(default_factory=lambda: [0, 1, 2, 3, 4, 5])
    samedi_fin: int = 12 * 60 + 30   # samedi : le matin seulement, 8 h → 12 h 30
    soiree: int = 18 * 60            # au-delà : créneau permis mais pénalisé (poids soir_samedi)
    jeudi_ftp_libre: int | None = 12 * 60 + 30   # jeudi après-midi libre pour les FTP à partir de…
    feries: bool = True              # jours fériés et ponts fermés ; leur semaine rouvre le jeudi après-midi
    annee_universitaire: str = ''    # « 2026-2027 » : dates des semaines (jours fériés)
    dejeuner: tuple | None = (12 * 60, 14 * 60, 60)   # (début, fin, minutes libres)
    temps_max: float = 20.0      # secondes par semaine (au-delà, gain constaté nul)
    temps_total: float = 100.0   # budget de la requête (gunicorn coupe à 120 s)
    ecart: float = 0.02          # écart relatif toléré à l'optimum
    dispos_exclusives: bool = True
    nb_salles_std: int | None = None
    salle_info: str = '123'
    capacite_info: int = 2
    annees: set | None = None
    debuts: set | None = None    # heures de début imposées (minutes) ; None = grille par durée
    grille_libre: bool = False   # True : début possible à chaque pas (modèle bien plus lourd)
    apres_midi: int = 13 * 60 + 30
    blocages: list = field(default_factory=list)
    simulation: bool = False
    solveur: str | None = None
    poids: dict = field(default_factory=lambda: dict(POIDS_DEFAUT))

    @property
    def nb_pas(self):
        return (self.fin - self.debut) // self.pas

    def debuts_pour(self, lon):
        """Pas de début autorisés pour une séance de `lon` pas (CourseStartTimeConstraint de flop!).

        Par défaut, les séances d'une même durée s'enchaînent depuis le début de la
        matinée, depuis le début de l'après-midi, ou à rebours depuis la fin de
        journée ; une séance du matin finit au plus tard à l'heure qui laisse la
        pause déjeuner libre. Restreindre les débuts rend le modèle bien plus
        facile à résoudre qu'une grille où tout chevauche tout."""
        U, dur = self.nb_pas, lon * self.pas
        if self.debuts is not None:
            return {u for u in range(U - lon + 1) if self.debut + u * self.pas in self.debuts}
        if self.grille_libre:
            return set(range(U - lon + 1))
        fin_matin = self.dejeuner[0] + (self.dejeuner[1] - self.dejeuner[0] - self.dejeuner[2]) \
            if self.dejeuner else self.apres_midi
        minutes = set()
        m = self.debut
        while m + dur <= fin_matin:
            minutes.add(m)
            m += dur
        m = self.apres_midi
        while m + dur <= self.fin:
            minutes.add(m)
            m += dur
        m = self.fin - dur
        while m >= self.apres_midi:
            minutes.add(m)
            m -= dur
        if not minutes:              # séance très longue : à défaut, n'importe quel pas
            return set(range(U - lon + 1))
        return {(m - self.debut) // self.pas for m in minutes
                if (m - self.debut) % self.pas == 0 and 0 <= (m - self.debut) // self.pas <= U - lon}


def lire_poids(poids):
    """Poids valides {clé: float} d'après un dict (anciens noms acceptés) ; ValueError sinon."""
    if not isinstance(poids, dict):
        raise ValueError('poids : objet {nom: valeur} attendu')
    out = {}
    for cle, val in poids.items():
        cle = POIDS_ALIAS.get(cle, cle)
        if cle not in POIDS_DEFAUT:
            raise ValueError(f'Poids inconnu : {cle}')
        try:
            v = float(val)
        except (TypeError, ValueError):
            raise ValueError(f'Poids {cle} : nombre attendu') from None
        if not (0 <= v <= POIDS_MAX):     # rejette aussi NaN
            raise ValueError(f'Poids {cle} : entre 0 et {POIDS_MAX:g}')
        out[cle] = v
    return out


def lire_reglages(data):
    """Construit les réglages depuis le JSON de la requête (clés FR, alias EN)."""
    data = data or {}
    g = lambda *cles, defaut=None: next((data[c] for c in cles if data.get(c) is not None), defaut)
    try:
        reg = Reglages(semaines=[int(w) for w in g('semaines', 'weeks', defaut=[])])
        reg.debut = _minutes(g('debut', 'day_start', defaut='08:00'))
        reg.fin = _minutes(g('fin', 'day_end', defaut='20:00'))
        reg.pas = int(g('pas', defaut=30))
        reg.jours = sorted({int(j) for j in g('jours', defaut=[0, 1, 2, 3, 4, 5])})
        reg.samedi_fin = _minutes(g('samedi_fin', defaut='12:30'))
        reg.soiree = _minutes(g('soiree', defaut='18:00'))
        jeudi = data.get('jeudi_ftp_libre', '12:30')
        reg.jeudi_ftp_libre = None if jeudi in (None, False, '') else _minutes('12:30' if jeudi is True else jeudi)
        reg.feries = bool(g('feries', defaut=True))
        reg.annee_universitaire = str(g('annee_universitaire', defaut=''))
        dej = data.get('pause_dejeuner', 'defaut')
        if dej is None or dej is False:
            reg.dejeuner = None
        elif isinstance(dej, dict):
            reg.dejeuner = (_minutes(dej.get('debut', '12:00')), _minutes(dej.get('fin', '14:00')),
                            int(dej.get('libre', 60)))
        reg.temps_max = float(g('temps_max', defaut=20))
        reg.temps_total = float(g('temps_total', defaut=100))
        reg.ecart = float(g('ecart', defaut=0.02))
        reg.dispos_exclusives = bool(g('dispos_exclusives', defaut=True))
        if g('nb_salles_std') is not None:
            reg.nb_salles_std = int(g('nb_salles_std'))
        reg.salle_info = str(g('salle_info', defaut='123'))
        reg.capacite_info = int(g('capacite_info', defaut=2))
        if g('annees'):
            reg.annees = {int(a) for a in g('annees')}
        if g('debuts') == 'tous':
            reg.grille_libre = True
        elif g('debuts'):
            reg.debuts = {_minutes(h) for h in g('debuts')}
        reg.apres_midi = _minutes(g('apres_midi', defaut='13:30'))
        reg.blocages = list(g('blocages', defaut=[]))
        reg.simulation = bool(g('simulation', 'dry_run', defaut=False))
        reg.solveur = g('solveur')
        reg.poids.update(lire_poids(g('poids', defaut={}) or {}))
    except (TypeError, ValueError, AttributeError) as e:
        raise ValueError(f'Réglage invalide : {e}') from e
    if reg.pas not in (5, 10, 15, 20, 30, 60) or reg.fin <= reg.debut or (reg.fin - reg.debut) % reg.pas:
        raise ValueError('Grille horaire invalide (début, fin et pas en minutes)')
    if not reg.jours or not set(reg.jours) <= set(range(6)):
        raise ValueError('Jours invalides (0 = lundi … 5 = samedi)')
    if reg.solveur and reg.solveur not in SOLVEURS:
        raise ValueError(f'Solveur inconnu : {reg.solveur}')
    return reg


# ───────────────────────── données ─────────────────────────

@dataclass
class Evenement:
    """Une séance à placer dans la semaine (le « Course » de flop!)."""
    idx: int
    session_id: int
    course_id: int
    code: str
    type: str
    formation: int
    annee: int
    groupe: int
    nb_groupes: int
    rang: int               # k-ième séance de ce (session, groupe) dans la semaine
    lon: int                # durée en pas
    enseignant: int | None
    salle: tuple | None     # ('STD',) | ('INFO',) | ('R', room_id) | ('X', nom)
    public: tuple           # ((annee, face, part_min, part_max), …)
    semestre: str = ''

    @property
    def libelle(self):
        g = f' gr{self.groupe}' if self.nb_groupes > 1 else ''
        return f'{self.code} {self.type}{g}'


class Donnees:
    """Tout ce qui ne dépend pas de la semaine, lu une fois."""

    def __init__(self, db, reg):
        self.reg = reg
        self.enseignants = {r['id']: r for r in _rows(db, 'SELECT id, name, max_hours_day, status FROM teachers')}
        self.salles = _rows(db, 'SELECT id, name, room_type FROM rooms')
        self.salle_par_nom = {_norm_salle(s['name']): s for s in self.salles}
        self.pool_std = [s for s in self.salles
                         if (s['room_type'] or '').strip().lower() in TYPES_SALLE_BANALE
                         and _norm_salle(s['name']) not in NOMS_HORS_POOL]
        ordre = {'td': 0, 'standard': 1, 'amphi': 2}
        self.pool_std.sort(key=lambda s: (ordre.get((s['room_type'] or '').strip().lower(), 3), s['name']))
        self.nb_std = reg.nb_salles_std if reg.nb_salles_std is not None else len(self.pool_std)
        self.id_pool_std = {s['id'] for s in self.pool_std}
        self.salle_info = self.salle_par_nom.get(_norm_salle(reg.salle_info))

        self.sg = {}
        if _table_existe(db, 'semester_groups'):
            for r in _rows(db, 'SELECT * FROM semester_groups'):
                self.sg[(r['semester_code'], r['formation_type'])] = {
                    'TD': r.get('td_groups'), 'TP': r.get('tp_groups'), 'TP8': r.get('tp8_groups'),
                    'PT': r.get('pt_groups'),
                    'ALT': r.get('alt_groups') if r.get('alt_groups') is not None else 1}
        self.mut, self.tpsep = set(), set()
        for r in _rows(db, 'SELECT * FROM semesters'):
            if r.get('mutualized'):
                self.mut.add(r['code'])
            if r.get('tp_separate') is None or r.get('tp_separate'):
                self.tpsep.add(r['code'])

        self.gt = defaultdict(dict)
        if _table_existe(db, 'course_group_teachers'):
            for r in _rows(db, 'SELECT course_session_id, group_index, teacher_id FROM course_group_teachers'):
                if r['teacher_id']:
                    self.gt[r['course_session_id']][r['group_index']] = r['teacher_id']

        self.enchainements = []
        if _table_existe(db, 'course_sequences'):
            self.enchainements = [(r['predecessor_session_id'], r['successor_session_id'])
                                  for r in _rows(db, 'SELECT * FROM course_sequences')
                                  if not r.get('min_gap_weeks')]

        lignes = defaultdict(list)
        if _table_existe(db, 'teacher_availability'):
            for r in _rows(db, 'SELECT * FROM teacher_availability'):
                lignes[r['teacher_id']].append(r)
        self.dispos = {tid: self._dispos(lignes.get(tid, [])) for tid in self.enseignants}

        debut_annee = 36
        if _table_existe(db, 'app_settings'):
            r = db.execute("SELECT value FROM app_settings WHERE key='academic_start_week'").fetchone()
            if r and str(r[0]).isdigit():
                debut_annee = int(r[0])
        self.debut_annee = debut_annee
        # Année universitaire (dates des semaines) : réglage, sinon nom du fichier de base
        self.annee_univ = reg.annee_universitaire
        if not re.match(r'^\d{4}-\d{4}$', self.annee_univ or ''):
            fichier = next((r[2] for r in db.execute('PRAGMA database_list').fetchall() if r[1] == 'main'), '') or ''
            m = re.search(r'(\d{4})-(\d{4})', fichier.replace('\\', '/').rsplit('/', 1)[-1])
            self.annee_univ = m.group(0) if m else ''
        # Jours fériés et ponts de l'année : {date: libellé}, ou None (liste pas encore définie)
        liste = lire_jours_fermes(db)
        self.jours_fermes = None if liste is None else {
            date.fromisoformat(j['date']): j['libelle'] or ('pont' if j['type'] == 'pont' else 'férié')
            for j in liste}

    def _dispos(self, lignes):
        """(créneaux interdits, coût par créneau, dispos saisies ?) d'un enseignant.

        Coût normalisé comme dans flop! : 0 sur les créneaux de meilleure priorité,
        1 en moyenne sur les autres (une priorité plus mauvaise coûte davantage)."""
        reg = self.reg
        if not lignes:
            return set(), {}, False
        lis = [(int(l['day_of_week']), _minutes(l['start_time']), _minutes(l['end_time']),
                int(l['available'] if l['available'] is not None else 1),
                int(l['priority'] or 1)) for l in lignes]
        indispo = [l for l in lis if not l[3]]
        dispo = [l for l in lis if l[3]]
        exclusif = reg.dispos_exclusives and bool(dispo)
        pire = max((l[4] for l in dispo), default=1)
        interdit, prio = set(), {}
        for d in reg.jours:
            for u in range(reg.nb_pas):
                t0 = reg.debut + u * reg.pas
                t1 = t0 + reg.pas
                if any(j == d and s < t1 and e > t0 for j, s, e, _, _ in indispo):
                    interdit.add((d, u))
                    continue
                touche = [l for l in dispo if l[0] == d and l[1] < t1 and l[2] > t0]
                fin_couverte = t0
                for _, s, e, _, _ in sorted(touche, key=lambda l: l[1]):
                    if s <= fin_couverte:
                        fin_couverte = max(fin_couverte, e)
                if fin_couverte >= t1:
                    prio[(d, u)] = max(l[4] for l in touche)
                elif exclusif:
                    interdit.add((d, u))
                else:
                    prio[(d, u)] = pire + 1
        cout = {}
        if prio:
            meilleure = min(prio.values())
            autres = [p for p in prio.values() if p > meilleure]
            if autres:
                moyenne = sum(autres) / len(autres)
                cout = {k: (p - meilleure) / (moyenne - meilleure) for k, p in prio.items() if p > meilleure}
        return interdit, cout, True

    def salle_de(self, nom):
        n = _norm_salle(nom)
        if not n or n == 'SITE':
            return None
        if n == 'STD':
            return ('STD',) if self.nb_std else None
        if self.salle_info and n == _norm_salle(self.salle_info['name']):
            return ('INFO',)
        s = self.salle_par_nom.get(n)
        return ('R', s['id']) if s else ('X', n)

    def public(self, annee, ft, g, n, sem, tt=''):
        """Part de l'effectif concernée : ((annee, face, min, max), …)."""
        part = (Fraction(g - 1, n), Fraction(g, n))
        if ft in FACES:
            return ((annee, FACES[ft], *part),)
        if ft == 2:
            # TP mutualisé à TP communs : les apprentis occupent les DERNIERS groupes
            # (cf. app.py, /api/repartition : is_common_mut / alt_group)
            if _norm_type(tt).startswith('TP') and sem in self.mut and sem not in self.tpsep and n > 1:
                k_alt = max(0, min(int((self.sg.get((sem, 2)) or {}).get('ALT') or 0), n))
                n_ftp = n - k_alt
                if g <= n_ftp:
                    return ((annee, 'FTP', Fraction(g - 1, n_ftp), Fraction(g, n_ftp)),)
                j = g - n_ftp
                return ((annee, 'ALT', Fraction(j - 1, k_alt), Fraction(j, k_alt)),)
            # CM / TD / PT mutualisés (et TP MUT distincts) : groupes mixtes FTP + ALT
            return ((annee, 'FTP', *part), (annee, 'ALT', *part))
        return ((annee, f'AUTRE{ft}', Fraction(0), Fraction(1)),)


def _filtre_annees(reg, alias='s'):
    if not reg.annees:
        return '', ()
    return f' AND {alias}.year_group IN ({",".join("?" * len(reg.annees))})', tuple(sorted(reg.annees))


def evenements_semaine(db, don, semaine, avert):
    """Découpe la répartition d'une semaine en séances à placer."""
    reg = don.reg
    filtre, args = _filtre_annees(reg)
    lignes = _rows(db, f'''
        SELECT cs.id AS sid, cs.course_id, cs.teacher_id, cs.formation_type, cs.teaching_type,
               cs.slot_duration, cs.room_name, c.code, c.tp_type, s.code AS sem, s.year_group,
               wh.group_index, wh.hours
        FROM weekly_hours wh
        JOIN course_sessions cs ON cs.id = wh.course_session_id
        JOIN courses c ON c.id = cs.course_id
        JOIN semesters s ON s.id = c.semester_id
        WHERE wh.week_number = ? AND wh.hours > 0{filtre}
        ORDER BY cs.id, wh.group_index''', (semaine, *args))
    evts = []
    for r in lignes:
        tt = _norm_type(r['teaching_type'])
        ft = r['formation_type'] if r['formation_type'] is not None else 0
        n = _nb_groupes(don.sg, don.mut, don.tpsep, r['sem'], ft, tt, r['tp_type'])
        gi = int(r['group_index'] or 1)
        if _par_groupe(tt):
            groupes = [gi]
        elif gi != 1:
            continue          # CM / PT : seul le groupe 1 porte le placement
        else:
            groupes = range(1, n + 1)
        duree = float(r['slot_duration'] or 1.5)
        heures = float(r['hours'])
        nb = int(math.floor(heures / duree + 1e-6))
        durees = [duree] * nb
        reste = round(heures - nb * duree, 4)
        if reste * 60 >= reg.pas - 1e-6:
            durees.append(reste)
        for g in groupes:
            nn = max(n, g)
            ens = don.gt.get(r['sid'], {}).get(g, r['teacher_id'])
            if ens is not None and ens not in don.enseignants:
                ens = None
            for k, h in enumerate(durees):
                lon = round(h * 60 / reg.pas)
                if lon <= 0:
                    continue
                if abs(lon * reg.pas - h * 60) > 1:
                    avert.append(f'S{semaine} · {r["code"]} {tt} : {h} h arrondi à {lon * reg.pas} min')
                if lon > reg.nb_pas:
                    avert.append(f'S{semaine} · {r["code"]} {tt} : séance de {h} h plus longue que la journée')
                    continue
                evts.append(Evenement(
                    idx=len(evts), session_id=r['sid'], course_id=r['course_id'], code=r['code'], type=tt,
                    formation=ft, annee=r['year_group'], groupe=g, nb_groupes=nn, rang=k, lon=lon,
                    enseignant=ens, salle=don.salle_de(r['room_name']),
                    public=don.public(r['year_group'], ft, g, nn, r['sem'], tt), semestre=r['sem']))
    return evts


def occupations_fixes(db, don, semaine):
    """Créneaux déjà posés des années qu'on ne recalcule pas (les « fixed courses » de flop!)."""
    reg = don.reg
    if not reg.annees:
        return []
    pl = ','.join('?' * len(reg.annees))
    return _rows(db, f'''
        SELECT ts.day_of_week, ts.start_time, ts.end_time, ts.teacher_id, ts.room_id, cs.room_name
        FROM timetable_slots ts
        JOIN course_sessions cs ON cs.id = ts.course_session_id
        JOIN courses c ON c.id = cs.course_id
        JOIN semesters s ON s.id = c.semester_id
        WHERE ts.week_number = ? AND s.year_group NOT IN ({pl})''', (semaine, *sorted(reg.annees)))


def publics_creneaux(db, creneaux, don=None):
    """Ajoute à chaque créneau enregistré (course_session_id, group_index) ses publics :
    [[année, 'FTP'|'ALT'], …] — mêmes règles de groupes que le solveur (un TP mutualisé
    à TP communs n'est que FTP ou qu'ALT selon son groupe). Sert à la vue Planning."""
    don = don or Donnees(db, lire_reglages({}))
    info = {r['sid']: r for r in _rows(db, '''
        SELECT cs.id AS sid, cs.teaching_type, cs.formation_type, c.tp_type, s.code AS sem, s.year_group
        FROM course_sessions cs JOIN courses c ON c.id = cs.course_id JOIN semesters s ON s.id = c.semester_id''')}
    for c in creneaux:
        r = info.get(c.get('course_session_id'))
        if not r:
            c['publics'] = []
            continue
        tt = _norm_type(r['teaching_type'])
        ft = r['formation_type'] if r['formation_type'] is not None else 0
        g = int(c.get('group_index') or 1)
        n = max(_nb_groupes(don.sg, don.mut, don.tpsep, r['sem'], ft, tt, r['tp_type']), g)
        c['publics'] = sorted({(a, f) for a, f, _, _ in don.public(r['year_group'], ft, g, n, r['sem'], tt)})
    return creneaux


# ───────────────────────── modèle d'une semaine ─────────────────────────

def _atomes(evts):
    """Parties d'effectif indivisibles : {frozenset(idx des séances qui la touchent)}."""
    bornes = defaultdict(set)
    for e in evts:
        for an, face, lo, hi in e.public:
            bornes[(an, face)].update((lo, hi))
    atomes = {}
    for (an, face), bs in bornes.items():
        bs = sorted(bs)
        for lo, hi in zip(bs, bs[1:]):
            membres = frozenset(e.idx for e in evts for a2, f2, l2, h2 in e.public
                                if a2 == an and f2 == face and l2 < hi and h2 > lo)
            if membres:
                atomes.setdefault(membres, (an, face, lo, hi))
    return atomes


def _espacement_matieres(evts, maximaux):
    """Séances d'une même matière qu'un même groupe d'étudiants suit dans la semaine.

    Pour chaque partie d'effectif indivisible (atome maximal) et chaque matière
    (course_id : CM, TD et TP confondus), l'ensemble de ses séances qui touchent
    cette partie ; seuls les ensembles d'au moins deux séances et non inclus dans
    un autre de la même matière comptent (sinon un même écart serait payé
    plusieurs fois). Ex. : {CM, TD1, TP1} pour les étudiants du TP1."""
    par_mat = defaultdict(set)
    for a in maximaux:
        groupes = defaultdict(set)
        for i in a:
            groupes[evts[i].course_id].add(i)
        for c, s in groupes.items():
            if len(s) > 1:
                par_mat[c].add(frozenset(s))
    return [s for c in sorted(par_mat) for s in sorted(par_mat[c], key=sorted)
            if not any(s < t for t in par_mat[c])]


def bilan_espacement(evts, espacement, jours_de):
    """Écarts constatés dans un placement {idx: jour} : (même jour, jours consécutifs,
    4 jours ou plus), et le détail des cas « même jour » et « lendemain »."""
    mj = ld = lg = 0
    cas = []
    for ens in espacement:
        jours = sorted(jours_de[i] for i in ens if i in jours_de)
        if len(jours) < 2:
            continue
        e0 = evts[min(ens)]
        fin = max((evts[i] for i in ens), key=lambda e: e.nb_groupes)   # le groupe le plus petit
        qui = ', '.join(sorted({f'{a}A {f}' for i in ens for a, f, _, _ in evts[i].public})) \
            + (f' gr{fin.groupe} de {fin.type}' if fin.nb_groupes > 1 else '')
        uniques = sorted(set(jours))
        for d in uniques:
            if jours.count(d) > 1:
                mj += jours.count(d) - 1
                cas.append(('meme_jour', e0.code, qui, JOURS[d]))
        for d, d2 in zip(uniques, uniques[1:]):
            if d2 - d == 1:
                ld += 1
                cas.append(('lendemain', e0.code, qui, f'{JOURS[d]} et {JOURS[d2]}'))
            elif d2 - d >= 4:
                lg += 1
    return mj, ld, lg, cas


def _paques(an):
    """Dimanche de Pâques (algorithme de Meeus, Jones et Butcher, calendrier grégorien)."""
    a, (b, c) = an % 19, divmod(an, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    mois, jour = divmod(h + ll - 7 * m + 114, 31)
    return date(an, mois, jour + 1)


def jours_feries(an):
    """Jours fériés nationaux de l'année civile `an` : {date: libellé}."""
    p = _paques(an)
    return {date(an, 1, 1): "Jour de l'an", p + timedelta(days=1): 'Lundi de Pâques',
            date(an, 5, 1): 'Fête du Travail', date(an, 5, 8): 'Victoire 1945',
            p + timedelta(days=39): 'Ascension', p + timedelta(days=50): 'Lundi de Pentecôte',
            date(an, 7, 14): 'Fête nationale', date(an, 8, 15): 'Assomption',
            date(an, 11, 1): 'Toussaint', date(an, 11, 11): 'Armistice', date(an, 12, 25): 'Noël'}


CLE_JOURS_FERMES = 'jours_fermes'   # app_settings de la base de l'année : liste JSON
TYPES_JOUR_FERME = {'ferie': 'Férié', 'pont': 'Pont'}


def lire_jours_fermes(db):
    """Jours fériés et ponts enregistrés pour l'année : [{date, type, libelle}], ou None
    tant que la liste n'a jamais été enregistrée (liste vide = aucun jour fermé)."""
    if not _table_existe(db, 'app_settings'):
        return None
    r = db.execute('SELECT value FROM app_settings WHERE key = ?', (CLE_JOURS_FERMES,)).fetchone()
    if not r:
        return None
    try:
        brut = json.loads(r[0])
    except (TypeError, ValueError):
        return None
    out = []
    for j in brut if isinstance(brut, list) else []:
        try:
            d = date.fromisoformat(str(j.get('date')))
        except (AttributeError, ValueError):
            continue
        out.append({'date': d.isoformat(), 'type': j.get('type') if j.get('type') in TYPES_JOUR_FERME else 'ferie',
                    'libelle': str(j.get('libelle') or '')})
    return out


def feries_legaux_periode(debut, fin):
    """Jours fériés légaux du `debut` au `fin` (dates), hors dimanches : [{date, type, libelle}]."""
    out = []
    for an in range(debut.year, fin.year + 1):
        for d, lib in sorted(jours_feries(an).items()):
            if debut <= d <= fin and d.weekday() != 6:
                out.append({'date': d.isoformat(), 'type': 'ferie', 'libelle': lib})
    return out


def dates_semaine(semaine, annee_univ, debut_annee):
    """Dates du lundi au samedi de la semaine ISO `semaine` de l'année « 2026-2027 », ou None."""
    m = re.match(r'^(\d{4})-(\d{4})$', annee_univ or '')
    if not m:
        return None
    an = int(m.group(1)) if semaine >= debut_annee else int(m.group(2))
    try:
        return [date.fromisocalendar(an, semaine, j + 1) for j in range(6)]
    except ValueError:
        return None


def calendrier_semaine(don, semaine):
    """Créneaux fermés de la semaine (samedi après-midi, jours fériés et ponts) et ces jours.

    Jours fermés : la liste de l'année (don.jours_fermes), ou à défaut les jours
    fériés légaux. Retour : (fermés {(jour, pas)}, jour fermé du lundi au vendredi ?,
    ["mercredi 11/11 (Armistice)", …], [jours fermés 0-5])."""
    reg = don.reg
    feries = {}
    dates = dates_semaine(semaine, don.annee_univ, don.debut_annee) if reg.feries else None
    for d, jd in enumerate(dates or []):
        lib = (jours_feries(jd.year) if don.jours_fermes is None else don.jours_fermes).get(jd)
        if lib and d in reg.jours:
            feries[d] = f'{JOURS[d]} {jd:%d/%m} ({lib})'
    ferme = set()
    for d in reg.jours:
        for u in range(reg.nb_pas):
            if d in feries or (d == 5 and reg.debut + (u + 1) * reg.pas > reg.samedi_fin):
                ferme.add((d, u))
    return ferme, any(d <= 4 for d in feries), list(feries.values()), sorted(feries)


def _blocages_unites(reg, cle_public, ferie_semaine=False):
    """Créneaux interdits aux étudiants de (année, face) : {(jour, pas)}.

    Règle du département : le jeudi après-midi est libre pour les FTP
    (reg.jeudi_ftp_libre), sauf la semaine d'un jour férié ou d'un pont, qui le rouvre.
    Autres blocages : blocages = [{"jour": 3, "debut": "13:30", "fin": "18:00",
    "annee": 1, "formation": "FTP", "sauf_ferie": true}, …] (annee, formation et
    sauf_ferie facultatifs : sans eux, le blocage vaut pour tous, toujours)."""
    an, face = cle_public
    out = set()
    regles = list(reg.blocages)
    if reg.jeudi_ftp_libre is not None:
        regles.append({'jour': 3, 'debut': _hhmm(reg.jeudi_ftp_libre), 'formation': 'FTP', 'sauf_ferie': True})
    for b in regles:
        if b.get('sauf_ferie') and ferie_semaine:
            continue
        if b.get('annee') not in (None, '') and int(b['annee']) != an:
            continue
        if (str(b.get('formation') or '').upper() or face) != face:
            continue
        j = int(b.get('jour', -1))
        t0, t1 = _minutes(b.get('debut', '00:00')), _minutes(b.get('fin', '23:59'))
        for u in range(reg.nb_pas):
            m = reg.debut + u * reg.pas
            if m < t1 and m + reg.pas > t0:
                out.add((j, u))
    return out


if pulp is not None:
    class _HiGHSDepart(pulp.HiGHS):
        """HiGHS avec solution de départ : PuLP 2.9 ne la transmet pas à l'API highspy.

        On ne donne que les binaires ; HiGHS recalcule le reste (« solving LP for
        user-supplied values of discrete variables »)."""

        def __init__(self, depart=None, **kw):
            super().__init__(**kw)
            self.depart = depart or {}

        def callSolver(self, lp):
            if self.depart:
                cols = [(v.index, float(self.depart[v.name])) for v in lp.variables() if v.name in self.depart]
                if cols:
                    idx, val = zip(*cols)
                    lp.solverModel.setSolution(len(idx), list(idx), list(val))
            lp.solverModel.run()


def _solveur(nom, temps, ecart, depart=None, x=None, ecart_abs=None):
    """Instance du solveur PuLP, avec solution de départ si fournie."""
    opts = {'msg': False, 'timeLimit': temps, 'gapRel': ecart}
    if ecart_abs is not None:
        opts['gapAbs'] = ecart_abs
    if nom == 'HiGHS':
        return _HiGHSDepart(depart=depart, **opts)
    if depart and x:
        for v in x.values():
            v.setInitialValue(depart.get(v.name, 0))
        return getattr(pulp, nom)(warmStart=True, **opts)
    return getattr(pulp, nom)(**opts)


def _statut(prob, statut):
    """Libellé du résultat (PuLP annonce « Optimal » même quand le temps limite coupe)."""
    sol = getattr(prob, 'sol_status', None)
    return {1: 'optimal', 2: 'meilleure solution trouvée dans le temps imparti', 0: 'aucune solution trouvée',
            -1: 'infaisable', -2: 'non borné'}.get(sol, pulp.LpStatus.get(statut, str(statut)))


def resoudre_semaine(semaine, evts, don, fixes, temps, nom_solveur, avert, calendrier=None):
    """Construit et résout le PLNE d'une semaine. Retourne (placements, non placés, infos).

    calendrier = calendrier_semaine(don, semaine) : créneaux fermés à tous (samedi
    après-midi, jours fériés et ponts) et présence d'un tel jour dans la semaine."""
    reg, P = don.reg, don.reg.poids
    U, J = reg.nb_pas, reg.jours
    ferme, ferie_semaine = (calendrier or calendrier_semaine(don, semaine))[:2]
    rang_jour = {d: i for i, d in enumerate(J)}
    M = len(J) * U + 1

    # Occupations déjà fixées (autres années) : enseignants et salles
    ens_occupe, salle_reduite = set(), defaultdict(int)
    for f in fixes:
        d, t0, t1 = int(f['day_of_week']), _minutes(f['start_time']), _minutes(f['end_time'])
        for u in range(U):
            m = reg.debut + u * reg.pas
            if m < t1 and m + reg.pas > t0:
                if f['teacher_id']:
                    ens_occupe.add((f['teacher_id'], d, u))
                cle = don.salle_de(f['room_name'])
                if cle:
                    salle_reduite[(cle, d, u)] += 1
                    if cle[0] == 'R' and cle[1] in don.id_pool_std:
                        salle_reduite[(('STD',), d, u)] += 1

    bloque = {}
    for e in evts:
        for an, face, _, _ in e.public:
            if (an, face) not in bloque:
                bloque[(an, face)] = _blocages_unites(reg, (an, face), ferie_semaine)

    # Débuts possibles de chaque séance (fermetures et indisponibilités exclues d'emblée)
    debuts = {}
    for e in evts:
        interdit = don.dispos[e.enseignant][0] if e.enseignant else set()
        bl = set().union(*(bloque[(an, f)] for an, f, _, _ in e.public))
        poss = []
        autorises = sorted(reg.debuts_pour(e.lon))
        for d in J:
            for u in autorises:
                couvre = [(d, v) for v in range(u, u + e.lon)]
                if any(c in interdit or c in bl or c in ferme for c in couvre):
                    continue
                if e.enseignant and any((e.enseignant, d, v) in ens_occupe for v in range(u, u + e.lon)):
                    continue
                poss.append((d, u))
        debuts[e.idx] = poss
        if not poss:
            avert.append(f'S{semaine} · {e.libelle} : aucun créneau compatible avec les dispos')

    # Structures indépendantes du modèle
    atomes = _atomes(evts)
    maximaux = [a for a in atomes if not any(a < b for b in atomes)]
    atomes_de = defaultdict(list)
    for k, a in enumerate(maximaux):
        for i in a:
            atomes_de[i].append(k)
    par_ens = defaultdict(list)
    for e in evts:
        if e.enseignant:
            par_ens[e.enseignant].append(e)
    par_atome = {k: [evts[i] for i in a] for k, a in enumerate(maximaux)}
    chaines = defaultdict(list)
    for e in evts:
        chaines[(e.session_id, e.groupe)].append(e)
    for es in chaines.values():
        es.sort(key=lambda e: e.rang)
    espacement = _espacement_matieres(evts, maximaux)
    coupure = (reg.dejeuner[0] + reg.dejeuner[1]) // 2 if reg.dejeuner else 13 * 60
    b = max(0, min(U, math.ceil((coupure - reg.debut) / reg.pas)))

    def se_croisent(e1, e2):
        return any(a1 == a2 and f1 == f2 and l1 < h2 and l2 < h1
                   for a1, f1, l1, h1 in e1.public for a2, f2, l2, h2 in e2.public)

    def construire(souple):
        """PLNE de la semaine : contraintes dures seules (souple=False) ou avec préférences."""
        prob = pulp.LpProblem(f'EDT_S{semaine}', pulp.LpMinimize)
        x = {(e.idx, d, u): pulp.LpVariable(f'x_{e.idx}_{d}_{u}', cat='Binary')
             for e in evts for d, u in debuts[e.idx]}
        vars_de = defaultdict(list)
        for (i, d, u), v in x.items():
            vars_de[i].append((d, u, v))
        place = {e.idx: pulp.lpSum(v for _, _, v in vars_de[e.idx]) for e in evts}
        cout = defaultdict(list)    # catégorie -> termes de l'objectif

        # ScheduleAllCourses : au plus une fois, non placé = forte pénalité
        for e in evts:
            if vars_de[e.idx]:
                prob += place[e.idx] <= 1, f'une_fois_{e.idx}'
                cout['placement'].append(-P['non_place'] * e.lon * place[e.idx])

        # Occupation par ressource : (ressource, jour, pas) -> variables
        occ = defaultdict(list)
        for e in evts:
            cles = [('A', k) for k in atomes_de[e.idx]]
            if e.enseignant:
                cles.append(('E', e.enseignant))
            if e.salle:
                cles.append(('S', e.salle))
                if e.salle[0] == 'R' and e.salle[1] in don.id_pool_std:
                    cles.append(('S', ('STD',)))
            for d, u, v in vars_de[e.idx]:
                for w in range(u, u + e.lon):
                    for c in cles:
                        occ[(c, d, w)].append(v)

        mobile = {}
        for (c, d, w), vs in occ.items():
            if c[0] in ('A', 'E'):
                # NoSimultaneousGroupCourses / NoSimultaneousAssigneeCourses
                if len(vs) > 1:
                    prob += pulp.lpSum(vs) <= 1
            elif c[1] == ('INFO',):
                cap = reg.capacite_info - salle_reduite[(c[1], d, w)]
                prob += pulp.lpSum(vs) <= max(cap, 0)
                if len(vs) > 1 and cap > 1:
                    # ConsiderRoomSorts : la salle mobile ne sert qu'en second, dans une salle banale
                    mobile[(d, w)] = m = pulp.LpVariable(f'mobile_{d}_{w}', lowBound=0)
                    prob += m >= pulp.lpSum(vs) - 1
                    if souple:
                        cout['salle_info_mobile'].append(P['salle_info_mobile'] * m)
        for (c, d, w), vs in occ.items():
            if c[0] != 'S' or c[1] == ('INFO',):
                continue
            cap = (don.nb_std if c[1] == ('STD',) else 1) - salle_reduite[(c[1], d, w)]
            extra = [mobile[(d, w)]] if c[1] == ('STD',) and (d, w) in mobile else []
            if len(vs) + len(extra) > cap:   # LimitSimultaneousRoomCourses
                prob += pulp.lpSum(vs + extra) <= max(cap, 0)
        for (d, w), m in mobile.items():
            if (('S', ('STD',)), d, w) not in occ and don.nb_std:
                prob += m <= max(don.nb_std - salle_reduite[(('STD',), d, w)], 0)

        # RespectTutorsMaxTimePerDay (heures de CM/TD, règle du département)
        for tid, es in par_ens.items():
            max_pas = int(float(don.enseignants[tid].get('max_hours_day') or 6) * 60 // reg.pas)
            cmtd = [e for e in es if e.type in ('CM', 'TD')]
            if sum(e.lon for e in cmtd) <= max_pas:
                continue
            for d in J:
                termes = [e.lon * v for e in cmtd for dd, _, v in vars_de[e.idx] if dd == d]
                if termes:
                    prob += pulp.lpSum(termes) <= max_pas, f'max_jour_{tid}_{d}'

        # Séances d'un même groupe interchangeables : on les ordonne (casse les symétries)
        def debut_expr(e):
            return pulp.LpAffineExpression([(v, rang_jour[d] * U + u) for d, u, v in vars_de[e.idx]])

        def fin_expr(e):
            return pulp.LpAffineExpression([(v, rang_jour[d] * U + u + e.lon) for d, u, v in vars_de[e.idx]])

        for es in chaines.values():
            for e1, e2 in zip(es, es[1:]):
                if vars_de[e1.idx] and vars_de[e2.idx]:
                    prob += place[e1.idx] >= place[e2.idx]
                    # les deux placées : e2 après e1 ; seule e1 placée : rien (forme serrée en LP)
                    prob += debut_expr(e2) >= fin_expr(e1) - M * (place[e1.idx] - place[e2.idx])

        if not souple:
            return prob, x, vars_de, cout

        # MinNonPreferredTutorsSlot
        for tid, es in par_ens.items():
            c_ens = don.dispos[tid][1]
            if not c_ens:
                continue
            for e in es:
                for d, u, v in vars_de[e.idx]:
                    k = sum(c_ens.get((d, w), 0.0) for w in range(u, u + e.lon))
                    if k:
                        cout['pref_enseignant'].append(P['pref_enseignant'] * k * v)

        # Soirées (après reg.soiree) et samedi : permis, mais pris en dernier
        if P['soir_samedi']:
            for e in evts:
                for d, u, v in vars_de[e.idx]:
                    n = e.lon if d == 5 else sum(1 for w in range(u, u + e.lon)
                                                 if reg.debut + w * reg.pas >= reg.soiree)
                    if n:
                        cout['soir_samedi'].append(P['soir_samedi'] * n * v)

        # Demi-journées de présence (MinTutorsHalfDays / MinGroupsHalfDays)
        def demis(e, u):
            return [h for h, ok in ((0, u < b), (1, u + e.lon > b)) if ok]

        def demi_journees(groupes, cat, prefixe):
            poids = P[cat]
            for cle, es in groupes.items():
                if len(es) < 2 or not poids:
                    continue
                hd = {}
                for e in es:
                    par_demi = defaultdict(list)
                    for d, u, v in vars_de[e.idx]:
                        for h in demis(e, u):
                            par_demi[(d, h)].append(v)
                    for dh, vs in par_demi.items():
                        if dh not in hd:
                            hd[dh] = pulp.LpVariable(f'{prefixe}_{cle}_{dh[0]}_{dh[1]}', lowBound=0, upBound=1)
                            cout[cat].append(poids * hd[dh])
                        prob.addConstraint(hd[dh] >= pulp.lpSum(vs))

        demi_journees(par_ens, 'demi_journee_enseignant', 'hdE')
        demi_journees(par_atome, 'demi_journee_groupe', 'hdG')

        # Pause déjeuner (TutorsLunchBreak / GroupsLunchBreak)
        if reg.dejeuner and P['dejeuner']:
            w0 = max(0, (reg.dejeuner[0] - reg.debut) // reg.pas)
            w1 = min(U, math.ceil((reg.dejeuner[1] - reg.debut) / reg.pas))
            libre = math.ceil(reg.dejeuner[2] / reg.pas)
            tolere = (w1 - w0) - libre
            if w1 > w0 and libre > 0:
                for prefixe, groupes in (('dejE', par_ens), ('dejG', par_atome)):
                    for cle, es in groupes.items():
                        if sum(e.lon for e in es) <= tolere:
                            continue
                        for d in J:
                            termes = []
                            for e in es:
                                for dd, u, v in vars_de[e.idx]:
                                    n = len(set(range(u, u + e.lon)) & set(range(w0, w1)))
                                    if dd == d and n:
                                        termes.append(n * v)
                            if termes:
                                s = pulp.LpVariable(f'{prefixe}_{cle}_{d}', lowBound=0)
                                prob += pulp.lpSum(termes) <= tolere + s
                                cout['dejeuner'].append(P['dejeuner'] * s)

        # Espacement d'une matière pour un même groupe d'étudiants (CM, TD, TP confondus) :
        # pas deux séances le même jour (s), si possible pas deux jours de suite (l),
        # ni 4 jours ou plus sans elle entre deux séances (lg) — idéal : 2 ou 3 jours.
        # z[d] = la matière a cours ce jour-là (exact : borné par le haut et par le bas).
        p_mj, p_ld, p_lg = P['matiere_meme_jour'], P['matiere_lendemain'], P['matiere_ecart_long']
        for n, ens in enumerate(espacement):
            es = [evts[i] for i in sorted(ens) if vars_de[i]]
            if len(es) < 2:
                continue
            z = {}
            for d in J:
                par_seance = [[v for dd, _, v in vars_de[e.idx] if dd == d] for e in es]
                par_seance = [vs for vs in par_seance if vs]
                if not par_seance:
                    continue
                termes = [v for vs in par_seance for v in vs]
                if p_mj and len(par_seance) > 1:
                    s = pulp.LpVariable(f'mj_{n}_{d}', lowBound=0)
                    prob += pulp.lpSum(termes) <= 1 + s
                    cout['matiere_meme_jour'].append(p_mj * s)
                if p_ld or p_lg:
                    z[d] = pulp.LpVariable(f'zm_{n}_{d}', lowBound=0, upBound=1)
                    for vs in par_seance:
                        prob += z[d] >= pulp.lpSum(vs)
                    prob += z[d] <= pulp.lpSum(termes)
            jours_z = sorted(z)
            for i, d in enumerate(jours_z):
                for d2 in jours_z[i + 1:]:
                    entre = [z[j] for j in jours_z if d < j < d2]
                    if d2 - d == 1 and p_ld:
                        lv = pulp.LpVariable(f'ld_{n}_{d}', lowBound=0)
                        prob += lv >= z[d] + z[d2] - 1
                        cout['matiere_lendemain'].append(p_ld * lv)
                    elif d2 - d >= 4 and p_lg:
                        gv = pulp.LpVariable(f'lg_{n}_{d}_{d2}', lowBound=0)
                        prob += gv >= z[d] + z[d2] - 1 - pulp.lpSum(entre)
                        cout['matiere_ecart_long'].append(p_lg * gv)

        def precede(avant, apres, cat, nom):
            """ConsiderDependencies (souple, au jour près) : `apres` ne tombe pas un jour avant `avant`.

            Forme indexée par jour (serrée en relaxation linéaire) : apres placée le
            jour d ⇒ avant placée un jour ≤ d, sauf violation payée une fois."""
            poids = P[cat]
            if not (vars_de[avant.idx] and vars_de[apres.idx]) or not poids:
                return
            viol = pulp.LpVariable(f'{nom}_{avant.idx}_{apres.idx}', lowBound=0, upBound=1)
            cumul = []
            for d in J:
                cumul += [v for dd, _, v in vars_de[avant.idx] if dd == d]
                z = [v for dd, _, v in vars_de[apres.idx] if dd == d]
                if z:
                    prob.addConstraint(pulp.lpSum(z) <= pulp.lpSum(cumul) + 1 - place[avant.idx] + viol)
            cout[cat].append(poids * viol)

        dernier = {k: es[-1] for k, es in chaines.items()}
        premier = {k: es[0] for k, es in chaines.items()}
        rang = {k: RANG_TYPE.get(premier[k].type[:2]) for k in chaines}
        par_matiere = defaultdict(list)
        for k in chaines:
            par_matiere[premier[k].course_id].append(k)
        for cles in par_matiere.values():
            for k2 in cles:
                if not rang[k2]:
                    continue          # CM (rang 0) ou PT/autre (None) : rien avant
                avant = [k1 for k1 in cles if rang[k1] is not None and rang[k1] < rang[k2]
                         and se_croisent(dernier[k1], premier[k2])]
                if avant:             # seulement le type immédiatement précédent (CM→TD, TD→TP)
                    r = max(rang[k1] for k1 in avant)
                    for k1 in avant:
                        if rang[k1] == r:
                            precede(dernier[k1], premier[k2], 'ordre_cm_td_tp', 'ordre')
        for pred, succ in don.enchainements:
            for k1 in chaines:
                if k1[0] != pred:
                    continue
                for k2 in chaines:
                    if k2[0] == succ and se_croisent(dernier[k1], premier[k2]):
                        precede(dernier[k1], premier[k2], 'enchainement', 'ench')
        return prob, x, vars_de, cout

    def cles_de(e):
        cles = [('A', k) for k in atomes_de[e.idx]]
        if e.enseignant:
            cles.append(('E', e.enseignant))
        if e.salle:
            cles.append(('S', e.salle))
            if e.salle[0] == 'R' and e.salle[1] in don.id_pool_std:
                cles.append(('S', ('STD',)))
        return cles

    def glouton():
        """Placement glouton qui respecte les mêmes contraintes dures que le PLNE.

        Sert de solution de départ : le solveur ne peut alors jamais faire moins
        bien. Chaînes les plus contraintes d'abord ; chaque séance va au créneau
        possible qui espace le mieux sa matière pour ses groupes (pas le même jour,
        puis pas la veille ni le lendemain), puis le moins chargé pour ses groupes
        et son enseignant ce jour-là."""
        occ, charge, cmtd = defaultdict(int), defaultdict(int), defaultdict(int)
        matj = defaultdict(int)    # (atome, matière, jour) -> séances déjà posées
        cap_std = lambda d, w: don.nb_std - salle_reduite[(('STD',), d, w)]   # noqa: E731
        choisi = {}
        ordre = sorted(chaines.values(), key=lambda es: (min(len(debuts[e.idx]) for e in es),
                                                         -sum(e.lon for e in es)))
        for es in ordre:
            fin_prec = 0
            for e in es:
                if fin_prec is None:
                    break                       # séance précédente non placée
                cles = cles_de(e)
                max_pas = (int(float(don.enseignants[e.enseignant].get('max_hours_day') or 6) * 60 // reg.pas)
                           if e.enseignant and e.type in ('CM', 'TD') else None)
                meilleur = None
                for d, u in debuts[e.idx]:
                    if rang_jour[d] * U + u < fin_prec:
                        continue
                    if max_pas is not None and cmtd[(e.enseignant, d)] + e.lon > max_pas:
                        continue
                    ok = True
                    for w in range(u, u + e.lon):
                        for c in cles:
                            n = occ[(c, d, w)] + 1
                            if c[0] in ('A', 'E'):
                                cap = 1
                            elif c[1] == ('INFO',):
                                cap = reg.capacite_info - salle_reduite[(c[1], d, w)]
                                if n > 1 and don.nb_std and occ[(('S', ('STD',)), d, w)] + n - 1 > cap_std(d, w):
                                    ok = False
                            elif c[1] == ('STD',):
                                cap = cap_std(d, w) - max(0, occ[(('S', ('INFO',)), d, w)] - 1)
                            else:
                                cap = 1 - salle_reduite[(c[1], d, w)]
                            if n > cap:
                                ok = False
                            if not ok:
                                break
                        if not ok:
                            break
                    if ok:
                        ats = atomes_de[e.idx]
                        meme = max((matj[(k, e.course_id, d)] for k in ats), default=0)
                        voisin = max((matj[(k, e.course_id, d - 1)] + matj[(k, e.course_id, d + 1)]
                                      for k in ats), default=0)
                        score = (meme, voisin, max(charge[(c, d)] for c in cles) if cles else 0, u)
                        if meilleur is None or score < meilleur[0]:
                            meilleur = (score, d, u)
                if meilleur is None:
                    fin_prec = None
                    continue
                _, d, u = meilleur
                choisi[e.idx] = (d, u)
                for w in range(u, u + e.lon):
                    for c in cles:
                        occ[(c, d, w)] += 1
                for c in cles:
                    charge[(c, d)] += e.lon
                for k in atomes_de[e.idx]:
                    matj[(k, e.course_id, d)] += 1
                if max_pas is not None:
                    cmtd[(e.enseignant, d)] += e.lon
                fin_prec = rang_jour[d] * U + u + e.lon
        return {f'x_{e.idx}_{d}_{u}': 1 if choisi.get(e.idx) == (d, u) else 0
                for e in evts for d, u in debuts[e.idx]}

    def niveau_de(prob_obj, sol):
        return sum(coef * sol.get(v.name, 0) for v, coef in prob_obj.items())

    # Voisinages de l'amélioration : les séances d'une année d'étude, puis d'une
    # promotion (année × FTP/ALT) ; un voisinage qui couvre presque toute la semaine
    # (calcul d'une seule année) est remplacé par ses promotions.
    voisinages = []
    for a in sorted({e.annee for e in evts}):
        voisinages.append(frozenset(e.idx for e in evts if e.annee == a))
    for a, f in sorted({(a, f) for e in evts for a, f, _, _ in e.public}):
        voisinages.append(frozenset(e.idx for e in evts if any(a2 == a and f2 == f for a2, f2, _, _ in e.public)))
    voisinages = [v for i, v in enumerate(voisinages)
                  if v and v not in voisinages[:i] and (len(v) <= 0.7 * len(evts) or len(evts) <= 40)]
    if not voisinages:
        voisinages = [frozenset(e.idx for e in evts)]

    def ameliorer(prob2, x2, depart, fin):
        """Optimise les préférences par voisinages (« fix-and-optimize »).

        Le modèle complet est trop gros pour que HiGHS améliore la solution de départ
        dans le temps imparti (constaté : la relaxation de la racine prend tout le
        temps, aucune heuristique ne tourne). On libère donc un voisinage à la fois —
        les séances d'une année ou d'une promotion —, tout le reste figé à la
        solution courante, et on garde le résultat s'il ne coûte pas plus. Le niveau
        de placement reste imposé (contrainte niveau_placement).
        Retourne (statut du dernier calcul retenu, nombre de calculs) ; statut None
        si rien n'a pu être évalué."""
        par_evt = defaultdict(list)
        for (i, _, _), v in x2.items():
            par_evt[i].append(v)
        courant, valeur, statut, n = dict(depart), None, None, 0

        def resoudre(libres, limite):
            for i, vs in par_evt.items():
                for v in vs:
                    if i in libres:
                        v.lowBound, v.upBound = 0, 1
                    else:
                        v.lowBound = v.upBound = courant.get(v.name, 0)
            st = prob2.solve(_solveur(nom_solveur, limite, reg.ecart, courant, x2))
            if any(v.varValue is None for v in x2.values()):
                return st, None, None
            return st, {v.name: round(v.varValue) for v in x2.values()}, pulp.value(prob2.objective) or 0.0

        # Évaluation du départ (tout figé : un simple calcul linéaire)
        st, sol, val = resoudre(frozenset(), max(2.0, fin - time.monotonic()))
        if sol is None:
            return None, 0
        courant, valeur, statut = sol, val, st
        sans_gain = 0
        k = 0
        while sans_gain < len(voisinages):
            reste = fin - time.monotonic()
            if reste < 1.5:
                break
            libres = voisinages[k % len(voisinages)]
            k += 1
            st, sol, val = resoudre(libres, min(reste - 0.3, max(3.0, reste / 3)))
            n += 1
            if sol is not None and val <= valeur + 1e-6:
                sans_gain = 0 if val < valeur - 1e-6 else sans_gain + 1
                courant, valeur, statut = sol, val, st
            else:
                sans_gain += 1
                # valeurs du solveur incohérentes avec la solution courante : on la rétablit
                st, sol, val = resoudre(frozenset(), 5.0)
                if sol is None:
                    break
        for vs in par_evt.values():
            for v in vs:
                v.lowBound, v.upBound = 0, 1
                v.varValue = courant.get(v.name, 0)
        return statut, n

    # Résolution en deux phases, chacune partant d'une solution connue.
    # Phase 1 : modèle allégé (contraintes dures seules), placer le plus d'heures
    #   possible, en partant du placement glouton.
    # Phase 2 : modèle complet, en partant de la phase 1 ; son niveau de placement
    #   devient une contrainte et l'objectif ne garde que les préférences (l'écart
    #   toléré porte alors sur elles seules).
    # Sans solution de départ, HiGHS peut passer tout son temps en coupes sans rien
    # trouver de bon (constaté sur S37 et S51 2026-2027).
    t0 = time.monotonic()
    depart = glouton()
    prob, x, vars_de, cout = construire(False)
    obj1 = pulp.lpSum(cout['placement'])
    prob.setObjective(obj1)
    statut = prob.solve(_solveur(nom_solveur, max(3.0, temps * 0.5), min(reg.ecart, 0.001)))
    sol1 = {v.name: round(v.varValue) for v in x.values() if v.varValue is not None}
    # À placement égal, le glouton reste le départ : lui tient compte de l'espacement
    # des matières et de la charge des journées, la phase 1 de rien d'autre que le placement
    if sol1 and niveau_de(obj1, sol1) < niveau_de(obj1, depart) - 1e-6:
        depart = sol1
    else:                                      # solveur pire que le glouton : on garde le glouton
        for v in x.values():
            v.varValue = depart.get(v.name, 0)
    tours = 0
    if temps - (time.monotonic() - t0) > 3:
        prob2, x2, vars_de2, cout2 = construire(True)
        obj2 = pulp.lpSum(cout2['placement'])
        prob2 += obj2 <= niveau_de(obj2, depart) + 1e-6, 'niveau_placement'
        prob2.setObjective(pulp.lpSum(t for cat, termes in cout2.items() if cat != 'placement' for t in termes))
        statut2, tours = ameliorer(prob2, x2, depart, t0 + temps)
        if statut2 is not None:
            prob, x, vars_de, cout, statut = prob2, x2, vars_de2, cout2, statut2
    duree = round(time.monotonic() - t0, 1)

    placements, non_places = [], []
    if not any(v.varValue is not None for v in x.values()) and x:
        return None, list(evts), {'statut': _statut(prob, statut), 'duree_s': duree,
                                  'variables': len(x), 'contraintes': len(prob.constraints)}
    for e in evts:
        choix = next(((d, u) for d, u, v in vars_de[e.idx] if (v.varValue or 0) > 0.5), None)
        if choix:
            placements.append((e, choix[0], choix[1]))
        else:
            non_places.append(e)
    penalites = {}
    for cat, termes in cout.items():
        if cat != 'placement':
            val = round(sum(pulp.value(t) or 0 for t in termes), 1)
            if val:
                penalites[cat] = val
    mj, ld, lg, cas = bilan_espacement(evts, espacement, {e.idx: d for e, d, _ in placements})
    infos = {'statut': _statut(prob, statut), 'duree_s': duree,
             'variables': len(x), 'contraintes': len(prob.constraints),
             'cout_preferences': round(sum(penalites.values()), 1), 'penalites': penalites,
             'voisinages_calcules': tours,
             'espacement': {'meme_jour': mj, 'lendemain': ld, 'ecart_long': lg,
                            'cas': [{'type': t, 'matiere': m, 'public': p, 'jours': j} for t, m, p, j in cas[:60]]}}
    return placements, non_places, infos


# ───────────────────────── salles concrètes ─────────────────────────

def attribuer_salles(don, placements, fixes, semaine, avert):
    """Salle précise de chaque séance placée : (e, jour, pas) -> room_id ou None."""
    reg = don.reg
    occupe = defaultdict(list)    # room_id -> [(jour, début, fin)] en pas depuis reg.debut
    for f in fixes:
        if f['room_id']:
            occupe[f['room_id']].append((int(f['day_of_week']),
                                         (_minutes(f['start_time']) - reg.debut) / reg.pas,
                                         (_minutes(f['end_time']) - reg.debut) / reg.pas))

    def libre(rid, d, u, lon):
        return all(not (dd == d and u < f and s < u + lon) for dd, s, f in occupe[rid])

    def prendre(rid, d, u, lon):
        occupe[rid].append((d, u, u + lon))

    salle = {}
    tri = sorted(placements, key=lambda p: (p[1], p[2], -p[0].lon))
    for e, d, u in tri:                                  # salles précises d'abord
        if e.salle and e.salle[0] == 'R':
            salle[e.idx] = e.salle[1]
            prendre(e.salle[1], d, u, e.lon)
    besoin_std = []
    for e, d, u in tri:
        if not e.salle or e.salle[0] in ('R', 'X'):
            continue
        if e.salle == ('INFO',):
            fixe = don.salle_info['id'] if don.salle_info else None
            if fixe and libre(fixe, d, u, e.lon):
                salle[e.idx] = fixe
                prendre(fixe, d, u, e.lon)
                continue
            avert.append(f'S{semaine} · {e.libelle} ({JOURS[d]} {_hhmm(reg.debut + u * reg.pas)}) '
                         f': salle info mobile, dans une salle banale')
        besoin_std.append((e, d, u))
    dernier_lieu = {}                                    # LimitMoves : garder la même salle
    for e, d, u in besoin_std:
        pref = [dernier_lieu.get(('E', e.enseignant, d)), dernier_lieu.get(('P', e.public, d))]
        candidates = [r for r in pref if r] + [s['id'] for s in don.pool_std]
        rid = next((r for r in candidates if libre(r, d, u, e.lon)), None)
        if rid is None:
            avert.append(f'S{semaine} · {e.libelle} : plus de salle banale libre, salle à choisir')
        else:
            prendre(rid, d, u, e.lon)
            dernier_lieu[('E', e.enseignant, d)] = dernier_lieu[('P', e.public, d)] = rid
        salle[e.idx] = rid
    return salle


# ───────────────────────── orchestration ─────────────────────────

def _charges(semaine, evts, reg):
    """Heures prévues par partie d'effectif (contrôle ALT ≤ 40 h, FTP 25–30 h)."""
    out = []
    atomes = _atomes(evts)
    pire = {}
    for membres, (an, face, _, _) in atomes.items():
        h = sum(evts[i].lon for i in membres) * reg.pas / 60
        pire[(an, face)] = max(pire.get((an, face), 0), h)
    for (an, face), h in sorted(pire.items()):
        if face == 'ALT' and h > 40:
            alerte = 'plus de 40 h'
        elif face == 'FTP' and not 25 <= h <= 30:
            alerte = 'hors cible 25–30 h'
        else:
            alerte = None
        out.append({'semaine': semaine, 'annee': an, 'formation': face, 'heures': h, 'alerte': alerte})
    return out


def _ordre_semaines(semaines, debut_annee):
    return sorted(set(semaines), key=lambda w: (w < debut_annee, w))


def _ecrire(db, semaines_ok, resultats, reg):
    cols = [r[1] for r in db.execute('PRAGMA table_info(timetable_slots)').fetchall()]
    if 'group_index' not in cols:       # migration additive, faite à la première écriture
        db.execute('ALTER TABLE timetable_slots ADD COLUMN group_index INTEGER')
    filtre, args = _filtre_annees(reg)
    for w in semaines_ok:
        if reg.annees:
            db.execute(f'''DELETE FROM timetable_slots WHERE week_number = ? AND course_session_id IN (
                               SELECT cs.id FROM course_sessions cs JOIN courses c ON c.id = cs.course_id
                               JOIN semesters s ON s.id = c.semester_id WHERE 1=1{filtre})''', (w, *args))
        else:
            db.execute('DELETE FROM timetable_slots WHERE week_number = ?', (w,))
    n = 0
    for c in resultats:
        db.execute('''INSERT INTO timetable_slots
                          (course_session_id, week_number, day_of_week, start_time, end_time,
                           room_id, teacher_id, formation_type, group_index)
                      VALUES (?,?,?,?,?,?,?,?,?)''',
                   (c['course_session_id'], c['week_number'], c['day_of_week'], c['start_time'],
                    c['end_time'], c['room_id'], c['teacher_id'], c['formation_type'], c['group_index']))
        n += 1
    return n


def generer(db, data):
    """Point d'entrée : résout les semaines demandées et écrit timetable_slots."""
    reg = lire_reglages(data)
    nom_solveur = reg.solveur or solveur_disponible()
    if not nom_solveur:
        raise RuntimeError('Aucun solveur PuLP disponible : pip install "pulp>=2.9,<3" (highspy en option)')
    t_debut = time.monotonic()
    avert = []
    don = Donnees(db, reg)
    semaines = reg.semaines or [r[0] for r in db.execute(
        'SELECT DISTINCT week_number FROM weekly_hours WHERE hours > 0')]
    semaines = _ordre_semaines(semaines, don.debut_annee)

    sans_dispo = sorted({don.enseignants[t]['name'] for t, (_, _, saisi) in don.dispos.items() if not saisi})
    if sans_dispo:
        avert.append(f'{len(sans_dispo)} enseignant(s) sans dispos saisies, supposés toujours disponibles : '
                     + ', '.join(sans_dispo[:12]) + (' …' if len(sans_dispo) > 12 else ''))
    if reg.feries and don.jours_fermes is None:
        avert.append(f'Jours fériés et ponts {don.annee_univ or "de l’année"} pas encore enregistrés : jours fériés '
                     'légaux pris, sans pont (Répartition journalière › Jours fériés et ponts)')

    rapport, conflits, charges, creneaux, ok, restantes = [], [], [], [], [], []
    noms_cours = {r[0]: r[1] for r in db.execute('SELECT id, name FROM courses')}
    for w in semaines:
        restant = reg.temps_total - (time.monotonic() - t_debut)
        if restant < 8:
            restantes.append(w)
            continue
        evts = evenements_semaine(db, don, w, avert)
        if not evts:
            ok.append(w)
            rapport.append({'semaine': w, 'statut': 'vide', 'seances': 0})
            continue
        charges.extend(_charges(w, evts, reg))
        fixes = occupations_fixes(db, don, w)
        cal = calendrier_semaine(don, w)
        ferme, ferie_semaine, feries, jours_fermes = cal
        if feries:
            rouvert = ferie_semaine and reg.jeudi_ftp_libre is not None and 3 not in jours_fermes
            avert.append(f'S{w} · {"jour fermé" if len(feries) == 1 else "jours fermés"} : {", ".join(feries)} — '
                         f'aucun cours {"ce jour-là" if len(feries) == 1 else "ces jours-là"}'
                         + (', jeudi après-midi ouvert aux FTP' if rouvert else ''))
        # Contrôle préalable (pré-analyse de flop!) : assez de dispos pour ses heures ?
        ouverts = {(d, u) for d in reg.jours for u in range(reg.nb_pas)} - ferme
        for tid in {e.enseignant for e in evts if e.enseignant}:
            besoin = sum(e.lon for e in evts if e.enseignant == tid)
            offre = len(ouverts - don.dispos[tid][0])
            if offre < besoin:
                avert.append(f'S{w} · {don.enseignants[tid]["name"]} : {besoin * reg.pas / 60:g} h à placer '
                             f'pour {offre * reg.pas / 60:g} h de dispos')
        placements, non_places, infos = resoudre_semaine(
            w, evts, don, fixes, max(5.0, min(reg.temps_max, restant - 5)), nom_solveur, avert, cal)
        infos.update({'semaine': w, 'seances': len(evts)})
        if feries:
            infos['feries'] = feries
            infos['jours_fermes'] = jours_fermes
        if placements is None:
            infos['statut_edt'] = 'sans solution dans le temps imparti'
            rapport.append(infos)
            continue
        salles = attribuer_salles(don, placements, fixes, w, avert)
        ok.append(w)
        nom_salle = {s['id']: s['name'] for s in don.salles}
        nom_ens = lambda t: don.enseignants[t]['name'] if t in don.enseignants else None   # noqa: E731
        for e, d, u in placements:
            debut = reg.debut + u * reg.pas
            rid = salles.get(e.idx)
            creneaux.append({
                'course_session_id': e.session_id, 'week_number': w, 'day_of_week': d,
                'start_time': _hhmm(debut), 'end_time': _hhmm(debut + e.lon * reg.pas),
                'room_id': rid, 'teacher_id': e.enseignant, 'formation_type': e.formation,
                # groupe noté seulement quand la séance en a plusieurs (sinon NULL)
                'group_index': e.groupe if e.nb_groupes > 1 else None,
                # mêmes champs que GET /api/timetable/week (affichage de l'aperçu)
                'libelle': e.libelle, 'course_code': e.code, 'teaching_type': e.type,
                'form_type': e.formation, 'year_group': e.annee, 'semester_code': e.semestre,
                'teacher_name': nom_ens(e.enseignant), 'room_name': nom_salle.get(rid),
                'course_name': noms_cours.get(e.course_id),
                # promotions concernées (vue Planning) : [[année, 'FTP'|'ALT'], …]
                'publics': sorted({(a, f) for a, f, _, _ in e.public})})
        for e in non_places:
            conflits.append({'week': w, 'session_id': e.session_id, 'course': e.code, 'type': e.type,
                             'group': e.groupe if e.nb_groupes > 1 else None, 'teacher_id': e.enseignant,
                             'teacher_name': nom_ens(e.enseignant), 'year_group': e.annee,
                             'form_type': e.formation, 'hours': e.lon * reg.pas / 60,
                             'reason': 'Aucun créneau compatible (enseignant, groupe ou salle)'})
        infos.update({'places': len(placements), 'non_places': len(non_places)})
        rapport.append(infos)

    ecrits = 0
    if not reg.simulation and ok:
        ecrits = _ecrire(db, ok, creneaux, reg)
        db.commit()
    res = {
        'moteur': 'pulp', 'solveur': nom_solveur, 'simulation': reg.simulation,
        'generated_slots': ecrits if not reg.simulation else len(creneaux),
        'weeks_processed': len(ok), 'conflicts': conflits[:200], 'nb_conflits': len(conflits),
        'semaines': rapport, 'semaines_restantes': restantes,
        'charges': [c for c in charges if c['alerte']], 'avertissements': avert[:300],
        'duree_s': round(time.monotonic() - t_debut, 1),
    }
    if reg.simulation:
        res['creneaux'] = creneaux
    return res


if __name__ == '__main__':   # essai en ligne de commande, sur une copie de base
    import argparse
    import sqlite3

    ap = argparse.ArgumentParser(description="Solveur d'EDT GestionEDT (PuLP)")
    ap.add_argument('base')
    ap.add_argument('--semaines', type=int, nargs='*', default=[])
    ap.add_argument('--annees', type=int, nargs='*')
    ap.add_argument('--temps', type=float, default=20)
    ap.add_argument('--total', type=float, default=1e9)
    ap.add_argument('--solveur')
    ap.add_argument('--ecrire', action='store_true', help='écrit timetable_slots (sinon simulation)')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    con = sqlite3.connect(a.base)
    con.row_factory = sqlite3.Row
    r = generer(con, {'semaines': a.semaines, 'annees': a.annees, 'temps_max': a.temps,
                      'temps_total': a.total, 'simulation': not a.ecrire, 'solveur': a.solveur})
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1, default=str))
    else:
        for s in r['semaines']:
            print(s)
        print('conflits :', r['nb_conflits'])
        for c in r['conflicts'][:20]:
            print('  ', c)
        print('charges hors cible :', len(r['charges']))
        for m in r['avertissements'][:30]:
            print('  !', m)
        print('durée totale', r['duree_s'], 's ; solveur', r['solveur'])
