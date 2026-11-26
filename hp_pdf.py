"""Indisponibilités des enseignants lues dans les PDF d'Hyperplanning.

Format attendu : l'emploi du temps d'un enseignant imprimé « une semaine par page »
(titre « M. NOM - du 04 au 09 janvier 2027 »), chaque jour dans sa bande, du lundi
au samedi, avec son bandeau daté (« lundi 4 janvier 2027 ») et toute la journée
(8 h 00 → 21 h 00) sur un axe régulier. Les indisponibilités y sont hachurées.
Sont lus aussi : plusieurs semaines côte à côte, jours datés ; et les semaines en
colonnes (« 24 août - 29 août »), jours en rangées sans date, dix semaines par page
(cf. `_cases_semaines`). Des horaires compactés (heures sans cours réduites) ne
conviennent pas : ils coupent les hachures.

Rien n'y est balisé ; on lit le dessin de la page (PDF produit par wPDF4) :
  * les hachures sont des milliers de petits tirets « - », posés en rangées
    régulières (ligne par ligne, 30 par rangée sur la largeur du jour) ;
  * l'axe horaire part du bas du bandeau du jour (heure de sa première étiquette,
    8h00) ; son échelle se lit sur le trait rose de midi (12h00) ;
  * les cases de cours sont des rectangles pleins (utilisés seulement pour les
    contrôles, cf. `cours`).
Coordonnées en unités internes de la page (avant la mise à l'échelle globale) :
x vers la droite, y négatif vers le bas.

Validé sur l'impression d'Hyperplanning 2025 de l'Université de Toulon : 123 cases
de cours sur 123 retombent à la minute près sur les horaires de l'export iCal.
"""
import io
import re
import unicodedata
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import date, timedelta

MOIS = {'janvier': 1, 'février': 2, 'fevrier': 2, 'mars': 3, 'avril': 4, 'mai': 5, 'juin': 6,
        'juillet': 7, 'août': 8, 'aout': 8, 'septembre': 9, 'octobre': 10, 'novembre': 11,
        'décembre': 12, 'decembre': 12}
JOURS = ('lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche')
_TITRE_JOUR = re.compile(r'^(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche) (\d{1,2}) (\S+) (\d{4})$')
# Semaines en colonnes, jours non datés : en-tête « 24 août - 29 août », « 28 déc. - 02 janv. »
_TITRE_SEMAINE = re.compile(r'^(\d{1,2}) ([^\s\d]+) - (\d{1,2}) ([^\s\d]+)$')
# Période du titre de la page : « du 24 août au 31 octobre 2026 », « du 02 novembre 2026 au 09 janvier 2027 »
_PERIODE = re.compile(r'\bdu (\d{1,2}) ([^\s\d]+)(?: (\d{4}))? au (\d{1,2}) ([^\s\d]+) (\d{4})\b')
_HEURE = re.compile(r'^(\d{1,2})h(\d{2})$')
_CIVILITE = re.compile(r'^(?:M\.|MM\.|Mme|Mmes|Mlle|Melle|Dr\.?|Pr\.?)\s+', re.I)
MIDI = 12 * 60
FIN_JOUR = 21 * 60

# ---------------------------------------------------------------------------
# Lecture du dessin d'une page
# ---------------------------------------------------------------------------
_NUM = rb'[-+]?(?:\d+\.?\d*|\.\d+)'
_CHAINE = rb'\((?:\\.|[^\\)])*\)'
_MONTRE = rb'(?:' + _CHAINE + rb'\s*Tj|\[(?:' + _CHAINE + rb'|[^\]()])*\]\s*TJ)'
# wPDF4 pose chaque caractère (et chaque tiret de hachure) par un déplacement suivi
# de son affichage : « 48 0 Td[(-)-4]TJ », « 37 0 Td(h)Tj ». Une suite de ces poses
# est lue d'un bloc : c'est l'essentiel du contenu, et la lire jeton par jeton est lent.
_POSES = rb'(?:' + _NUM + rb'\s+' + _NUM + rb'\s+Td\s*' + _MONTRE + rb'\s*)+'
_TOK = re.compile(
    rb'(?P<poses>' + _POSES + rb')'
    rb'|(?P<chaine>' + _CHAINE + rb')'
    rb'|(?P<tableau>\[(?:' + _CHAINE + rb'|[^\]()])*\])'
    rb'|(?P<nom>/[^\s/\[\]()<>]+)'
    rb'|(?P<num>' + _NUM + rb')'
    rb'|(?P<op>[A-Za-z\'"*]+)', re.S)
_POSE = re.compile(rb'(' + _NUM + rb')\s+(' + _NUM + rb')\s+Td\s*(' + _MONTRE + rb')', re.S)
_CHAINES = re.compile(_CHAINE, re.S)
# Bloc de hachures pur : chaque rangée (un déplacement quelconque, puis des
# déplacements horizontaux) est lue d'un coup
_TIRET = rb'(?:\(-\)\s*Tj|\[\s*\(-\)[^\]()]*\]\s*TJ)'
_ZERO = rb'[-+]?0(?:\.0*)?'
_RANGEE = re.compile(rb'(' + _NUM + rb')\s+(' + _NUM + rb')\s+Td\s*' + _TIRET + rb'\s*((?:' + _NUM + rb'\s+'
                     + _ZERO + rb'\s+Td\s*' + _TIRET + rb'\s*)*)')
_TX_HORIZ = re.compile(rb'(' + _NUM + rb')\s+' + _ZERO + rb'\s+Td')


def _texte(b):
    """Chaîne PDF littérale « (...) » -> texte (WinAnsi), échappements compris."""
    out, i, n = bytearray(), 1, len(b) - 1
    while i < n:
        c = b[i]
        if c == 0x5C and i + 1 < n:
            s = b[i + 1]
            if 0x30 <= s <= 0x37:
                j = i + 1
                while j < min(i + 4, n) and 0x30 <= b[j] <= 0x37:
                    j += 1
                out.append(int(b[i + 1:j], 8) & 0xFF)
                i = j
                continue
            out.append({0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12}.get(s, s))
            i += 2
            continue
        out.append(c)
        i += 1
    return out.decode('cp1252', 'replace')


def _montre(b):
    """Opérande d'affichage « (…)Tj » ou « […]TJ » -> texte."""
    if b[:1] == b'[':
        return ''.join(_texte(c) for c in _CHAINES.findall(b))
    corps = b[1:b.rindex(b')')]
    return corps.decode('cp1252', 'replace') if b'\\' not in corps else _texte(b[:b.rindex(b')') + 1])


def lire_page(data):
    """Contenu d'une page -> (textes, tirets, rects, traits).

    textes : [{x, y, s, t (taille)}] (tirets de petite taille exclus) ;
    tirets : {(y, taille): [(nombre, x_min, x_max), …]} — les « - » de petite taille,
             par segments de rangée (tirets voisins d'un même bloc à la même hauteur) ;
    rects  : [{x0, x1, y0, y1, c (couleur de remplissage)}] ;
    traits : [{p, q, c (couleur), w (épaisseur)}] ;
    filigranes : {(x, y): texte} — textes posés en biais (le « Férié » d'un jour
             fermé, en travers de sa case), par point d'origine."""
    textes, rects, traits = [], [], []
    tirets = defaultdict(list)
    filigranes = defaultdict(str)
    pile = []
    taille = 0.0
    police = ''                   # ressource de police (/F1 = Arial gras : nom de la matière)
    lx = ly = 0.0
    biais = None                  # origine d'un texte posé en biais (Tm tourné), sinon None
    remp, coul, larg = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 1.0
    chemin, pt = [], None

    for m in _TOK.finditer(data):
        kind = m.lastgroup
        if kind == 'poses':
            pile = []
            bloc = m.group()
            if biais is not None:
                for _, _, montre in _POSE.findall(bloc):
                    filigranes[biais] += _montre(montre)
                continue
            petit = taille < 30
            if petit and bloc.count(b'(-)') == bloc.count(b'Td'):
                # rien que des tirets : une zone hachurée, rangée par rangée
                for tx0, ty0, suite in _RANGEE.findall(bloc):
                    lx += float(tx0)
                    ly += float(ty0)
                    x_premier = lx
                    pas = list(map(float, _TX_HORIZ.findall(suite))) if suite else ()
                    if pas:
                        lx += sum(pas)
                    tirets[(round(ly, 1), taille)].append(
                        (1 + len(pas), min(x_premier, lx), max(x_premier, lx)))
                continue
            seg = None                # [y, nombre, x_min, x_max] : rangée de tirets en cours
            for tx, ty, montre in _POSE.findall(bloc):
                lx += float(tx)
                if ty != b'0':
                    ly += float(ty)
                if petit and (montre == b'(-)Tj' or montre.startswith(b'[(-)')):
                    if seg is not None and seg[0] == ly:
                        seg[1] += 1
                        if lx < seg[2]:
                            seg[2] = lx
                        elif lx > seg[3]:
                            seg[3] = lx
                    else:
                        if seg is not None:
                            tirets[(round(seg[0], 1), taille)].append((seg[1], seg[2], seg[3]))
                        seg = [ly, 1, lx, lx]
                    continue
                s = _montre(montre)
                if s:
                    textes.append({'x': lx, 'y': ly, 's': s, 't': taille, 'f': police})
            if seg is not None:
                tirets[(round(seg[0], 1), taille)].append((seg[1], seg[2], seg[3]))
            continue
        if kind != 'op':
            pile.append(m.group())
            continue
        op = m.group()
        a, pile = pile, []
        try:
            if op == b'Td' or op == b'TD':
                lx += float(a[-2]); ly += float(a[-1])
            elif op == b'Tm':
                lx, ly = float(a[-2]), float(a[-1])
                droit = [float(v) for v in a[-6:-2]] == [1.0, 0.0, 0.0, 1.0]
                biais = None if droit else (round(lx, 1), round(ly, 1))
            elif op == b'ET':
                biais = None
            elif op == b'Tf':
                taille = float(a[-1])
                police = a[-2].decode('latin-1') if isinstance(a[-2], bytes) else str(a[-2])
            elif op in (b'Tj', b'TJ', b"'", b'"'):
                brut = a[-1]
                s = ''.join(_texte(c) for c in _CHAINES.findall(brut)) if brut[:1] == b'[' else _texte(brut)
                if biais is not None:
                    filigranes[biais] += s
                elif s == '-' and taille < 30:
                    tirets[(round(ly, 1), taille)].append((1, lx, lx))
                elif s:
                    textes.append({'x': lx, 'y': ly, 's': s, 't': taille, 'f': police})
            elif op == b'rg':
                remp = tuple(float(v) for v in a[-3:])
            elif op == b'g':
                v = float(a[-1]); remp = (v, v, v)
            elif op == b'RG':
                coul = tuple(float(v) for v in a[-3:])
            elif op == b'G':
                v = float(a[-1]); coul = (v, v, v)
            elif op == b'w':
                larg = float(a[-1])
            elif op == b're':
                chemin.append(tuple(float(v) for v in a[-4:]))
            elif op == b'm':
                pt = (float(a[-2]), float(a[-1]))
            elif op == b'l':
                q = (float(a[-2]), float(a[-1]))
                chemin.append((pt, q))
                pt = q
            elif op in (b'f', b'F', b'f*', b'B', b'B*', b'b', b'b*'):
                for c in chemin:
                    if len(c) == 4:
                        x, y, w, h = c
                        rects.append({'x0': min(x, x + w), 'x1': max(x, x + w),
                                      'y0': min(y, y + h), 'y1': max(y, y + h), 'c': remp})
                chemin = []
            elif op in (b'S', b's'):
                for c in chemin:
                    if len(c) == 2 and c[0] is not None:
                        traits.append({'p': c[0], 'q': c[1], 'c': coul, 'w': larg})
                chemin = []
            elif op == b'n':
                chemin = []
        except (IndexError, ValueError):
            pass
    return textes, dict(tirets), rects, traits, dict(filigranes)


def _mots(textes):
    """Caractères posés un à un -> mots (même ligne, se suivant de près)."""
    out = []
    for t in textes:
        if out and abs(out[-1]['y'] - t['y']) < 1 and out[-1]['t'] == t['t'] \
                and 0 <= t['x'] - out[-1]['xe'] < max(t['t'], 1) * 1.3:
            out[-1]['s'] += t['s']
            out[-1]['xe'] = t['x']
        else:
            out.append(dict(t, xe=t['x']))
    vus, res = set(), []
    for w in out:                       # wPDF4 écrit certains textes deux fois
        k = (round(w['x']), round(w['y']), w['s'])
        if k not in vus:
            vus.add(k)
            res.append(w)
    return res


def _blanc(c):
    return all(v > 0.99 for v in c)


def _rose(c):
    return c[0] > 0.9 and c[1] < 0.1 and c[2] > 0.9


def _noir(c):
    return all(v < 0.05 for v in c)


def _arrondi(m, pas=15):
    return int(round(m / pas) * pas)


_FRACTION = re.compile(r'^\s*\d+\s*/\s*\d+\s*$')
_CLASSE_GROUPE = re.compile(r'<([^>]+)>\s*([^,<]*)')
_CLASSE_SEULE = re.compile(r'(?:^|,)\s*((?:BUT|LP|DU|DUT|ING|L\d|M\d)\b[^,<]*)')


def lire_case_cours(textes, gras=('/F1',)):
    """Texte d'une case de cours -> {matiere, classes, groupes, salles, gim, lisible,
    texte}. Hyperplanning y écrit « Matière,<Classe> Groupe,Salle » — ou,
    dans une petite case, la matière en gras après le reste — plus le compteur
    « 7/10 » de la séance. La matière est le texte en gras (hors compteur)."""
    lignes = defaultdict(list)
    for t in textes:
        lignes[round(t['y'] / 4)].append(t)
    gras_txt, reste = [], []
    for k in sorted(lignes, reverse=True):
        ts = sorted(lignes[k], key=lambda t: t['x'])
        ligne = ''.join(t['s'] for t in ts)
        if _FRACTION.match(ligne):
            continue
        g = ''.join(t['s'] for t in ts if t.get('f') in gras)
        r = ''.join(t['s'] for t in ts if t.get('f') not in gras)
        if g.strip() and not _FRACTION.match(g):
            gras_txt.append(g.strip())
        if r.strip():
            reste.append(r.strip())
    texte = ' '.join(reste)
    matiere = ' '.join(gras_txt).strip(' ,')
    if not matiere:                             # pas de gras : le premier morceau
        matiere = texte.split(',')[0].strip() if not texte.startswith(',') and not texte.startswith('<') else ''
    paires = [(c.strip(), g.strip()) for c, g in _CLASSE_GROUPE.findall(texte)]
    classes = [c for c, _ in paires] + [c.strip() for c in _CLASSE_SEULE.findall(re.sub(r'<[^>]*>', '', texte))]
    groupes = [g for _, g in paires if g]
    salles = []
    for seg in re.sub(r'<[^>]*>[^,<]*', '', texte).split(','):
        seg = seg.strip()
        if seg and seg != matiere and not _CLASSE_SEULE.match(',' + seg) and re.match(r'^[A-Z]?\d{2,4}\b', seg):
            salles.append(seg)
    # case trop petite pour son texte : « ... » seulement (semaines en colonnes)
    lisible = bool(re.search(r'[^\W_]', matiere + texte))
    return {'matiere': matiere if lisible else '', 'classes': classes, 'groupes': groupes, 'salles': salles,
            'gim': any('GIM' in c.upper() for c in classes), 'lisible': lisible,
            'texte': (matiere + ' · ' + texte).strip(' ·')}


def _mois(tok):
    """« août », « sept. », « janv. », « déc. » -> numéro du mois (None : inconnu ou ambigu)."""
    t = (tok or '').strip('.').lower()
    if t in MOIS:
        return MOIS[t]
    ms = {m for nom, m in MOIS.items() if len(t) >= 3 and nom.startswith(t)}
    return ms.pop() if len(ms) == 1 else None


def _cases_semaines(mots, filigranes, traits):
    """Planning sur plusieurs semaines, semaines en colonnes et jours en rangées, sans
    date dans les cases : chaque colonne a pour en-tête sa semaine (« 24 août - 29 août »),
    chaque rangée son jour écrit en biais à gauche (« lundi »), et l'année se déduit de
    la période du titre (« M. NOM - du 24 août au 31 octobre 2026 »). La rangée est
    comprise entre deux traits épais ; son axe horaire commence au trait du haut.
    -> cases [{date, haut, x0, x1, titre_haut}] comme pour les jours datés."""
    titre = next((w['s'] for w in mots if ' - du ' in w['s']), '')
    m = _PERIODE.search(titre)
    if not m:
        return []
    try:
        fin = date(int(m.group(6)), _mois(m.group(5)), int(m.group(4)))
        m1 = _mois(m.group(2))
        a1 = int(m.group(3)) if m.group(3) else (fin.year if m1 <= fin.month else fin.year - 1)
        debut = date(a1, m1, int(m.group(1)))
    except (TypeError, ValueError):
        return []
    verticaux = [(l['p'][0], min(l['p'][1], l['q'][1]), max(l['p'][1], l['q'][1]))
                 for l in traits if abs(l['p'][0] - l['q'][0]) < 0.5]
    semaines = []
    for w in mots:
        s = _TITRE_SEMAINE.match(w['s'].strip())
        mo = _mois(s.group(2)) if s else None
        if not mo:
            continue
        lundi = None
        for an in sorted({debut.year, fin.year}):
            try:
                d = date(an, mo, int(s.group(1)))
            except ValueError:
                continue
            if debut - timedelta(days=6) <= d <= fin:
                lundi = d - timedelta(days=d.weekday())
                break
        # colonne : entre les traits verticaux qui encadrent l'en-tête
        xs = [x for x, ya, yb in verticaux if ya - 1 <= w['y'] <= yb + 1]
        x0 = max((x for x in xs if x <= w['x'] + 0.5), default=None)
        x1 = min((x for x in xs if x >= w['xe'] + 1), default=None)
        if lundi is not None and x0 is not None and x1 is not None:
            semaines.append((lundi, x0, x1, w['y']))
    if not semaines:
        return []
    grille_x0 = min(s[1] for s in semaines)
    bas_entetes = min(s[3] for s in semaines)
    epais = sorted({round(l['p'][1], 1) for l in traits if l['w'] >= 1.5 and _noir(l['c'])
                    and abs(l['p'][1] - l['q'][1]) < 1 and max(l['p'][0], l['q'][0]) > grille_x0})
    cases = []
    for (fx, fy), t in filigranes.items():
        nom = t.strip().lower()
        if nom not in JOURS or fx >= grille_x0:
            continue
        haut = min((y for y in epais if y > fy), default=None)
        if haut is None or haut >= bas_entetes:
            continue
        for lundi, x0, x1, _ in semaines:
            cases.append({'date': lundi + timedelta(days=JOURS.index(nom)), 'haut': haut,
                          'x0': x0, 'x1': x1, 'titre_haut': haut})
    return cases


def analyser_page(data, avec_cours=False, gras=('/F1',)):
    """Une page -> {'qui', 'jours': [{'date', 'zones': [(début, fin)], 'cours': [(début, fin)]}]},
    heures en minutes ; None si la page n'a pas de jours datés (format non reconnu).
    `cours` (cases de cours, pour les contrôles) n'est lu qu'avec avec_cours.

    Chaque jour est une case avec son bandeau daté (« lundi 4 janvier 2027 ») : une
    seule colonne (une semaine par page) ou plusieurs (une semaine par colonne). Les
    cases d'une même rangée (même jour de la semaine) partagent l'axe horaire, à
    gauche de la page, et le trait rose de midi. Sans bandeau daté, les semaines en
    colonnes (« 24 août - 29 août ») et les jours en rangées (cf. `_cases_semaines`).
    `cours_lus` : la page donne aussi les cours posés (`cours_hp` de chaque jour)."""
    textes, tirets, rects, traits, filigranes = lire_page(data)
    mots = _mots(textes)
    qui = next((re.sub(r'\s+-\s+du\s.*$', '', w['s']).strip() for w in mots if ' - du ' in w['s']), None)
    blancs = [r for r in rects if _blanc(r['c']) and r['x1'] - r['x0'] > 200]
    cases = []
    for w in mots:
        m = _TITRE_JOUR.match(w['s'].strip())
        if not m or m.group(3).lower() not in MOIS:
            continue
        # bandeau du jour : le plus petit rectangle blanc qui contient son titre (le
        # fond de la page et celui de la rangée le contiennent aussi)
        r = min((r for r in blancs if r['x0'] - 1 <= w['x'] < r['x1'] and r['y0'] < w['y'] < r['y1']),
                key=lambda r: (r['y1'] - r['y0']) * (r['x1'] - r['x0']), default=None)
        if r is None:
            continue
        try:
            d = date(int(m.group(4)), MOIS[m.group(3).lower()], int(m.group(2)))
        except ValueError:
            continue
        cases.append({'date': d, 'haut': r['y0'], 'x0': r['x0'], 'x1': r['x1'], 'titre_haut': r['y1']})
    sans_date = bool(qui and not cases)
    if sans_date:
        cases = _cases_semaines(mots, filigranes, traits)
    if not qui or not cases:
        return None
    grille_x0 = min(c['x0'] for c in cases)
    # Rangées de jours (même haut d'axe), de haut en bas
    hauts = []
    for c in sorted(cases, key=lambda c: -c['haut']):
        if not hauts or hauts[-1][0] - c['haut'] > 1:
            hauts.append([c['haut'], c['titre_haut']])
    epais = sorted({round(l['p'][1], 1) for l in traits if l['w'] >= 1.5 and _noir(l['c'])
                    and abs(l['p'][1] - l['q'][1]) < 1}, reverse=True)
    roses_y = [l['p'][1] for l in traits if _rose(l['c']) and l['w'] >= 2 and abs(l['p'][1] - l['q'][1]) < 1]
    heures = [(w['y'], w['s'].strip(), w['t']) for w in mots if w['x'] < grille_x0 and _HEURE.match(w['s'].strip())]
    rangees = []
    tops = []
    for i, (haut, _) in enumerate(hauts):
        suivant = hauts[i + 1][1] if i + 1 < len(hauts) else None
        bas = max((y for y in epais if y < haut - 10), default=None)
        if suivant is not None and (bas is None or suivant > bas):
            bas = suivant
        # première étiquette d'heure de la rangée (sur l'axe à gauche, la plus haute) ;
        # la dernière, au bas de la rangée, donne la fin de la journée affichée
        etiq = [(y, s, t) for y, s, t in heures if (bas is None or y > bas) and y < haut]
        fin_jour = FIN_JOUR          # étiquette du bas effacée faute de place : 21h00
        if etiq:
            hm = _HEURE.match(max(etiq)[1])
            tops.append(int(hm.group(1)) * 60 + int(hm.group(2)))
            y, s, t = min(etiq)
            if bas is not None and y - bas <= 1.5 * t:
                hm = _HEURE.match(s)
                fin_jour = int(hm.group(1)) * 60 + int(hm.group(2))
        rangees.append({'haut': haut, 'bas': bas, 'fin_jour': fin_jour, 'etiq': etiq,
                        'rose': max((y for y in roses_y if (bas is None or y > bas) and y < haut), default=None)})
    # Heure du haut de l'axe, commune à la page : la plus tôt des premières étiquettes.
    # Un jour dont le premier cours est à 8h30 n'affiche que « 8h30 », posée sous le
    # haut de l'axe, qui reste 8h00.
    debut = min(tops) if tops else 8 * 60
    if sans_date:
        # Semaines en colonnes : « 8h00 » manque en haut de toutes les rangées quand une
        # « 8h30 » la chevaucherait (cours ou hachure à 8h30 dans l'une des dix
        # semaines). Le haut de l'axe se déduit alors du trait rose de midi et du bas de
        # la rangée (« 21h00 »), dont l'écart donne l'échelle.
        hauts_axe = sorted(MIDI - (rg['haut'] - rg['rose']) / ((rg['rose'] - rg['bas']) / ((rg['fin_jour'] - MIDI) / 60)) * 60
                           for rg in rangees if rg['rose'] is not None and rg['bas'] is not None
                           and rg['fin_jour'] > MIDI and rg['rose'] > rg['bas'])
        if hauts_axe:
            debut = _arrondi(hauts_axe[len(hauts_axe) // 2], 30)
    echelles = []
    for rg in rangees:
        # échelle : le trait rose de midi
        rg['uph'] = (rg['haut'] - rg['rose']) / ((MIDI - debut) / 60) \
            if rg['rose'] is not None and debut < MIDI else None
        if rg['uph'] and rg['uph'] > 0:
            echelles.append(rg['uph'])
    echelles.sort()
    defaut = echelles[len(echelles) // 2] if echelles else 36.0
    for rg in rangees:
        if not (rg['uph'] and abs(rg['uph'] - defaut) <= 0.05 * defaut):
            rg['uph'] = defaut
        if rg['bas'] is None:
            rg['bas'] = rg['haut'] - (FIN_JOUR - debut) / 60 * rg['uph'] - 2 * rg['uph']
    if sans_date:
        # Semaines en colonnes : axe régulier exigé (journée complète). Chaque étiquette
        # est posée contre le trait de son heure, juste dessous (ligne de base à environ
        # une hauteur de caractère) ou juste dessus ; des horaires compactés (heures
        # sans cours réduites) l'en éloigneraient, et les hachures seraient lues à de
        # fausses heures : page refusée.
        for rg in rangees:
            for y, s, t in rg['etiq']:
                hm = _HEURE.match(s)
                attendu = rg['haut'] - (int(hm.group(1)) * 60 + int(hm.group(2)) - debut) / 60 * rg['uph']
                if not -1.2 * t - 4 <= y - attendu <= 0.6 * t + 4:
                    return None
    # taille des tirets de hachure : la plus fréquente
    nb_taille = Counter()
    for (_, t), segs in tirets.items():
        nb_taille[t] += sum(s[0] for s in segs)
    taille = nb_taille.most_common(1)[0][0] if nb_taille else 0
    # Rangées de hachures réparties entre les cases : (rangée de jours, colonne) -> [y].
    # Une rangée de tirets appartient au jour qui contient le milieu de ses tirets ;
    # il en faut au moins 3 dans la case (un « - » isolé est un trait d'union).
    colonnes = sorted({(c['x0'], c['x1']) for c in cases})
    x0s = [c[0] for c in colonnes]
    par_case = defaultdict(list)
    for (y, t), segs in tirets.items():
        if t != taille:
            continue
        ym = y + 0.4 * taille
        ir = next((i for i, rg in enumerate(rangees) if rg['bas'] < ym < rg['haut']), None)
        if ir is None:
            continue
        nb = Counter()
        for n, xa, xb in segs:
            ic = bisect_right(x0s, (xa + xb) / 2) - 1
            if ic >= 0 and xa > colonnes[ic][0] - 1 and xb < colonnes[ic][1] + 1:
                nb[ic] += n
        for ic, n in nb.items():
            if n >= 3:
                par_case[(ir, ic)].append(y)
    couleurs = [r for r in rects if not _blanc(r['c'])] if avec_cours else []
    # Cours posés dans Hyperplanning : lus là où leur case dit la classe.
    #  * Une semaine par page (une seule colonne de jours) : texte complet (matière,
    #    classe, groupe, salle).
    #  * Semaines en colonnes, jours non datés : texte presque complet ; le bout d'une
    #    ligne trop longue devient « (...) », et une case d'une heure ne montre que
    #    « ... » (cours illisible).
    #  * Jours datés, plusieurs semaines côte à côte : le bandeau du jour prend la place,
    #    la classe est le plus souvent masquée : les cours n'y sont pas lus.
    hebdo = len(colonnes) == 1
    lit_cours = hebdo or sans_date
    boites = []
    if lit_cours:
        larg_min = min(300, 0.3 * min(x1 - x0 for x0, x1 in colonnes))
        vus = set()
        for r in rects:
            k = (round(r['x0']), round(r['y0']), round(r['x1']), round(r['y1']))
            if not _blanc(r['c']) and r['x1'] - r['x0'] > larg_min and k not in vus:
                vus.add(k)
                boites.append(r)
    jours = []
    for b in cases:
        ir = next(i for i, r in enumerate(rangees) if abs(r['haut'] - b['haut']) <= 1)
        ic = colonnes.index((b['x0'], b['x1']))
        rg = rangees[ir]
        haut, bas, uph = rg['haut'], rg['bas'], rg['uph']

        def heure(y, haut=haut, uph=uph):
            return debut + (haut - y) / uph * 60
        rangs = sorted(par_case.get((ir, ic), ()), reverse=True)
        zones = []
        if rangs:
            pas = min((p - q for p, q in zip(rangs, rangs[1:])), default=0.15 * taille) or 0.15 * taille
            groupes, cur = [], [rangs[0]]
            for y in rangs[1:]:
                if cur[-1] - y <= pas * 1.6:
                    cur.append(y)
                else:
                    groupes.append(cur)
                    cur = [y]
            groupes.append(cur)
            for g in groupes:
                d = _arrondi(heure(g[0] + 0.45 * taille))
                f = _arrondi(heure(g[-1] + 0.15 * taille))
                # Hachures jusqu'au bas de la case : jusqu'à la fin de la journée
                # affichée. Quand plusieurs semaines sont côte à côte, la fin de
                # soirée sans cours est réduite à rien (« 21h00 » posée au niveau de
                # 19h30) : l'échelle ne la donne pas.
                if rg['fin_jour'] and g[-1] + 0.15 * taille - bas <= 2 * pas + 1:
                    f = max(f, rg['fin_jour'])
                d, f = max(debut, d), min(FIN_JOUR, f)
                if f > d:
                    zones.append((d, f))
        cours = sorted((heure(r['y1']), heure(r['y0'])) for r in couleurs
                       if r['x1'] - r['x0'] > 0.5 * (b['x1'] - b['x0']) and b['x0'] - 1 <= r['x0']
                       and r['x1'] <= b['x1'] + 1 and bas - 1 <= r['y0'] and r['y1'] <= haut + 1)
        # jour fermé : « Férié » écrit en biais dans la case (son origine y est posée)
        ferie = any(b['x0'] <= fx <= b['x1'] and bas < fy < haut and cle_nom(t) == 'FERIE'
                    for (fx, fy), t in filigranes.items())
        # cours posés dans Hyperplanning, avec ce que dit leur case
        cours_hp = []
        for r in boites:
            if not (b['x0'] - 1 <= r['x0'] and r['x1'] <= b['x1'] + 1 and bas - 1 <= r['y0'] and r['y1'] <= haut + 1):
                continue
            dedans = [t for t in textes if r['x0'] <= t['x'] <= r['x1'] and r['y0'] <= t['y'] <= r['y1']]
            d, f = _arrondi(heure(r['y1']), 5), _arrondi(heure(r['y0']), 5)
            if f > d:
                cours_hp.append(dict(lire_case_cours(dedans, gras), debut=d, fin=f))
        cours_hp.sort(key=lambda c: (c['debut'], c['fin']))
        jours.append({'date': b['date'], 'zones': zones, 'cours': cours, 'ferie': ferie, 'cours_hp': cours_hp})
    return {'qui': qui, 'jours': jours, 'hebdo': hebdo, 'cours_lus': lit_cours}


def lire_pdf(flux, avec_cours=False, pages=None):
    """Fichier PDF (chemin, octets ou flux) -> {'pages' (nombre total), 'lues',
    'ignorees', 'enseignants': {nom affiché: {date: [(début, fin), …]}}, 'cours': {…},
    'feries': {date: nombre de pages qui le marquent « Férié »},
    'jours_vus': {date: nombre de pages qui affichent ce jour},
    'cours_hp': {nom affiché: {date: [{debut, fin, matiere, classes, groupes, salles,
    gim, lisible, texte}, …]}} (pages « une semaine », ou semaines en colonnes sans
    date dans les cases), 'pages_cours': leur nombre}.
    `pages` : plage [début, fin[ des pages à lire (0 = la première), pour découper un
    gros fichier en plusieurs requêtes. Une page qui n'a pas de jours datés est
    comptée dans `ignorees` ; un même jour lu deux fois réunit ses zones."""
    from pypdf import PdfReader
    if isinstance(flux, (bytes, bytearray)):
        flux = io.BytesIO(flux)
    lecteur = PdfReader(flux)
    total = len(lecteur.pages)
    a, b = pages if pages else (0, total)
    a, b = max(0, a), min(total, b)
    ens = defaultdict(lambda: defaultdict(list))
    cours = defaultdict(lambda: defaultdict(list))
    cours_hp = defaultdict(lambda: defaultdict(list))
    ignorees = pages_cours = 0
    feries, vus = Counter(), Counter()
    for i in range(a, b):
        page = lecteur.pages[i]
        contenu = page.get_contents()
        res = analyser_page(contenu.get_data(), avec_cours, _polices_grasses(page)) if contenu is not None else None
        if res is None:
            ignorees += 1
            continue
        pages_cours += res['cours_lus']
        for j in res['jours']:
            ens[res['qui']][j['date']].extend(j['zones'])
            vus[j['date']] += 1
            if j['ferie']:
                feries[j['date']] += 1
            if avec_cours:
                cours[res['qui']][j['date']].extend(j['cours'])
            if res['cours_lus']:
                cours_hp[res['qui']][j['date']] = j['cours_hp']
    return {'pages': total, 'lues': max(0, b - a), 'ignorees': ignorees,
            'enseignants': {q: {d: _fusion(z) for d, z in jours.items()} for q, jours in ens.items()},
            'cours': {q: dict(jours) for q, jours in cours.items()},
            'feries': dict(feries), 'jours_vus': dict(vus),
            'cours_hp': {q: dict(jours) for q, jours in cours_hp.items()}, 'pages_cours': pages_cours}


def _polices_grasses(page):
    """Ressources de police en gras (non italique) de la page : le nom de la matière
    dans une case de cours."""
    try:
        polices = page['/Resources']['/Font']
        out = tuple(str(k) for k in polices
                    if 'Bold' in str(polices[k].get('/BaseFont', '')) and 'Italic' not in str(polices[k].get('/BaseFont', '')))
        return out or ('/F1',)
    except (KeyError, TypeError, AttributeError):
        return ('/F1',)


def _fusion(zones):
    out = []
    for d, f in sorted(zones):
        if out and d <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], f))
        else:
            out.append((d, f))
    return out


def nom_sans_civilite(qui):
    return _CIVILITE.sub('', (qui or '').strip()).strip()


def cle_nom(s):
    """Nom comparable : sans accents, en majuscules, lettres seules."""
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode()
    return re.sub(r'[^A-Z]', '', s.upper())


def rapprocher(qui, enseignants):
    """Nom lu dans le PDF -> (id, 'exact' | 'approché') ou (None, None), parmi
    enseignants = [(id, nom)]. Exact : même nom ; approché : un seul enseignant dont le
    nom est contenu dans celui du PDF (prénom ajouté…) ou l'inverse."""
    k = cle_nom(nom_sans_civilite(qui))
    if not k:
        return None, None
    exacts = [i for i, n in enseignants if cle_nom(n) == k]
    if len(exacts) == 1:
        return exacts[0], 'exact'
    if exacts:
        return None, None
    proches = [i for i, n in enseignants if len(cle_nom(n)) >= 3 and (cle_nom(n) in k or k in cle_nom(n))]
    if len(proches) == 1:
        return proches[0], 'approché'
    return None, None
