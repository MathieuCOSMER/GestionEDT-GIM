// ===== ONGLET AIDE : le mode d'emploi du site =====
// Rangé comme le site : une rubrique par grand onglet, une section par écran ou par
// notion, puis des pas-à-pas, les questions fréquentes et un glossaire. Chaque
// section dit à quoi sert l'écran, comment s'en servir et ce qu'il faut savoir.
// Les accès (qui voit, qui modifie) ne sont pas recopiés ici : ils sont lus au
// serveur (/api/aide/acces), réglages du superadmin compris, et restent donc justes.
// Le bouton « ? » en bas à droite de chaque écran ouvre la section qui le décrit.
//
// L'aide ne montre QUE ce que la session ouvre : une section dont l'écran est fermé
// à la session n'apparaît ni dans les rubriques, ni dans la recherche, ni par un
// renvoi. C'est la connexion en cours qui compte : un enseignant entré sans son mot
// de passe n'a l'aide que de ce qu'ouvre cette connexion-là.
//
// Ce fichier est chargé après le script principal de index.html, dont il utilise
// l'état (state, tabHidden, canEditTab…) et les fonctions de navigation. Le contenu
// n'est construit qu'au premier affichage : tout ce qu'il emprunte existe alors.

// ---- Briques de rédaction ----
function _aUi(t) { return `<span class="aide-ui">${t}</span>`; }          // bouton, case, liste
function _aOng(t) { return `<span class="aide-ong">${t}</span>`; }        // onglet › sous-onglet
function _aLien(id, t) {           // renvoi vers une autre section (texte simple si elle est fermée)
    return `<a href="#" class="aide-lien" data-aide-lien="${id}" onclick="aideAller('${id}');return false">${t}</a>`;
}
function _aEx(titre, html) {
    return `<div class="aide-ex"><div class="aide-ex-t">Exemple — ${titre}</div>${html}</div>`;
}
function _aTip(html) { return `<div class="aide-tip"><b>Astuce.</b> ${html}</div>`; }
function _aWarn(html) { return `<div class="aide-warn"><b>Attention.</b> ${html}</div>`; }
// Étapes numérotées ; une étape vide (écran fermé à la session, cf. _aSi) est sautée
function _aSteps(items) { return `<ol class="aide-steps">${items.filter(Boolean).map(i => `<li>${i}</li>`).join('')}</ol>`; }
// Pastille colorée, aux couleurs qu'elle a dans le site (décisions de jury, statuts…)
function _aCode(txt, style, titre) {
    return `<span class="aide-code" style="${style || 'background:#f3f4f6;color:#374151'}"${
        titre ? ` title="${esc(titre)}"` : ''}>${txt}</span>`;
}
function _aDec(code) {          // décision d'année (grille Jury)
    return _aCode(code, (typeof _JURY_DEC_STYLE !== 'undefined' && _JURY_DEC_STYLE[code]) || '');
}
function _aUe(code) {           // code d'UE (grille Jury)
    return _aCode(code, (typeof _JURY_CODE_STYLE !== 'undefined' && _JURY_CODE_STYLE[code]) || '');
}
function _aStatut(st) {         // statut d'un étudiant dans sa cohorte
    return _aCode(st, 'background:' + (typeof _statutColor === 'function' ? _statutColor(st) : '#f3f4f6')
        + ';color:#374151');
}
// Passage écrit seulement pour les sessions qui ouvrent l'écran `cle` (une clé ou une
// liste : il suffit d'une), ou qui peuvent y enregistrer (_aSiModif). À employer dans
// des sections dont le texte est une fonction : il se calcule alors à l'affichage.
function _aSi(cle, html) { return [].concat(cle).some(_aideOngletOuvert) ? html : ''; }
function _aSiModif(cle, html) {
    return [].concat(cle).some(k => _aideOngletOuvert(k) && canEditTab(k)) ? html : '';
}
// Passage réservé au compte Admin (superadmin)
function _aSuper(html) { return state.superadmin ? html : ''; }
// Lignes d'un tableau d'onglets : [clé(s), cellule, cellule…], celles des écrans ouverts seulement
function _aLignes(rows) {
    return rows.map(([cle, ...cells]) => _aSi(cle, `<tr>${cells.map(c => `<td>${c}</td>`).join('')}</tr>`)).join('');
}

// ---- État de l'onglet ----
const _aide = {
    rub: 'demarrer',    // rubrique affichée
    q: '',              // recherche en cours
    acces: null,        // réponse de /api/aide/acces (null tant qu'elle n'est pas lue)
    aller: null,        // section à montrer au prochain rendu (bouton « ? », renvoi)
    marquer: null,      // mots à surligner dans la section ouverte depuis la recherche
    sections: null,     // contenu, construit au premier affichage
    texte: null,        // texte brut de chaque section, pour la recherche
};

const AIDE_RUBRIQUES = [
    { id: 'demarrer', titre: 'Prise en main',
      intro: "Ce qu'il faut savoir avant tout : se connecter, les profils et leurs droits, les années universitaires, et la façon dont le site enregistre." },
    { id: 'service', titre: 'Service & EDT',
      intro: "L'onglet Service : le bilan des services, la répartition des heures semaine par semaine, les matières, les contraintes et la comparaison avec Hyperplanning." },
    { id: 'promotions', titre: 'Promotions',
      intro: "Une promotion est une cohorte de trois ans. On y gère son effectif, ses groupes, son calendrier, ses notes, ses jurys et le devenir de chaque étudiant." },
    { id: 'etudiants', titre: 'Étudiants',
      intro: "Le registre des étudiants, la fiche de chacun et les photos (trombinoscope)." },
    { id: 'suivi', titre: 'Stages & alternance',
      intro: "Les fiches de suivi des stagiaires et des alternants : entreprise, tuteurs, mission, et leurs statistiques." },
    { id: 'programme', titre: 'Programme',
      intro: "Le programme national : matières, compétences (UE), coefficients, volumes horaires et contenus." },
    { id: 'stats', titre: 'Statistiques',
      intro: "Le tableau de bord du département : étudiants, recrutement, parcours, résultats et enseignement." },
    { id: 'admin', titre: 'Administration',
      intro: "Les enseignants et leurs accès, les salles, les paramètres du site, les sauvegardes et le journal, et l'onglet Mon Compte." },
    { id: 'exemples', titre: 'Pas à pas',
      intro: "Les grandes tâches de l'année, du début à la fin, dans l'ordre où on les fait." },
    { id: 'faq', titre: 'Questions fréquentes',
      intro: "Les situations qui reviennent le plus souvent, et ce qu'il faut faire." },
    { id: 'glossaire', titre: 'Glossaire',
      intro: "Les sigles et les mots du site, du BUT et de la scolarité." },
];

// ---- Accès : ce que la session ouvre ----
// Groupe parent d'une clé d'onglet : un sous-onglet n'est ouvert que si son onglet l'est
function _aideParent(key) {
    const g = key.split(':')[0];
    return { promo: 'nav:promotions', prog: 'nav:programme', st: 'nav:statistiques',
             svc: 'nav:service', rep: 'svc:repartition' }[g] || null;
}
// L'onglet `key` est-il ouvert à la session ? Mêmes règles que la barre d'onglets :
// accès calculés par le serveur, puis boutons masqués selon le rôle.
function _aideOngletOuvert(key) {
    if (!key) return true;
    if (tabHidden(key)) return false;
    const parent = _aideParent(key);
    if (parent && !_aideOngletOuvert(parent)) return false;
    if (key.startsWith('promo:')) {
        // Hors de l'onglet Saisie Notes : c'est la page Promotions qui compte ici
        const garde = _promoSaisieOnly;
        _promoSaisieOnly = false;
        try { return _promoTabAllowed(key.slice(6)); } finally { _promoSaisieOnly = garde; }
    }
    const el = _tvEl(key);
    return !el || getComputedStyle(el).display !== 'none';
}
// Clés d'accès d'une section : une seule le plus souvent, plusieurs quand le même
// écran s'atteint par deux onglets selon le profil (Saisie Notes)
function _aideCles(s) { return !s.onglet ? [] : [].concat(s.onglet); }
// Section utile à la session : un de ses écrans est ouvert ; pour une section qui
// décrit une tâche (pour: 'modifier'), la session peut y enregistrer ; pour une
// tâche du compte Admin (pour: 'superadmin'), c'est lui qui est connecté.
function _aideOuvert(s) {
    if (s.pour === 'superadmin' && !state.superadmin) return false;
    const ks = _aideCles(s);
    return !ks.length || ks.some(k => _aideOngletOuvert(k) && (s.pour !== 'modifier' || canEditTab(k)));
}
// Écran à ouvrir : `cible` suit l'ordre de `onglet` — le premier ouvert à la session
function _aideCible(s) {
    if (!s.cible) return null;
    const ks = _aideCles(s), cs = [].concat(s.cible);
    for (let i = 0; i < cs.length; i++) {
        const k = ks[Math.min(i, ks.length - 1)];
        if (!k || _aideOngletOuvert(k)) return cs[i];
    }
    return null;
}
// Section `id` affichable à la session (existe, et son écran lui est ouvert)
function _aideVisible(id) {
    const s = (_aide.sections || []).find(x => x.id === id);
    return !!s && _aideOuvert(s);
}
// Rubrique qui a au moins une section affichable à la session
function _aideRubriqueVisible(id) { return (_aide.sections || []).some(s => s.rub === id && _aideOuvert(s)); }
// Titre et présentation d'une rubrique : l'Administration réduite au seul Mon Compte
// (session d'enseignant) prend le nom de ce qu'elle contient
function _aideRubAdminSeule(r) {
    if (r.id !== 'admin') return false;
    const ids = (_aide.sections || []).filter(s => s.rub === 'admin' && _aideOuvert(s)).map(s => s.id);
    return ids.length === 1 && ids[0] === 'mon-compte';
}
function _aideRubTitre(r) { return _aideRubAdminSeule(r) ? 'Mon Compte' : r.titre; }
function _aideRubIntro(r) { return _aideRubAdminSeule(r) ? 'Vos coordonnées et vos heures hors GIM.' : r.intro; }
// Renvois d'une zone affichée : un lien vers une section fermée à la session redevient
// du texte, une carte vers une rubrique vide disparaît
function _aideNettoyerLiens(el) {
    el.querySelectorAll('a[data-aide-lien]').forEach(a => {
        if (_aideVisible(a.dataset.aideLien)) return;
        a.replaceWith(...a.childNodes);
    });
    el.querySelectorAll('[data-aide-carte]').forEach(c => {
        const cible = c.dataset.aideCarte;
        const ok = cible.startsWith('rub:') ? _aideRubriqueVisible(cible.slice(4)) : _aideVisible(cible);
        if (!ok) c.remove();
    });
}
// Profils d'onglets de la session (pour les repérer dans les pastilles d'accès)
function _aideMesProfils() {
    if (state.superadmin) return [];
    if (state.role === 'admin')
        return state.resp.length ? state.resp.map(r => 'resp_' + r).concat('teacher_pwd') : ['admin'];
    return [state.promoAccess ? 'teacher_pwd' : 'teacher'];
}
function _aideNoeud(key) {
    const find = nodes => {
        for (const n of nodes || []) {
            if (n.key === key) return n;
            const r = find(n.children);
            if (r) return r;
        }
        return null;
    };
    return _aide.acces ? find(_aide.acces.tree) : null;
}
// Pastilles « Modifier : … · Consulter : … » d'une section, d'après les accès réels ;
// une ligne par onglet ouvert à la session quand elle en a plusieurs, chacune nommée
function _aideAccesSection(s) {
    const ks = _aideCles(s).filter(_aideOngletOuvert);
    if (ks.length < 2) return _aideAccesHtml(ks[0]);
    // Nom complet (« Promotions › Saisie Notes ») : deux onglets peuvent porter le même libellé
    const nom = k => [_aideParent(k), k].filter(Boolean).map(x => (_aideNoeud(x) || {}).label).filter(Boolean).join(' › ');
    return ks.map(k => _aideAccesHtml(k, nom(k))).join('');
}
function _aideAccesHtml(key, nom) {
    const a = _aide.acces && key && _aide.acces.acces[key];
    if (!a) return '';
    const moi = new Set(_aideMesProfils());
    const chip = (p, modif) => `<span class="aide-prof${modif ? ' modif' : ''}${moi.has(p) ? ' moi' : ''}"${
        moi.has(p) ? ' title="Votre session"' : ''}>${esc(TAB_PROFILE_LABELS[p] || p)}</span>`;
    const modif = a.modifier;
    const voir = a.voir.filter(p => !modif.includes(p));
    const noeud = _aideNoeud(key);
    let html = nom ? `<span class="aide-acces-l" style="color:#374151">${esc(nom)} —</span>` : '';
    if (modif.length) html += `<span class="aide-acces-l">Modifier :</span>${modif.map(p => chip(p, true)).join('')}`;
    if (voir.length) html += `<span class="aide-acces-l">${noeud && noeud.consultation ? 'Ouvert à' : 'Consulter'} :</span>${
        voir.map(p => chip(p)).join('')}`;
    html += modif.length || voir.length
        ? '<span class="aide-acces-l" title="Le compte Admin a tous les droits, partout">· superadmin : tout</span>'
        : '<span class="aide-acces-l">Réservé au superadmin</span>';
    return `<div class="aide-acces">${html}</div>`;
}

// ---- Rendu ----
async function aideCharger() {
    if (!_aide.sections) _aide.sections = _aideConstruire();
    if (!_aide.acces) {
        try { _aide.acces = await api('/aide/acces'); } catch (e) { _aide.acces = null; }
        _aide.texte = null;     // des sections se calculent d'après les accès
    }
    const q = document.getElementById('aide-q');
    _aide.q = q ? q.value.trim() : '';
    aideRender();
}

function aideRubrique(id) {
    _aide.rub = id;
    _aide.q = '';
    const q = document.getElementById('aide-q');
    if (q) q.value = '';
    aideRender();
    window.scrollTo(0, 0);
}

function aideRechercher(v) {
    _aide.q = (v || '').trim();
    aideRender();
}

// Montre une section : depuis un renvoi, un résultat de recherche ou le bouton « ? ».
// Une section fermée à la session ne s'ouvre pas : on reste sur l'accueil de l'aide.
function aideAller(id, mots) {
    if (!_aide.sections) _aide.sections = _aideConstruire();
    if (!_aideVisible(id)) { id = 'bienvenue'; mots = null; }
    _aide.aller = id;
    _aide.marquer = mots || null;
    _aide.q = '';
    const q = document.getElementById('aide-q');
    if (q) q.value = '';
    if (!document.getElementById('page-aide').classList.contains('active')) { showPage('aide'); return; }
    aideRender();
}

function aideRender() {
    const secs = _aide.sections;
    if (!secs) return;
    // Seules existent à l'écran les sections que la session ouvre (_aideOuvert)
    const cible = _aide.aller && secs.find(s => s.id === _aide.aller && _aideOuvert(s));
    if (cible) _aide.rub = cible.rub;
    const rubs = AIDE_RUBRIQUES.filter(r => _aideRubriqueVisible(r.id));
    if (!rubs.some(r => r.id === _aide.rub)) _aide.rub = (rubs[0] || AIDE_RUBRIQUES[0]).id;
    document.getElementById('aide-rubriques').innerHTML = rubs.map(r =>
        `<button type="button" class="subtab${!_aide.q && r.id === _aide.rub ? ' active' : ''}"
            onclick="aideRubrique('${r.id}')">${esc(_aideRubTitre(r))}</button>`).join('');
    const el = document.getElementById('aide-content');
    if (_aide.q) {
        el.innerHTML = _aideRenduRecherche();
        _aideNettoyerLiens(el);
        return;
    }
    const rub = AIDE_RUBRIQUES.find(r => r.id === _aide.rub);
    const liste = secs.filter(s => s.rub === _aide.rub && _aideOuvert(s));
    el.innerHTML = `<div class="aide-layout">
        <aside class="aide-toc"><div class="aide-toc-t">${esc(_aideRubTitre(rub))}</div>${liste.map(s =>
            `<a href="#" data-aide="${s.id}" onclick="aideAller('${s.id}');return false">${s.titre}</a>`).join('')}</aside>
        <div>
            <p class="aide-intro">${_aideRubIntro(rub)}</p>
            ${liste.map(_aideSection).join('')}
        </div></div>`;
    _aideNettoyerLiens(el);
    if (cible) {
        const sec = document.getElementById('aide-s-' + cible.id);
        if (sec) {
            if (_aide.marquer) _aideSurlignerDans(sec, _aide.marquer);
            sec.scrollIntoView({ block: 'start' });
            sec.classList.add('aide-flash');
            setTimeout(() => sec.classList.remove('aide-flash'), 1900);
        }
        _aide.aller = null;
        _aide.marquer = null;
    }
    _aideSuivreSommaire();
}

// Une section (toujours ouverte à la session : aideRender ne rend que celles-là)
function _aideSection(s) {
    const html = typeof s.html === 'function' ? s.html() : s.html;
    const cible = _aideCible(s);
    return `<section class="aide-sec" id="aide-s-${s.id}">
        <h2>${s.titre}</h2>
        ${s.chemin ? `<div class="aide-chemin">${s.chemin}</div>` : ''}
        ${_aideAccesSection(s)}
        ${html}
        ${cible ? `<div class="aide-ouvrir"><button type="button" class="btn btn-secondary btn-sm"
            onclick="aideOuvrir('${cible}')">Ouvrir cet écran →</button></div>` : ''}
    </section>`;
}

// Sommaire : la section en cours de lecture y est mise en avant
function _aideSuivreSommaire() {
    const page = document.getElementById('page-aide');
    if (!page || !page.classList.contains('active')) return;
    const liens = [...document.querySelectorAll('.aide-toc a[data-aide]')];
    if (!liens.length) return;
    let cur = liens[0].dataset.aide;
    for (const a of liens) {
        const sec = document.getElementById('aide-s-' + a.dataset.aide);
        if (sec && sec.getBoundingClientRect().top < 140) cur = a.dataset.aide;
    }
    liens.forEach(a => a.classList.toggle('active', a.dataset.aide === cur));
}
let _aideScrollPrevu = false;
window.addEventListener('scroll', () => {
    if (_aideScrollPrevu) return;
    _aideScrollPrevu = true;
    requestAnimationFrame(() => { _aideScrollPrevu = false; _aideSuivreSommaire(); });
}, { passive: true });

// ---- Recherche ----
function _aideTexte(s) {
    if (!_aide.texte) _aide.texte = {};
    if (!_aide.texte[s.id]) {
        const div = document.createElement('div');
        div.innerHTML = typeof s.html === 'function' ? s.html() : s.html;
        const corps = div.textContent.replace(/\s+/g, ' ').trim();
        const titre = s.titre.replace(/<[^>]+>/g, '');
        _aide.texte[s.id] = { titre, corps, cle: _sansAccent(titre + ' ' + (s.chemin || '') + ' '
                                                            + corps + ' ' + (s.mots || '')) };
    }
    return _aide.texte[s.id];
}
function _aideMots(q) { return _sansAccent(q).split(/\s+/).filter(m => m.length > 1 || /\d/.test(m)); }

// Texte échappé, mots surlignés (sans tenir compte des accents ni de la casse)
function _aideSurligner(txt, mots) {
    const cle = _sansAccent(txt);
    const zones = [];
    mots.forEach(m => {
        for (let i = cle.indexOf(m); i >= 0 && zones.length < 60; i = cle.indexOf(m, i + m.length))
            zones.push([i, i + m.length]);
    });
    zones.sort((a, b) => a[0] - b[0]);
    let out = '', pos = 0;
    zones.forEach(([a, b]) => {
        if (a < pos) return;
        out += esc(txt.slice(pos, a)) + '<mark>' + esc(txt.slice(a, b)) + '</mark>';
        pos = b;
    });
    return out + esc(txt.slice(pos));
}
// Surligne les mots cherchés dans une section affichée (nœuds de texte seulement)
function _aideSurlignerDans(el, mots) {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const noeuds = [];
    while (walker.nextNode()) noeuds.push(walker.currentNode);
    noeuds.forEach(n => {
        if (!n.nodeValue.trim() || n.parentNode.closest('button, .aide-acces')) return;
        const cle = _sansAccent(n.nodeValue);
        if (!mots.some(m => cle.includes(m))) return;
        const span = document.createElement('span');
        span.innerHTML = _aideSurligner(n.nodeValue, mots);
        n.parentNode.replaceChild(span, n);
    });
}
// Extrait du texte autour de la première occurrence trouvée
function _aideExtrait(corps, mots) {
    const cle = _sansAccent(corps);
    let i = -1;
    for (const m of mots) { const j = cle.indexOf(m); if (j >= 0 && (i < 0 || j < i)) i = j; }
    if (i < 0) return _aideSurligner(corps.slice(0, 200), mots) + (corps.length > 200 ? '…' : '');
    const a = Math.max(0, i - 90), b = Math.min(corps.length, i + 190);
    return (a ? '…' : '') + _aideSurligner(corps.slice(a, b), mots) + (b < corps.length ? '…' : '');
}
// Résultats : parmi les seules sections ouvertes à la session — le reste n'est ni
// cherché, ni compté
function _aideRenduRecherche() {
    const mots = _aideMots(_aide.q);
    if (!mots.length) return '<div class="empty">Tapez au moins deux lettres.</div>';
    const trouve = _aide.sections.filter(s => _aideOuvert(s) && mots.every(m => _aideTexte(s).cle.includes(m)));
    // Pertinence : les mots dans le titre d'abord, puis le nombre d'occurrences
    const score = s => {
        const t = _aideTexte(s), titre = _sansAccent(t.titre);
        return mots.reduce((n, m) => n + (titre.includes(m) ? 50 : 0) + t.cle.split(m).length - 1, 0);
    };
    const scores = new Map(trouve.map(s => [s, score(s)]));
    trouve.sort((a, b) => scores.get(b) - scores.get(a));
    const rubTitre = id => { const r = AIDE_RUBRIQUES.find(x => x.id === id); return r ? _aideRubTitre(r) : ''; };
    // Attribut entre guillemets doubles : le JSON échappé y redevient du JS valide,
    // apostrophes des mots comprises
    const motsJs = esc(JSON.stringify(mots));
    return `<p class="aide-intro"><strong>${trouve.length}</strong> résultat${trouve.length > 1 ? 's' : ''} pour
            « ${esc(_aide.q)} »${trouve.length ? ' — cliquez pour ouvrir la section' : ''}.</p>
        ${trouve.map(s => `<div class="aide-res" onclick="aideAller('${s.id}', ${motsJs})">
            <b>${_aideSurligner(_aideTexte(s).titre, mots)}</b>
            <div class="aide-chemin">${esc(rubTitre(s.rub))}${s.chemin ? ' · ' + s.chemin : ''}</div>
            <p>${_aideExtrait(_aideTexte(s).corps, mots)}</p></div>`).join('')}
        ${!trouve.length ? `<div class="empty">Rien ne correspond. Essayez un autre mot, ou parcourez les rubriques
            (le <a href="#" class="aide-lien" onclick="aideRubrique('glossaire');return false">glossaire</a> explique les sigles).</div>` : ''}`;
}

// ---- Aller sur un écran du site depuis l'aide ----
// `cible` : « page » ou « page/sous-onglet » (promotions/jury, repartition/jour,
// statistiques/recrutement, stages/stats, etudiants/trombi, programme/contenu…)
function aideOuvrir(cible) {
    const [page, sous] = cible.split('/');
    if (page === 'promotions' && sous) {
        _promoSaisieOnly = false;
        if (_promoTabAllowed(sous)) { _promoTab = sous; _syncPromoSubtabs(); }
    } else if (page === 'programme' && sous) {
        if (sous === 'contenu-edit') { _progTab = 'contenu'; _contTab = 'edit'; }
        else _progTab = sous;
    } else if (page === 'statistiques' && sous) {
        _statsTab = sous;
    } else if ((page === 'stages' || page === 'alternance') && sous) {
        _suiviState(page).tab = sous;
    } else if (page === 'etudiants') {
        _etuSelected = null;
        _studentCard = null;
        if (['trombi', 'liste', 'convoquer'].includes(sous)) {
            _etuVue = sous;
            try { localStorage.setItem('etuVue', sous); } catch (e) { /* sans mémoire */ }
        }
    }
    showPage(page);
    if (page === 'repartition' && sous) showRepTab(sous);
    else if (page === 'programme' && sous) setTimeout(() => {
        // Le sous-onglet s'affiche une fois le programme relu (loadPage le rouvre aussi)
        const b = document.getElementById('prog-subtab-' + _progTab);
        if (b && !b.classList.contains('active')) b.click();
    }, 0);
    window.scrollTo(0, 0);
}

// ---- Bouton « ? » : l'aide de l'écran affiché ----
const _AIDE_CONTEXTE = {
    'svc:repartition-enseignant': 'bilan', 'rep:annuelle': 'rep-annuelle', 'rep:jour': 'rep-jour',
    'svc:matieres': 'matieres', 'svc:contraintes': 'contraintes',
    'svc:contraintes-matiere': 'contraintes-matiere', 'svc:comparaison': 'comparaison',
    'promo:effectif': 'promo-effectifs', 'promo:groupes': 'promo-groupes',
    'promo:calendrier': 'promo-calendrier', 'promo:saisie': 'promo-saisie', 'nav:saisie': 'promo-saisie',
    'promo:notes': 'promo-bulletins', 'promo:jury': 'promo-jury', 'promo:devenir': 'promo-devenir',
    'promo:actions': 'promo-actions',
    'prog:coeff': 'prog-coeff', 'prog:matieres': 'prog-matieres', 'prog:contenu': 'prog-contenu',
    'prog:actions': 'prog-actions',
    'nav:enseignants': 'enseignants', 'nav:salles': 'salles', 'nav:journal': 'journal',
    'nav:parametres': 'parametres', 'nav:mon-compte': 'mon-compte',
};
function aideContexte() {
    const key = _currentTabKey() || '';
    let id = _AIDE_CONTEXTE[key];
    if (key.startsWith('etu:')) id = _etuSelected ? (_etuFicheTab === 'suivi' ? 'etu-suivi' : 'etu-fiche')
        : _etuVue === 'trombi' ? 'etu-photos' : _etuVue === 'convoquer' ? 'etu-convoquer' : 'etu-liste';
    else if (key === 'nav:statistiques') id = 'stats-' + _statsTab;
    else if (key === 'nav:stages' || key === 'nav:alternance')
        id = _suiviState(key.slice(4)).tab === 'stats' ? 'suivi-stats' : 'suivi-fiches';
    if (!_aide.sections) _aide.sections = _aideConstruire();
    if (!id || !_aide.sections.some(s => s.id === id)) id = 'bienvenue';
    aideAller(id);
}

// ---- Contenu ----
// Une section : { id, rub, titre, chemin, onglet (clé d'accès, cf. _TAB_TREE),
// pour ('modifier' : tâche réservée à qui peut y enregistrer), cible (écran à
// ouvrir), mots (synonymes pour la recherche), html (texte, ou fonction quand il
// dépend de la session) }.
function _aideConstruire() {
    return [].concat(_aideDemarrer(), _aideService(), _aidePromotions(), _aideEtudiants(), _aideSuivi(),
                     _aideProgramme(), _aideStats(), _aideAdmin(), _aideExemples(), _aideFaq(), _aideGlossaire());
}

// Les onglets que la session voit dans la barre, avec leur libellé
function _aideMesOnglets() {
    return [...document.querySelectorAll('nav > button[id^="nav-"]')]
        .filter(b => getComputedStyle(b).display !== 'none' && b.id !== 'nav-aide')
        .map(b => _aUi(esc(b.textContent.trim()))).join(' ');
}
function _aideQuiSuisJe() {
    if (state.superadmin) return 'avec le compte <b>Admin</b> : superadmin, vous avez tous les droits.';
    if (state.role === 'admin' && state.resp.length)
        return `en <b>session normale</b>, avec vos responsabilités (<b>${esc(respLabel(state.resp))}</b>) :
            vous avez les droits de ces domaines, en plus de ce que fait tout enseignant.`;
    if (state.role === 'admin')
        return 'en <b>session admin</b> (enseignant administrateur) : vous avez les droits d\'administration, sauf ceux réservés au superadmin.';
    if (state.promoAccess)
        return 'comme <b>enseignant, avec votre mot de passe</b> : vous consultez les promotions et saisissez vos notes.';
    return 'comme <b>enseignant, sans mot de passe</b> : l\'accès est réduit au service, au programme et aux statistiques.';
}
// Tableau des accès : les onglets que la session voit (tous pour le superadmin), avec,
// pour chacun, ce que chaque profil peut y faire
function _aideTableAcces() {
    const d = _aide.acces;
    if (!d) return '<p class="aide-masques">Le tableau des accès n\'a pas pu être chargé.</p>';
    const moi = new Set(_aideMesProfils());
    const rows = [];
    const walk = (nodes, depth) => nodes.forEach(n => {
        if (!state.superadmin && !_aideOngletOuvert(n.key)) return;   // ni lui, ni ses sous-onglets
        const a = d.acces[n.key] || { voir: [], modifier: [] };
        rows.push(`<tr><td style="padding-left:${8 + depth * 16}px;white-space:nowrap${depth ? '' : ';font-weight:700'}">${
            esc(n.label)}</td>${d.profiles.map(p => {
                const m = a.modifier.includes(p), v = a.voir.includes(p);
                return `<td style="text-align:center${moi.has(p) ? ';background:#eef2ff' : ''}" title="${
                    m ? 'Voir et modifier' : v ? 'Voir (consultation)' : 'Fermé'}">${
                    m ? '✎' : v ? '👁' : '<span style="color:#d1d5db">—</span>'}</td>`;
            }).join('')}</tr>`);
        walk(n.children, depth + 1);
    });
    walk(d.tree, 0);
    return `<div style="overflow-x:auto"><table><thead><tr><th>Onglet</th>${d.profiles.map(p =>
        `<th style="text-align:center${moi.has(p) ? ';background:#e0e7ff' : ''}">${esc(TAB_PROFILE_LABELS[p] || p)}</th>`).join('')}</tr></thead>
        <tbody>${rows.join('')}</tbody></table></div>
        <p style="font-size:.8rem;color:#6b7280">👁 voir · ✎ voir et modifier · — fermé.
        ${moi.size ? 'Colonne surlignée : votre session.' : ''} Le superadmin a tous les droits, partout.</p>`;
}

function _aideDemarrer() {
    const R = 'demarrer';
    return [
    { id: 'bienvenue', rub: R, titre: 'Bienvenue', mots: 'accueil sommaire présentation à quoi sert',
      html: () => `
        <p>Ce site est l'outil de gestion du département <b>GIM</b> (Génie Industriel et Maintenance) de l'IUT
        de Toulon. Il réunit en un seul endroit ce qui servait autrefois de tableurs séparés${(() => {
            // Ce qu'il réunit, dit d'après les onglets ouverts à la session
            const dom = [
                _aSi('nav:service', 'les services des enseignants et l\'emploi du temps'),
                _aSi('nav:promotions', 'les promotions et la scolarité'),
                _aSi('nav:etudiants', 'le registre des étudiants'),
                _aSi(['nav:stages', 'nav:alternance'], 'le suivi des stages et de l\'alternance'),
                _aSi('nav:programme', 'le programme national'),
                _aSi('nav:statistiques', 'les statistiques du département'),
            ].filter(Boolean);
            return dom.length ? ` ; pour vous : ${dom.slice(0, -1).join(', ')}${dom.length > 1 ? ' et ' : ''}${dom[dom.length - 1]}` : '';
        })()}.</p>
        <div class="aide-tip"><b>Votre session.</b> Vous êtes connecté ${_aideQuiSuisJe()}
            ${_aideMesOnglets() ? `<br>Onglets ouverts : ${_aideMesOnglets()}.` : ''}</div>
        <h3>Par où commencer ?</h3>
        <div class="aide-cartes">
            <div class="aide-carte" data-aide-carte="connexion" onclick="aideAller('connexion')"><b>Se connecter</b><span>Identifiant, mot de passe, première connexion.</span></div>
            <div class="aide-carte" data-aide-carte="sessions" onclick="aideAller('sessions')"><b>Profils et droits</b><span>Qui voit quoi, qui modifie quoi.</span></div>
            <div class="aide-carte" data-aide-carte="annees" onclick="aideAller('annees')"><b>Les années</b><span>Quelle année universitaire est affichée.</span></div>
            <div class="aide-carte" data-aide-carte="enregistrer" onclick="aideAller('enregistrer')"><b>Enregistrer</b><span>Ce qui s'enregistre tout seul, et ce qui attend un clic.</span></div>
            <div class="aide-carte" data-aide-carte="rub:exemples" onclick="aideRubrique('exemples')"><b>Pas à pas</b><span>Les grandes tâches, dans l'ordre où on les fait.</span></div>
            <div class="aide-carte" data-aide-carte="rub:faq" onclick="aideRubrique('faq')"><b>Questions fréquentes</b><span>Les situations qui reviennent le plus souvent.</span></div>
        </div>
        <h3>Vos onglets</h3>
        <table><thead><tr><th>Onglet</th><th>À quoi il sert</th></tr></thead><tbody>${_aLignes([
            ['nav:service', _aUi('Service'), `Les heures d'enseignement : bilan des services, répartition semaine par semaine, contraintes d'emploi du temps. ${_aLien('service-vue', 'En savoir plus')}`],
            [['nav:saisie', 'promo:saisie'], _aUi('Saisie Notes'), `Saisir les notes des sous-matières. ${_aLien('promo-saisie', 'En savoir plus')}`],
            ['nav:promotions', _aUi('Promotions'), `Les cohortes : effectifs, groupes, bulletins, jury… ${_aLien('promo-vue', 'En savoir plus')}`],
            ['nav:etudiants', _aUi('Étudiants'), `Le registre des étudiants, leur fiche, leurs photos et le trombinoscope, leur suivi. ${_aLien('etu-liste', 'En savoir plus')}`],
            [['nav:stages', 'nav:alternance'], _aSi('nav:stages', _aUi('Stages')) + ' ' + _aSi('nav:alternance', _aUi('Alternance')),
             `Les fiches de suivi : entreprise, tuteurs, mission. ${_aLien('suivi-fiches', 'En savoir plus')}`],
            ['nav:programme', _aUi('Programme'), `Le programme national : coefficients, matières, volumes, contenus. ${_aLien('prog-vue', 'En savoir plus')}`],
            ['nav:statistiques', _aUi('Statistiques'), `Le tableau de bord du département. ${_aLien('stats-apercu', 'En savoir plus')}`],
            [['nav:enseignants', 'nav:salles'], _aSi('nav:enseignants', _aUi('Enseignant')) + ' ' + _aSi('nav:salles', _aUi('Salles')),
             `Les listes de référence de l'année. ${_aLien('enseignants', 'En savoir plus')}`],
            [['nav:journal', 'nav:parametres'], _aSi('nav:journal', _aUi('Journal')) + ' ' + _aSi('nav:parametres', _aUi('Paramètres')),
             `Sauvegardes et réglages du site. ${_aLien('parametres', 'En savoir plus')}`],
            ['nav:mon-compte', _aUi('Mon Compte'), `Vos coordonnées et vos heures hors GIM. ${_aLien('mon-compte', 'En savoir plus')}`],
        ])}</tbody></table>
        ${_aTip(`le bouton rond ${_aUi('?')} en bas à droite de chaque écran ouvre directement l'aide de cet écran.
            L'aide ne décrit que les écrans que votre session ouvre.`)}` },

    { id: 'connexion', rub: R, titre: 'Se connecter', mots: 'login identifiant mot de passe oublié première connexion initialiser déconnexion',
      html: () => `
        <p>L'écran de connexion demande un <b>identifiant</b> et un <b>mot de passe</b>.</p>
        <ul>
            <li><b>Enseignant</b> : l'identifiant est votre <b>nom de famille</b>, tel qu'il figure dans la liste des enseignants (majuscules ou minuscules indifférentes).</li>
            <li><b>Administration</b> : l'identifiant <b>Admin</b>, avec son mot de passe.</li>
        </ul>
        <h3>Avec ou sans mot de passe ?</h3>
        <p>Pour un enseignant, le mot de passe est <b>facultatif</b>, mais il change ce que l'on peut faire :</p>
        <table><thead><tr><th>Connexion</th><th>Ce qui est ouvert</th></tr></thead><tbody>
            <tr><td>Nom seul, sans mot de passe</td><td>${_aUi('Service')} (son bilan, la répartition, ses contraintes), ${_aUi('Programme')} en consultation, ${_aUi('Statistiques')}, ${_aUi('Mon Compte')}. Comme n'importe qui peut taper un nom, cette connexion ne reçoit <b>jamais</b> de droit de modification supplémentaire.</td></tr>
            <tr><td>Nom + mot de passe</td><td>${state.role === 'teacher' && !state.promoAccess
                ? `Des onglets en plus, selon les droits que l'administration vous ouvre — et l'aide qui va avec, qui n'apparaît qu'une fois connecté avec votre mot de passe.`
                : `En plus : ${_aUi('Saisie Notes')}, ${_aUi('Promotions')}, ${_aUi('Étudiants')}, ${_aUi('Stages')} et ${_aUi('Alternance')}, selon les droits ouverts au profil.`}
                C'est aussi la seule connexion qui active des droits d'administration ou des responsabilités.</td></tr>
        </tbody></table>
        <h3>Première connexion : créer son mot de passe</h3>
        ${_aSteps([
            `L'administration autorise la création de votre mot de passe (fiche enseignant, ${_aUi('Autoriser la création du mot de passe')}).`,
            `Sur l'écran de connexion, tapez votre nom : le bouton ${_aUi('Initialiser mon mot de passe')} apparaît.`,
            `Choisissez votre mot de passe, deux fois : <b>au moins 8 caractères, dont une majuscule et un caractère spécial</b>.`,
            `${_aUi('Enregistrer et se connecter')} : vous êtes connecté aussitôt.`])}
        ${_aEx('un mot de passe valide', `<code>Maintenance!2026</code> convient (majuscule, caractère spécial, 16 caractères) ;
            <code>maintenance2026</code> est refusé (ni majuscule ni caractère spécial).`)}
        <h3>Mot de passe oublié</h3>
        <p>Il n'y a pas de récupération par e-mail : demandez à l'administration de <b>réinitialiser</b> votre mot de passe.
        Le bouton ${_aUi('Initialiser mon mot de passe')} réapparaît alors sur l'écran de connexion.</p>
        ${_aWarn(`après plusieurs échecs, le bouton de connexion se bloque quelques secondes (compte à rebours affiché) :
            c'est une protection contre les essais au hasard. Patientez, puis réessayez.`)}
        <h3>Se déconnecter</h3>
        <p>Bouton ${_aUi('Déconnexion')}, en haut à droite. Si une grille contient des modifications non enregistrées, le site vous le demande d'abord.</p>` },

    { id: 'sessions', rub: R, titre: 'Profils, sessions et droits', mots: 'rôle superadmin admin responsable resp ftp alt stages enseignant accès droits session normale changer de session',
      html: () => `
        <p>Chaque connexion ouvre une <b>session</b> d'un certain profil. Le badge en haut à droite rappelle la vôtre.</p>
        ${state.role === 'admin' ? `<dl>
            <dt>Superadmin</dt><dd>Le compte <b>Admin</b>. Tous les droits, y compris ceux qui touchent au site entier : droits des enseignants, mots de passe, restauration, journal, années, coefficients HETD, suppression de promotions et de programmes, réglage des accès.</dd>
            <dt>Admin</dt><dd>Un enseignant à qui le superadmin a donné les <b>droits d'administration</b>. Il fait tout le travail courant, sauf ce qui est réservé au superadmin.</dd>
            <dt>Responsables</dt><dd>Un enseignant chargé d'un domaine : <b>Resp. FTP</b> (emploi du temps, matières, services, groupes, effectifs, jury et devenir), <b>Resp. ALT</b> (tuteurs des alternants, jury et devenir), <b>Resp. stages</b> (tuteurs des stages FTP). Ces droits s'ajoutent à ceux de l'enseignant, dans sa session normale ; ils se cumulent.</dd>
            <dt>Enseignant avec mdp</dt><dd>Connecté avec son mot de passe : consulte les promotions, saisit ses notes, suit ses stagiaires et alternants.</dd>
            <dt>Enseignant sans mdp</dt><dd>Connecté par son seul nom : service, programme, statistiques, son compte.</dd>
        </dl>` : `<dl>
            <dt>Enseignant avec mot de passe</dt><dd>Connecté avec son mot de passe${state.promoAccess ? ' — c\'est votre session' : ''}.</dd>
            <dt>Enseignant sans mot de passe</dt><dd>Connecté par son seul nom${state.promoAccess ? '' : ' — c\'est votre session'} : service, programme, statistiques, son compte.</dd>
            <dt>Administration, responsables</dt><dd>Des enseignants reçoivent aussi des droits d'administration ou des responsabilités ; ils les retrouvent en se connectant avec leur mot de passe.</dd>
        </dl>`}
        <h3>Choisir et changer de session</h3>
        <p>Un enseignant qui a des droits d'administration et/ou des responsabilités choisit sa session à la connexion :
        <b>session admin</b> ou <b>session normale</b> (enseignant, avec ses responsabilités). Il en change à tout moment
        avec le bouton ${_aUi('Passer en session admin')} / ${_aUi('Passer en session normale')} de la barre (ou la liste,
        s'il a trois sessions possibles). La page se recharge sur la nouvelle session.</p>
        ${_aTip(`la session normale montre le site tel que le voit un enseignant (votre bilan, vos notes à saisir…) ;
            la session admin, la vue de tous les enseignants. Une modification de vos droits prend effet au prochain changement de session ou à la prochaine connexion.`)}
        <h3>Qui voit et modifie quoi, aujourd'hui</h3>
        <p>Le tableau ci-dessous est lu en direct : il tient compte des réglages du superadmin
        (${_aOng('Paramètres › Accès aux onglets')}). Dans chaque section de l'aide, les mêmes informations sont
        rappelées par des pastilles : <span class="aide-prof modif">vert</span> = peut modifier,
        <span class="aide-prof">gris</span> = consulte ; la pastille entourée est la vôtre.</p>
        ${_aideTableAcces()}
        ${_aWarn(`« modifier » ne veut pas toujours dire « tout modifier » : un enseignant ne modifie que le contenu, les
            contraintes et les notes de <b>ses</b> matières, et les fiches de suivi des étudiants <b>dont il est tuteur</b>.
            Le serveur vérifie ces règles à chaque enregistrement.`)}` },

    { id: 'annees', rub: R, titre: 'Les années universitaires', mots: 'année active année du service année de la cohorte 2026-2027 changer d\'année',
      html: () => `
        <p>Le site garde une base par année universitaire (2025-2026, 2026-2027…). Ces réglages disent laquelle vous regardez :</p>
        <table><thead><tr><th>Réglage</th><th>Où</th><th>Ce qu'il change</th></tr></thead><tbody>
            <tr><td><b>Année active</b></td><td>Réglée par le superadmin${_aSi('nav:parametres', ` (${_aOng('Paramètres')})`)}</td><td>L'année de travail du site, l'année « en cours » : c'est elle qu'ouvrent les onglets qui n'ont pas leur propre sélecteur.</td></tr>
            ${_aSi('nav:service', `<tr><td><b>Année du Service</b></td><td>Liste ${_aUi('Année')} à droite de la barre du ${_aOng('Service')}</td><td>Seulement les vues du Service. Elle permet de consulter ou de préparer une autre année <b>sans rien changer pour les autres</b>. Elle part de l'année active.</td></tr>`)}
            ${_aSi('nav:promotions', `<tr><td><b>Année de la cohorte</b></td><td>${_aOng('Promotions')}</td><td>Une promotion vit trois ans : on choisit son année d'étude (1, 2 ou 3), affichée avec l'année universitaire correspondante.</td></tr>`)}
            ${_aSi(['nav:stages', 'nav:alternance'], `<tr><td><b>Année universitaire</b></td><td>${_aSi('nav:stages', _aOng('Stages'))} ${_aSi('nav:alternance', _aOng('Alternance'))}</td><td>Les fiches de suivi d'une année.</td></tr>`)}
        </tbody></table>
        ${_aSi(['nav:service', 'nav:promotions'], _aEx('en 2026-2027', `
            ${_aSi('nav:promotions', `<p>La promotion <b>26-29</b> est en 1<sup>re</sup> année (BUT1), <b>25-28</b> en BUT2, <b>24-27</b> en BUT3.
                Dans le sélecteur des promotions, « 25-28 · BUT2 (26/30) » se lit : cohorte 25-28, en 2<sup>e</sup> année cette année,
                26 étudiants actifs sur 30 fiches.</p>`)}
            ${_aSi('nav:service', `<p>Pour consulter ou préparer 2027-2028 sans gêner personne : ${_aOng('Service')}, liste ${_aUi('Année')} → 2027-2028.</p>`)}`))}
        ${_aSi('promo:calendrier', _aTip(`le calendrier d'une cohorte s'écrit dans la base de <b>son</b> année (un bandeau le signale quand elle diffère de l'année active).`))}` },

    { id: 'enregistrer', rub: R, titre: 'Enregistrer ses modifications', mots: 'sauvegarder enregistrer perdu modifications non enregistrées quitter brouillon',
      html: () => {
        // Les grilles à bouton « Enregistrer » où la session peut écrire
        const grilles = [
            [['nav:saisie', 'promo:saisie'], _aOng('Saisie Notes')], ['promo:notes', _aOng('Bulletins')], ['promo:jury', _aOng('Jury')],
            ['promo:groupes', 'le nombre de groupes'], ['promo:calendrier', `le ${_aOng('Calendrier')}`],
            [['prog:coeff', 'prog:matieres'], `le ${_aOng('Programme')}`],
            ['rep:annuelle', `la ${_aOng('Répartition annuelle')} (qui travaille sur un brouillon, avec retour arrière)`],
        ].map(([k, t]) => _aSiModif(k, t)).filter(Boolean);
        const imports = ['promo:effectif', 'promo:notes', 'promo:groupes', 'etu:liste', 'rep:annuelle', 'nav:saisie', 'promo:saisie'];
        return `
        <p>Le site enregistre de deux façons.</p>
        <h3>Enregistrement immédiat</h3>
        <p>La plupart des champs s'enregistrent <b>dès qu'on les quitte</b>, ou avec le bouton ${_aUi('Enregistrer')} placé juste à côté.
        Un message vert confirme (« Enregistré »), un message rouge dit pourquoi c'est refusé.</p>
        ${grilles.length ? `<h3>Grilles avec bouton « Enregistrer »</h3>
        <p>Les grandes grilles se remplissent d'abord, puis s'enregistrent d'un bloc : ${grilles.join(', ')}.</p>
        <p>Si vous quittez une de ces grilles sans enregistrer (autre onglet, autre page, déconnexion), le site demande quoi faire :</p>
        <ul>
            <li>${_aUi('Rester ici')} — on revient à la grille, rien n'est perdu ;</li>
            <li>${_aUi('Quitter sans enregistrer')} — les saisies sont abandonnées ;</li>
            <li>${_aUi('Enregistrer et quitter')} — on enregistre, puis on part (une valeur invalide annule le départ).</li>
        </ul>
        ${_aWarn(`fermer l'onglet du navigateur ou recharger la page avec des modifications en attente déclenche l'alerte du navigateur :
            il ne peut proposer que « rester » ou « quitter ». Enregistrez avant.`)}` : ''}
        ${_aSiModif(imports, `<h3>Imports : toujours un aperçu d'abord</h3>
        <p>Les imports de fichiers commencent par une <b>analyse</b> qui dit ce qui changerait. Rien n'est écrit avant votre confirmation.</p>`)}`;
      } },

    { id: 'interface', rub: R, titre: "Repères d'interface", mots: 'tri colonne infobulle filtre export import couleur pastille raccourci clavier',
      html: () => `
        <ul>
            <li><b>Onglets et sous-onglets</b> : la barre du haut, puis une ligne de sous-onglets propre à chaque page.${_aSi('nav:service', ` Le ${_aOng('Service')} a sa propre barre grise.`)}</li>
            <li><b>Infobulles</b> : survolez un en-tête de colonne, une pastille ou un bouton — presque tout est expliqué au survol.</li>
            <li><b>Tri</b> : un clic sur un en-tête de colonne trie le tableau (▲/▼), un second clic inverse l'ordre.</li>
            <li><b>Filtres</b> : ils ne changent que l'affichage, jamais les données. Un bouton ${_aUi('Réinitialiser')} les efface.</li>
            <li><b>Recherche</b> : sans tenir compte des accents ni des majuscules ; plusieurs mots se cherchent ensemble (« dup lea » trouve DUPONT Léa).</li>
            <li><b>Exports</b> ${_aUi('⤓')} : ce qui est affiché (filtres compris) part en Excel, CSV ou PDF. <b>Imports</b> ${_aUi('⤒')} : toujours avec aperçu.</li>
            <li><b>Cases grisées</b> : consultation seule — votre session voit l'écran sans pouvoir y modifier.</li>
            <li><b>Couleurs</b> : vert = acquis / validé / enregistré, orange = à vérifier / provisoire, rouge = problème / non acquis.</li>
        </ul>
        <h3>Raccourcis clavier</h3>
        <table><tbody>
            ${_aSiModif('rep:annuelle', `<tr><td><kbd>Ctrl</kbd> + <kbd>S</kbd></td><td>Enregistrer la répartition annuelle</td></tr>
            <tr><td><kbd>Ctrl</kbd> + <kbd>Z</kbd></td><td>Retour arrière dans la répartition annuelle</td></tr>
            <tr><td><kbd>Ctrl</kbd> + <kbd>Y</kbd> (ou <kbd>Ctrl</kbd> + <kbd>Maj</kbd> + <kbd>Z</kbd>)</td><td>Rétablir</td></tr>`)}
            <tr><td><kbd>Entrée</kbd></td><td>Valider la connexion${_aSiModif('promo:notes', ", l'éditeur de pénalité")}…</td></tr>
        </tbody></table>` },
    ];
}

function _aideService() {
    const R = 'service';
    return [
    { id: 'service-vue', rub: R, titre: "L'onglet Service", chemin: 'Service', onglet: 'nav:service',
      mots: 'service enseignant edt emploi du temps sous-onglets année',
      html: () => `
        <p>Le ${_aOng('Service')} regroupe tout ce qui touche aux heures d'enseignement et à l'emploi du temps. Il a sa propre
        barre grise de sous-onglets :</p>
        <table><tbody>${_aLignes([
            ['svc:repartition-enseignant', _aUi('Bilan Global'), `Le service de chaque enseignant, en heures et en HETD. ${_aLien('bilan', 'Voir')}`],
            ['svc:repartition', _aUi('Répartition Calendaire'), `Les heures de chaque matière placées semaine par semaine${
                _aSi('rep:jour', ", et ce qu'il reste à poser semaine après semaine (vue journalière)")}. ${_aLien('rep-annuelle', 'Voir')}`],
            ['svc:matieres', _aUi('Matières'), `Les matières de l'année : volumes, durées de séance, salles, enseignants, référents. ${_aLien('matieres', 'Voir')}`],
            ['svc:contraintes', _aUi('Contraintes Enseignant'), `Les indisponibilités et préférences de chacun. ${_aLien('contraintes', 'Voir')}`],
            ['svc:contraintes-matiere', _aUi('Contraintes Matière'), `Les contraintes propres à une matière (salle, ordre, période). ${_aLien('contraintes-matiere', 'Voir')}`],
            ['svc:comparaison', _aUi('Comparaison'), `Confronter un export Hyperplanning aux heures saisies ici. ${_aLien('comparaison', 'Voir')}`],
        ])}</tbody></table>
        <p>À droite de la barre, la liste ${_aUi('Année')} choisit l'année universitaire <b>affichée dans le Service seulement</b> :
        on peut consulter l'année passée ou préparer la suivante sans rien changer aux autres onglets
        (${_aLien('annees', 'les années')}).</p>
        ${_aTip(`un enseignant arrive sur son ${_aUi('Bilan Global')}, l'administration sur la ${_aUi('Répartition Calendaire')}.`)}` },

    { id: 'bilan', rub: R, titre: 'Bilan Global (service des enseignants)', chemin: 'Service › Bilan Global',
      onglet: 'svc:repartition-enseignant', cible: 'repartition-enseignant',
      mots: 'service hetd heures complémentaires sous-service heures brutes pondérées qr code appel corps mcf prag prce plp vacataire titulaire',
      html: () => `
        <p>Le service de chaque enseignant, matière par matière : pour chaque CM, TD, TP ou PT qu'il assure, les heures,
        le nombre de groupes et la conversion en <b>HETD</b> (heures équivalent TD).</p>
        <h3>Lire une ligne</h3>
        <table><thead><tr><th>Colonne</th><th>Signification</th></tr></thead><tbody>
            <tr><td>H. brutes</td><td>Le volume de la séance pour <b>un</b> groupe (ex. 30 h de TD).</td></tr>
            <tr><td>× groupes</td><td>Le nombre de groupes que l'enseignant assure (${_aSi('promo:groupes', `réglé dans ${_aOng('Promotions › Groupes')}`)
                || 'réglé par l\'administration pour chaque semestre'} ; un CM compte 1). Un point violet signale une matière partagée : chaque enseignant n'est compté que pour <b>ses</b> groupes.</td></tr>
            <tr><td>H. pondérées</td><td>H. brutes × groupes : les heures réellement faites.</td></tr>
            <tr><td>Coef.</td><td>Le coefficient HETD du type, réglé par le superadmin : par défaut CM 1,5 · TD 1 · TP 0,667 · PT 1.</td></tr>
            <tr><td>HETD</td><td>H. pondérées × coefficient.</td></tr>
        </tbody></table>
        ${_aEx('le calcul', `<div class="aide-maquette"><table><thead><tr><th>Séance</th><th>H. brutes</th><th>Groupes</th><th>H. pondérées</th><th>Coef.</th><th>HETD</th></tr></thead><tbody>
            <tr><td><span class="badge badge-cm">CM</span> R1.04</td><td>15 h</td><td>× 1</td><td>15 h</td><td>1,50</td><td><b>22,50</b></td></tr>
            <tr><td><span class="badge badge-td">TD</span> R1.04</td><td>20 h</td><td>× 3</td><td>60 h</td><td>1,00</td><td><b>60,00</b></td></tr>
            <tr><td><span class="badge badge-tp">TP12</span> R1.04</td><td>12 h</td><td>× 4</td><td>48 h</td><td>0,67</td><td><b>32,02</b></td></tr>
            </tbody></table></div><p>Soit 114,52 HETD pour cette matière.</p>`)}
        <h3>Heures complémentaires</h3>
        <p>Pour un titulaire dont le corps est renseigné, le bilan compare le total d'HETD au service statutaire :
        <b>192 HETD</b> pour un MCF, <b>384 HETD</b> pour un PRAG, PRCE ou PLP. Au-delà : heures complémentaires ;
        en dessous : sous-service. Les heures déclarées <b>hors GIM</b> (${_aLien('mon-compte', 'Mon Compte')}) s'y ajoutent.</p>
        <h3>Filtres</h3>
        <p>${_aUi('Enseignant')}, ${_aUi('Année')} (1A, 2A, 3A), ${_aUi('Formation')} (FTP, ALT, MUT = mutualisé) et une recherche par matière.
        Un enseignant connecté trouve son nom présélectionné ; pour un vacataire, la liste reste sur son nom.</p>
        <h3>Appel par QR code</h3>
        <p>La colonne ${_aUi('Appel QR')} : chaque enseignant coche, sur la ligne de bilan d'une sous-matière, s'il y fait l'appel
        par QR code — un seul choix pour tous ses CM, TD, TP et PT de cette sous-matière. L'administration voit ces choix
        sans pouvoir les modifier.</p>
        ${_aWarn(`qui voit quoi : un enseignant voit ses heures complémentaires et toutes ses heures hors GIM ; l'administration voit
            les heures complémentaires de chacun et seulement les heures hors GIM déclarées <b>publiques</b>.`)}` },

    { id: 'rep-annuelle', rub: R, titre: 'Répartition annuelle (heures par semaine)', chemin: 'Service › Répartition Calendaire › Répartition annuelle',
      onglet: 'rep:annuelle', cible: 'repartition/annuelle',
      mots: 'répartition calendaire planning semaine placer heures reste h module brouillon retour arrière taux horaire vacances orange',
      html: () => `
        <p>Le tableau de bord de l'emploi du temps : pour chaque matière, chaque type d'enseignement et chaque groupe, les heures
        placées sur chacune des semaines de l'année.</p>
        <h3>Afficher</h3>
        <p>Rien ne s'affiche tant qu'aucun semestre n'est choisi : cliquez sur ${_aUi('S1')} … ${_aUi('S6')} (plusieurs à la fois si besoin).
        Puis affinez avec ${_aUi('Type')} (CM, TD, TP, PT), ${_aUi('Formation')}, ${_aUi('Enseignant')}, ${_aUi('Salle')}, la recherche de matière,
        et les cases ${_aUi('Impair')} / ${_aUi('Pair')} (semaines du semestre impair ou pair).</p>
        <h3>Lire le tableau</h3>
        <ul>
            <li>Une ligne bleue par <b>matière</b>, puis une ligne par formation (MUT, FTP, ALT) et par type ; les TP partagés en groupes portent leur numéro (gr.1, gr.2… ; ALT pour les groupes d'apprentis).</li>
            <li>${_aUi('H. module')} : le volume à placer ; ${_aUi('Reste')} : ce qu'il reste à placer, <b>en rouge tant qu'il n'est pas à zéro</b>. Le reste compte toutes les semaines, même celles qu'un filtre masque.</li>
            <li>Les semaines <b style="color:#c2410c">orange</b> sont des semaines de vacances, de stage (FTP) ou d'entreprise (ALT), d'après le ${_aLien('promo-calendrier', 'calendrier')} de la promotion.</li>
            <li>En haut, les <b>taux horaires</b> (FTP1, ALT1… FTP3, ALT3) donnent les heures de cours d'un étudiant de chaque promo, semaine par semaine. Filtré sur un enseignant ou une salle, le tableau ajoute sa charge hebdomadaire.</li>
            <li>La ligne des <b>commentaires</b> de semaine (écrits dans le calendrier) s'affiche au-dessus des semaines.</li>
        </ul>
        ${_aSiModif('rep:annuelle', `<h3>Placer des heures</h3>
        ${_aSteps([
            'Cliquez sur la case d\'une semaine : deux flèches apparaissent.',
            `${_aUi('▲')} ajoute une séance (la durée de séance de la matière, ex. 1,5 h), ${_aUi('▼')} en retire une.`,
            `Le ${_aUi('Reste')}, les taux horaires et les totaux suivent aussitôt ; la case modifiée est encadrée en orange.`,
            `Quand tout est bon : ${_aUi('Enregistrer')} (ou <kbd>Ctrl</kbd>+<kbd>S</kbd>).`])}
        <div class="aide-maquette"><table><thead><tr><th>Matière</th><th>Type</th><th>S37</th><th>S38</th><th>S39</th><th>S40</th><th>H. module</th><th>Reste</th></tr></thead><tbody>
            <tr><td><b>R1.04</b> FTP</td><td><span class="badge badge-td">TD</span></td><td style="text-align:center">1,5</td><td style="text-align:center;box-shadow:inset 0 0 0 2px #b45309;font-weight:700">3</td><td style="text-align:center">1,5</td><td style="text-align:center;background:#fdba74"></td><td style="text-align:center">21</td><td style="text-align:center;color:#dc2626;font-weight:700">15</td></tr>
        </tbody></table>
        <p style="font-size:.8rem;color:#6b7280;margin:6px 0 0">S38 vient de passer à 3 h (deux séances), case encadrée = pas encore enregistrée ; S40 est une semaine de vacances ; il reste 15 h à placer.</p></div>
        <h3>Le brouillon : rien n'est enregistré sans vous</h3>
        <p>Les clics modifient une <b>copie de travail</b> : la barre au-dessus du tableau compte les modifications en attente.
        ${_aUi('↶ Retour arrière')} (<kbd>Ctrl</kbd>+<kbd>Z</kbd>) et ${_aUi('↷ Rétablir')} (<kbd>Ctrl</kbd>+<kbd>Y</kbd>) défont et refont clic par clic ;
        ${_aUi('Abandonner')} revient à la version enregistrée. Le brouillon survit au changement de semestres affichés ; quitter l'onglet
        ou l'année demande quoi en faire.</p>`)}
        <h3>Outils de la barre</h3>
        <ul>
            ${_aSiModif('rep:annuelle', `<li>${_aUi('Contrôle')} : un panneau à droite liste la <b>charge des enseignants par semaine</b> (orange au-delà de 20 h, rouge au-delà de 30 h) et les <b>conflits de salle</b> (plus de 2 matières la même semaine). Le brouillon est compris dans le contrôle.</li>
            <li>${_aUi('Ordonnancement')} : des règles d'ordre entre matières (« R1.01 avant R1.05, avec au moins 2 semaines d'écart »), à respecter dans le placement.</li>`)}
            <li>${_aUi('Export Excel')} : exactement ce qui est affiché (semestres, formation, enseignant)${_aSiModif('rep:annuelle', ', brouillon compris')}.</li>
            ${_aSiModif('rep:annuelle', `<li>${_aUi('Import Excel')} : recharge des heures depuis un fichier au format de l'export — elles <b>remplacent</b> les heures existantes, après confirmation.</li>`)}
            <li>${_aUi('Taux horaires')} : la case masque les lignes de taux pour gagner de la place.</li>
        </ul>
        ${_aTip(`les vacataires ne voient ni les taux horaires ni l'export.`)}` },

    { id: 'rep-jour', rub: R, titre: 'Répartition journalière (semaine par semaine)', chemin: 'Service › Répartition Calendaire › Répartition journalière',
      onglet: 'rep:jour', cible: 'repartition/jour',
      mots: 'journalière semaine posée optimisée hyperplanning avancement cohorte mut reste à poser',
      html: `
        <p>La vue de travail pour construire l'emploi du temps <b>semaine après semaine</b> : pour une année d'étude, une cohorte et une
        semaine, tous les cours à placer, et le suivi de ce qui a déjà été fait.</p>
        <h3>Choisir</h3>
        <ul>
            <li>${_aUi('Année')} : 1<sup>re</sup> (S1/S2), 2<sup>e</sup> (S3/S4) ou 3<sup>e</sup> (S5/S6) année ;</li>
            <li>${_aUi('Cohorte')} : FTP, ALT, ou <b>MUT</b> (FTP + ALT ensemble — proposé d'office quand tous les cours de la semaine sont mutualisés) ;</li>
            <li>${_aUi('Semaine')} : la liste ne propose que les semaines où la cohorte a cours (ni vacances, ni stage, ni entreprise). La semaine en cours est présélectionnée.</li>
        </ul>
        <h3>Le tableau</h3>
        <p>Les cours sont rangés par matière, puis sous-matière (R1.03a, R1.03b…), type d'enseignement et, pour les TP, groupe par groupe
        (TP12_1, TP12_2, TP12_ALT…). Chaque niveau se replie ; ${_aUi('Tout replier')} / ${_aUi('Tout déplier')} agissent sur l'ensemble. Un clic sur
        un en-tête trie ; les listes ${_aUi('Enseignant')} et ${_aUi('Salle')} filtrent.</p>
        <h3>Suivre l'avancement</h3>
        <p>Deux cases, pour la semaine et la cohorte affichées :</p>
        <ul>
            <li>${_aUi('Posée à l\'EDT')} : les cours de la semaine sont déposés dans l'emploi du temps, sans être encore organisés ;</li>
            <li>${_aUi('Optimisée')} : le placement est fait, contraintes respectées. Une semaine optimisée est forcément posée.</li>
        </ul>
        <p>La liste des semaines porte ✓ (posée) et ✓✓ (optimisée), et un bandeau compte les semaines faites, avec les semaines
        <b>restant à poser</b> ou <b>à optimiser</b> en pastilles cliquables. Cocher FTP ne coche ni ALT ni MUT : chaque cohorte a son suivi.</p>
        ${_aEx('construire le S1', `Année 1, cohorte FTP, semaine 37 : on dépose les cours dans Hyperplanning, on coche ${_aUi('Posée à l\'EDT')} ;
            une fois les placements arrangés, ${_aUi('Optimisée')}. Le bandeau indique alors « reste à poser : S38, S39… » — un clic sur S38 y mène.`)}
        ${_aWarn(`la vue journalière lit la répartition <b>enregistrée</b> : un brouillon en cours dans la vue annuelle est à enregistrer ou abandonner avant.`)}` },

    { id: 'matieres', rub: R, titre: 'Matières (volumes, séances, enseignants)', chemin: 'Service › Matières',
      onglet: 'svc:matieres', cible: 'matieres',
      mots: 'matière sous-matière cours volume horaire durée séance salle enseignant référent mutualisé tp12 tp8 groupe hetd pn semaine début fin',
      html: `
        <p>La liste des matières de l'année affichée, semestre par semestre, rangées sous leur matière du programme national.
        C'est ici qu'on dit <b>combien d'heures</b>, <b>par séances de combien</b>, <b>dans quelle salle</b> et <b>avec qui</b>.</p>
        <h3>Le tableau</h3>
        <ul>
            <li>À gauche, la <b>matière générale</b> (celle du programme), puis ses <b>sous-matières</b> (R1.03 → R1.03a, R1.03b…), chacune avec ses lignes CM, TD, TP, PT.</li>
            <li>Les heures se lisent en colonnes : <b>PN</b> (volume du programme), <b>FTP</b>, <b>ALT</b> — un cours <b>mutualisé</b> (CM/TD communs) n'a qu'une case FTP+ALT. Une colonne récapitule total et HETD.</li>
            <li>${_aUi('Référent')} : un par face (FTP / ALT) et par matière. Il est présélectionné quand un seul titulaire intervient ; sinon la case est vide (bordure rouge) et se choisit parmi les intervenants. Le référent fixe les pondérations des sous-matières dans la ${_aLien('promo-saisie', 'saisie des notes')}.</li>
            <li>Filtres : semestres, formation, enseignant, salle, recherche.</li>
        </ul>
        <h3>Créer ou modifier une sous-matière</h3>
        <p>${_aUi('+ sous-matière')} sur une matière du programme crée R1.03a, R1.03b… ; ${_aUi('✎')} ouvre la fiche d'une sous-matière,
        ${_aUi('🗑')} la supprime. La fiche :</p>
        <ul>
            <li><b>Code</b>, <b>intitulé</b>, <b>type</b> (Ressource ou SAÉ), <b>type de TP</b> (TP12 = groupes de 12, TP8 = groupes de 8 : il fixe le nombre de groupes de TP) ;</li>
            <li><b>Semestre</b>, semaines de <b>début</b> et de <b>fin</b> — ou la case « dates par défaut du semestre », qui suit le calendrier ;</li>
            <li><b>Mutualisé</b> : CM et TD communs à FTP et ALT ; seuls TP et PT restent propres à chaque face ;</li>
            <li>Par type et par face : <b>total d'heures</b>, <b>durée de séance</b>, <b>séances par semaine</b>, <b>salle</b>, <b>enseignant</b>. Le bouton ${_aUi('👥')} confie chaque groupe à un enseignant différent (groupe vide = l'enseignant de la ligne) ;</li>
            <li>${_aUi('Copier FTP → ALT')} / ${_aUi('Copier ALT → FTP')} recopient les volumes d'une face sur l'autre.</li>
        </ul>
        <p>Le bouton ${_aUi('📅')} d'une matière ouvre sa <b>répartition hebdomadaire</b>, semaine par semaine, FTP et ALT.</p>
        ${_aEx('une ressource partagée', `R1.04 « Mécanique » : CM 15 h (séances de 1,5 h) mutualisé, TD 20 h en 3 groupes dont le groupe 3 confié à
            un autre enseignant (${_aUi('👥')}), TP12 12 h. Le ${_aLien('bilan', 'Bilan Global')} compte alors 2 groupes de TD au premier enseignant et 1 au second.`)}
        ${_aTip(`le nombre de groupes ne se règle pas ici mais dans ${_aOng('Promotions › Groupes')} ; une matière n'apparaît pas dans le Service
            tant qu'elle n'est pas créée pour l'année affichée.`)}` },

    { id: 'contraintes', rub: R, titre: "Contraintes d'emploi du temps (enseignant)", chemin: 'Service › Contraintes Enseignant',
      onglet: 'svc:contraintes', cible: 'contraintes',
      mots: 'contraintes indisponibilité préférence fichier joint disponibilité',
      html: `
        <p>Chaque enseignant y indique ses <b>indisponibilités et préférences</b> pour l'année affichée dans le Service :</p>
        <ul>
            <li>un <b>texte libre</b> (${_aUi('Enregistrer le texte')}), par exemple « indisponible le lundi matin ; pas de cours après 17 h le mercredi » ;</li>
            <li>et/ou un <b>fichier joint</b> : PDF, Word, Excel, image… (10 Mo au plus), remplaçable et supprimable.</li>
        </ul>
        <p>L'administration et le responsable FTP voient les contraintes de <b>tous</b> les enseignants, avec leurs fichiers et la date
        de mise à jour ; un responsable voit d'abord les siennes, puis celles des autres.</p>
        ${_aTip(`pour donner ses contraintes de l'an prochain, choisissez d'abord l'année suivante dans la liste ${_aUi('Année')} du Service.`)}` },

    { id: 'contraintes-matiere', rub: R, titre: 'Contraintes par matière', chemin: 'Service › Contraintes Matière',
      onglet: 'svc:contraintes-matiere', cible: 'contraintes-matiere',
      mots: 'contrainte matière salle imposée ordre des séances période',
      html: `
        <p>Un texte par matière pour ce qui ne tient pas dans les volumes : <b>salle spécifique</b>, <b>ordre des séances</b>,
        <b>période imposée</b>… (« TP en salle B12 uniquement ; CM avant les TP ; à placer avant la semaine 45 »).</p>
        <p>Chaque matière a son bouton ${_aUi('Enregistrer')}. Un enseignant ne voit et ne modifie que les matières <b>où il intervient</b> ;
        l'administration et le responsable FTP les renseignent toutes. Filtres : semestres et recherche.</p>` },

    { id: 'comparaison', rub: R, titre: 'Comparaison avec Hyperplanning', chemin: 'Service › Comparaison',
      onglet: 'svc:comparaison', cible: 'comparaison',
      mots: 'hyperplanning état récapitulatif export écart comparer maquette dispensées',
      html: `
        <p>Pour vérifier que l'emploi du temps réel correspond à ce qui est prévu ici : on dépose l'<b>état récapitulatif</b> exporté
        d'Hyperplanning, et le site confronte ses heures à celles saisies, matière par matière et enseignant par enseignant.
        <b>Rien n'est enregistré</b> : l'écran ne fait que montrer les écarts.</p>
        ${_aSteps([
            `Dans Hyperplanning : <code>Imports/Exports › TXT/CSV/XML/SQL › Exporter un fichier texte</code>, colonnes d'origine conservées (TXT, CSV ou Excel acceptés).`,
            `Choisissez le ${_aUi('Fichier')}, l'${_aUi('Année comparée')}, la ${_aUi('Face')} (FTP / ALT — déduite du nom du fichier par défaut) et, si besoin, les ${_aUi('Semestres')}.`,
            `${_aUi('Heures comparées')} : <b>Maquette</b> (une fois, comme l'état récapitulatif) ou <b>Dispensées</b> (multipliées par le nombre de groupes).`,
            `${_aUi('Comparer')} : chaque matière montre trois lignes empilées — Hyperplanning, planifié ici, écart.`])}
        ${_aTip(`ce que le fichier contient sans que la maquette le connaisse est listé à part : souvent une matière mal codée d'un côté ou de l'autre.`)}` },
    ];
}

function _aidePromotions() {
    const R = 'promotions';
    return [
    { id: 'promo-vue', rub: R, titre: 'Promotions : principes', chemin: 'Promotions', onglet: 'nav:promotions',
      mots: 'promotion cohorte sous-cohorte ftp alt année de la cohorte sélecteur programme affecté',
      html: () => `
        <p>Une <b>promotion</b> est une <b>cohorte</b> d'étudiants entrés la même année, suivie sur ses trois années de BUT.
        Elle porte le nom de ses années : <b>26-29</b> pour la cohorte entrée en septembre 2026. Elle contient deux
        <b>sous-cohortes</b> : <b>FTP</b> (formation à temps plein) et <b>ALT</b> (alternance).</p>
        <h3>Le sélecteur de promotion</h3>
        <p>En haut à droite : « <b>26-29 · BUT1 (52/57)</b> » se lit : la cohorte 26-29, en 1<sup>re</sup> année cette année
        universitaire, 52 étudiants actifs sur 57 fiches (toutes années et tous statuts). Une cohorte terminée est marquée OLD, une cohorte
        pas encore commencée À VENIR.</p>
        <h3>Les sous-onglets</h3>
        <table><tbody>${_aLignes([
            ['promo:effectif', _aUi('Effectifs'), `Les étudiants de chaque année d'étude, leur statut, leur profil. ${_aLien('promo-effectifs', 'Voir')}`],
            ['promo:groupes', _aUi('Groupes'), `Le nombre de groupes par semestre et la répartition des étudiants. ${_aLien('promo-groupes', 'Voir')}`],
            ['promo:calendrier', _aUi('Calendrier'), `Dates des semestres, vacances, stages, semaines en entreprise. ${_aLien('promo-calendrier', 'Voir')}`],
            [['promo:saisie', 'nav:saisie'], _aUi('Saisie Notes'), `Les notes par sous-matière, saisies par les enseignants${
                _aSi('nav:saisie', ` — pour vous, dans l'onglet ${_aOng('Saisie Notes')} de la barre principale`)}. ${_aLien('promo-saisie', 'Voir')}`],
            ['promo:notes', _aUi('Bulletins'), `Les notes des matières et les moyennes d'UE, semestre par semestre. ${_aLien('promo-bulletins', 'Voir')}`],
            ['promo:jury', _aUi('Jury'), `Les codes d'UE et la décision d'année. ${_aLien('promo-jury', 'Voir')}`],
            ['promo:devenir', _aUi('Devenir'), `Ce que devient chaque étudiant après le jury. ${_aLien('promo-devenir', 'Voir')}`],
            ['promo:actions', _aUi('Actions'), `Créer ou supprimer une promotion. ${_aLien('promo-actions', 'Voir')}`],
        ])}</tbody></table>
        <p>Plusieurs sous-onglets ont une liste ${_aUi('Année de la cohorte')} : année 1, 2 ou 3, chacune affichée avec son année universitaire
        (année 2 de 26-29 = 2027-2028). À l'ouverture, c'est l'année que la cohorte suit en ce moment.</p>
        ${_aSi('promo:effectif', `<p>En tête des Effectifs, la liste ${_aUi('Programme')} rattache la promotion à un ${_aLien('prog-vue', 'programme national')} : c'est lui qui
        fixe ses matières, ses UE et ses coefficients.</p>`)}` },

    { id: 'promo-effectifs', rub: R, titre: 'Effectifs', chemin: 'Promotions › Effectifs',
      onglet: 'promo:effectif', cible: 'promotions/effectif',
      mots: 'effectif étudiants liste statut actif abandon semaine abandon retirer supprimer fiche réintégrer bascule ftp alt mobilité internationale mi profil sexe recrutement scolarité antérieure autres fiches report jury',
      html: () => `
        <p>L'effectif d'une promotion <b>pour une année d'étude</b>, en deux sections : <b>FTP — formation initiale</b> et
        <b>ALT — alternance</b>. Chaque section affiche ses compteurs par statut (${_aStatut('Actif')} ${_aStatut('RED')}
        ${_aStatut('Césure')} ${_aStatut('Abandon')}) et son total.</p>
        <h3>Un effectif qui se compose tout seul</h3>
        <p>L'année 1 contient les étudiants inscrits à l'entrée. Les années suivantes se déduisent du jury : un étudiant passe en
        année 2 s'il n'est ni ajourné (${_aDec('AJ')}), ni redoublant (${_aDec('RED')}), ni parti.${_aSiModif('promo:effectif', ` On ajuste ensuite à la main
        (${_aUi('+ Étudiant')}, import, retrait). ${_aUi('↺ Reporter depuis le jury')} efface ces ajustements de l'année affichée et
        recalcule l'effectif à partir du jury.`)}</p>
        <h3>Les colonnes</h3>
        <ul>
            <li><b>Nom, prénom</b> : un clic ouvre la ${_aLien('etu-fiche', 'fiche de l\'étudiant')} ; <b>Apogée</b>, <b>naissance</b>.</li>
            <li><b>Sexe</b>, <b>Recrut.</b> (PS ParcourSup, EC eCandidat, ADIUT candidats étrangers, HP hors procédure) et la <b>scolarité antérieure</b>
                (pays, série de bac, années depuis le bac, études antérieures) : ce sont des données de <b>l'étudiant</b>, pas de l'année —
                elles valent pour toutes les cohortes où il est inscrit. Les colonnes grisées viennent de ParcourSup ;
                survolez une abréviation pour lire l'intitulé complet.</li>
            <li><b>MI</b> : <b>mobilité internationale</b> — le semestre passé dans un établissement partenaire${_aSiModif('promo:effectif',
                ' (choisissez le semestre, puis le nom de l\'établissement)')}. Les UE de ce semestre sont validées par équivalence, sans note.</li>
            ${_aSiModif('promo:effectif', `<li><b>Statut</b> : ${_aStatut('Actif')} ou ${_aStatut('Abandon')} (avec la <b>semaine</b> d'abandon). ${_aStatut('RED')} et ${_aStatut('Césure')}
                ne se choisissent pas ici : ils découlent du jury et du ${_aLien('promo-devenir', 'Devenir')}. Repasser en Actif quelqu'un que son devenir
                avait fait sortir annule ce devenir.</li>
            <li><b>Cohorte</b> : ${_aUi('⇄ ALT')} / ${_aUi('⇄ FTP')} bascule l'étudiant dans l'autre sous-cohorte <b>à partir de l'année affichée</b>
                (les années précédentes gardent la leur).</li>`) || `<li><b>Statut</b> : ${_aStatut('Actif')}, ${_aStatut('Abandon')} (avec la semaine d'abandon),
                ${_aStatut('RED')} ou ${_aStatut('Césure')}.</li>`}
        </ul>
        ${_aSiModif('promo:effectif', `<h3>Retirer ou supprimer : deux gestes différents</h3>
        <table><tbody>
            <tr><td>${_aUi('⊘')}</td><td><b>Retirer</b> de l'année affichée et des suivantes — celui qui ne poursuit pas. Ses années précédentes et leurs
                notes restent intactes, et il se <b>réintègre</b> (${_aUi('↩')}) depuis « Autres fiches de la cohorte ».</td></tr>
            <tr><td>${_aUi('🗑')}</td><td><b>Supprimer la fiche</b> de la cohorte : les trois années et toutes les notes, <b>sans retour</b>.</td></tr>
        </tbody></table>`)}
        <h3>Les pastilles à côté du nom</h3>
        <p>${_aCode('redoublant', 'background:#ddd6fe')} ou ${_aCode('reprise césure', 'background:#ddd6fe')} (venu d'une autre cohorte),
        ${_aCode('entrant', 'background:#ddd6fe')} (entré directement en année 2 ou 3), ${_aCode('ajouté', 'background:#dbeafe')} (ajout manuel),
        ${_aCode('MI S3', 'background:#cffafe')} (mobilité), ${_aCode('à compléter', 'background:#fef3c7')} (pas de dossier de candidature importé),
        et le devenir décidé : ${_aCode('→ année 2 FTP', 'background:#dcfce7')}, ${_aCode('RED · à décider', 'background:#fef3c7')}…</p>
        <h3>Sous les deux listes</h3>
        <ul>
            <li><b>Autres fiches de la cohorte</b> : celles qui ne sont pas dans l'effectif de l'année (entrants d'une année ultérieure, abandons, césures,
                retraits), avec la raison — pour qu'aucune fiche ne soit hors de portée. Les ajournés et redoublants n'y figurent pas : ils restent visibles
                sur l'année qu'ils ont faite.</li>
            ${_aSi('promo:devenir', `<li>Un rappel du nombre d'étudiants jugés et des devenirs à renseigner, avec ${_aUi('Onglet Devenir →')}.</li>`)}
        </ul>
        <h3>Les boutons du haut</h3>
        <p>${_aSiModif('promo:effectif', `${_aUi('⤒ Importer ParcourSup')} (${_aLien('promo-import', 'voir')}), `)}${_aUi('⤓ Exporter en Excel')} (un onglet par
        sous-cohorte, mêmes colonnes${_aSiModif('promo:effectif', ', réimportable')}), ${_aUi('⤓ Trombi (PDF)')} (${_aLien('etu-photos', 'trombinoscope de l\'année')})${
        _aSiModif('promo:effectif', ` et ${_aUi('↺ Reporter depuis le jury')}`)}.</p>
        ${_aTip(`le bandeau de couverture ParcourSup (« 7 sans dossier importé — afficher ») filtre les deux listes sur les étudiants dont le dossier reste à compléter.`)}` },

    { id: 'promo-import', rub: R, titre: "Importer un effectif ou ParcourSup", chemin: 'Promotions › Effectifs',
      onglet: 'promo:effectif', pour: 'modifier', cible: 'promotions/effectif',
      mots: 'import effectif pv de jury apogée tableur excel parcoursup classement dossier candidature csv sti2d xlsx xlsm',
      html: `
        <h3>Importer un effectif</h3>
        <p>Bouton ${_aUi('Importer un effectif')} en tête de la section FTP ou ALT : les étudiants du fichier arrivent dans <b>cette</b>
        sous-cohorte, pour l'année affichée. Fichiers acceptés (<code>.xlsx</code> / <code>.xlsm</code>) :</p>
        <ul>
            <li>un <b>PV de jury</b> (seules les feuilles « PV… », « Jury… » et « Temp » sont lues) ;</li>
            <li>un export <b>Apogée</b> ;</li>
            <li>tout tableur avec des en-têtes <i>Nom, Prénom, Numéro, Naissance</i> (et <i>Sexe</i> si vous l'avez), cherchés dans les premières lignes — l'export Excel de l'effectif, complété, se réimporte tel quel.</li>
        </ul>
        <p>Un étudiant déjà présent (même n° Apogée, ou mêmes nom, prénom et naissance) n'est <b>pas dupliqué</b> : son sexe est mis à jour si le fichier
        le donne, et une colonne vide n'efface jamais une saisie. Un étudiant rangé dans l'autre sous-cohorte est <b>recalé</b> du côté du fichier,
        pour l'année importée seulement ; les fiches déplacées sont listées à la fin.</p>
        ${_aEx('la rentrée', `Le PV de rentrée des BUT1 FTP (.xlsm) → ${_aOng('Effectifs')}, année 1, section FTP, ${_aUi('Importer un effectif')}.
            Les 48 étudiants sont créés en année 1 ; les années 2 et 3 se rempliront d'elles-mêmes au fil des jurys.`)}
        <h3>Importer ParcourSup</h3>
        <p>${_aUi('⤒ Importer ParcourSup')} complète les fiches <b>déjà dans l'effectif</b> avec leur dossier de candidature — il <b>ne crée aucune fiche</b>
        (le classement compte des centaines de candidats pour quelques dizaines d'inscrits) et rapproche par <b>nom et prénom</b>, le classement ne portant
        pas de n° Apogée.</p>
        <ul>
            <li>Le <b>classement</b> (<code>.xlsx</code>, export « dossier_AD_… ») : rang, n° ParcourSup, profil, scolarité, série, spécialités, spécialité abandonnée,
                spécialité Bac Pro, note globale.</li>
            <li>L'<b>export CSV complet</b> (« …_CLA_….csv ») ajoute le <b>dossier de candidature</b> détaillé : pays, ville du lycée, bac et mention, années post-bac,
                bulletins (notes et appréciations), bourse, sportif de haut niveau, artiste.</li>
        </ul>
        ${_aSteps([
            'Importez le classement <b>STI2D</b> ;',
            'lisez le compte rendu : il liste les inscrits restés sans dossier ;',
            'importez le classement <b>hors STI2D</b> : le compte rendu se réduit à ceux qui ne sont pas passés par ParcourSup (eCandidat, ADIUT…), à compléter à la main sur leur fiche.'])}
        ${_aTip(`la série de bac et le dossier ne s'importent plus avec l'effectif : uniquement par ParcourSup. Une note globale de 0 signale un dossier écarté par la commission, pas une note obtenue.`)}` },

    { id: 'promo-groupes', rub: R, titre: 'Groupes', chemin: 'Promotions › Groupes',
      onglet: 'promo:groupes', cible: 'promotions/groupes',
      mots: 'groupes td tp12 tp8 pt nombre de groupes mutualisé tp distincts apprentis répartition automatique vérifier règles covoiturage filles binôme télécharger importer reprendre semestre',
      html: () => `
        <h3>1. Le nombre de groupes</h3>
        <p>Pour l'année de la cohorte choisie, semestre par semestre : le nombre de groupes de <b>TD</b>, <b>TP12</b>, <b>TP8</b> et <b>PT</b>, pour FTP et pour ALT
        (le CM compte toujours 1). Ce réglage alimente le ${_aLien('bilan', 'Bilan Global')} (heures × groupes) et la répartition.${
        _aSiModif('promo:groupes', ` ${_aUi('Enregistrer')} après modification.`)}</p>
        <ul>
            <li><b>Mutualisé</b> : FTP et ALT suivent le semestre ensemble ; toutes ses matières passent en MUT et les groupes se définissent pour la promotion entière.</li>
            <li><b>TP distincts</b> (semestre mutualisé) : les TP gardent des lignes FTP et ALT séparées ; décoché, une seule ligne de TP commune à la promo.</li>
            <li><b>Apprentis</b> : dans des TP communs, le nombre de groupes d'alternants — ils occupent toujours les <b>derniers</b> groupes.</li>
        </ul>
        <h3>2. La répartition des étudiants</h3>
        <p>Pour un semestre : le groupe de chaque étudiant dans chaque <b>famille</b> (TD, TP12, TP8 ; TD SAÉ et TP12 SAÉ au S1 ; toute famille ajoutée, comme
        « Covoiturage » ou une langue). Un semestre mutualisé a un tableau pour la promo ; sinon FTP et ALT ont chacun le leur.</p>
        <ul>
            <li>Vue ${_aUi('Tableau')} (un étudiant par ligne, tri et filtres par colonne comme dans Excel) ou ${_aUi('Par groupe')} (la liste de chaque groupe, avec son effectif et son nombre de filles — une fille seule est signalée).</li>
            <li>${_aUi('⤓ Télécharger')} : un classeur Excel avec la liste complète et une feuille par famille de groupes.</li>
            ${_aSiModif('promo:groupes', `<li>On corrige une case directement : l'enregistrement est immédiat. Le projet tutoré suit le groupe de TD : son numéro se reprend tout seul.</li>
            <li>${_aUi('⚙ Répartition automatique')} : propose une répartition selon les règles du département —
                <b>emboîtement</b> (un TD de 24 étudiants contient 2 TP12 et 3 TP8 ; au-delà, il prend sur le TP suivant),
                <b>effectifs pairs</b> pour le travail en binôme (26 en 3 groupes : 10, 8, 8 plutôt que 9, 9, 8), <b>alternants</b> dans les derniers groupes
                (mélangés aux FTP ou dans des groupes dédiés), <b>filles</b> au moins par deux, membres d'un même <b>covoiturage</b> dans le même TP8
                (donc le même TP12 et le même TD). ${_aUi('Calculer l\'aperçu')}, vérifier, puis ${_aUi('Appliquer')} ; toute modification d'un réglage
                demande un nouvel aperçu.</li>
            <li>${_aUi('✓ Vérifier les règles')} : contrôle la répartition affichée (complétude, capacités des TP, chaque TP contenu dans un TD, alternants, SAÉ,
                filles, covoiturages, effectifs pairs, accord avec le nombre de groupes du service).</li>
            <li>${_aUi('⧉ Reprendre le S1')} (au semestre pair) : recopie la répartition du semestre impair, sans les groupes de SAÉ.</li>
            <li>${_aUi('⤒ Importer')} : un <code>.xlsx</code> avec <i>Nom</i>, <i>Prénom</i> et une colonne par famille (valeurs <code>TD_1</code>, <code>TP12_3</code>…) ;
                rapprochement par nom et prénom, aperçu avant écriture, une case vide retire de la famille.</li>`)}
        </ul>
        ${_aSiModif('promo:groupes', _aEx('le S1 d\'une promotion de 48 étudiants FTP', `Nombre de groupes : 2 TD, 4 TP12, 6 TP8. ${_aUi('⚙ Répartition automatique')} → aperçu :
            TD1 et TD2 de 24 ; TD1 = TP12_1 + TP12_2 (12 chacun) = TP8_1 + TP8_2 + TP8_3 (8 chacun), et de même pour TD2.
            ${_aUi('Appliquer')}, puis ${_aUi('✓ Vérifier les règles')}, et ${_aUi('⤓ Télécharger')} pour l'envoyer aux enseignants.`))}` },

    { id: 'promo-calendrier', rub: R, titre: 'Calendrier', chemin: 'Promotions › Calendrier',
      onglet: 'promo:calendrier', cible: 'promotions/calendrier',
      mots: 'calendrier vacances stages entreprise semaines dates semestres plage commentaires 52 53 semaines',
      html: () => `
        <p>Le calendrier d'une année de la cohorte, pour FTP ou pour ALT (liste ${_aUi('Cohorte')}).</p>
        <ul>
            <li><b>Dates des semestres</b> : début et fin des semestres impairs (S1/S3/S5) et pairs (S2/S4/S6) ; la fin de l'impair et le début du pair se suivent.</li>
            <li><b>Plage de l'année</b> : première et dernière semaine de cours, et le nombre de semaines de l'année civile (52 ou 53).</li>
            <li><b>Semaines spéciales</b> : ${_aSiModif('promo:calendrier', 'cliquez sur les semaines pour les ranger dans une catégorie — ')}<b>vacances</b>
                et <b>stages</b> pour FTP, <b>entreprise</b> pour ALT. Chaque catégorie a un <b>code</b> court, repris en tête de la répartition.</li>
            <li><b>Commentaires</b> : une note libre par semaine (« semaine de soutenances », « pont »…), pour les formations et les années cochées.</li>
        </ul>
        <p>${_aSiModif('promo:calendrier', `${_aUi('Enregistrer')} enregistre le tout. `)}Ces semaines apparaissent en <b style="color:#c2410c">orange</b> dans la
        ${_aLien('rep-annuelle', 'répartition annuelle')}${_aSi('rep:jour', ` et disparaissent de la liste des semaines de la ${_aLien('rep-jour', 'répartition journalière')}`)}.</p>
        ${_aSiModif('promo:calendrier', _aWarn(`le calendrier s'écrit dans la base de l'année universitaire <b>de la cohorte</b>, qui peut différer de l'année active : un bandeau jaune le signale.`))}` },

    { id: 'promo-saisie', rub: R, titre: 'Saisie des notes (enseignants)', chemin: 'Saisie Notes — ou Promotions › Saisie Notes',
      onglet: ['nav:saisie', 'promo:saisie'], cible: ['saisie', 'promotions/saisie'],
      mots: 'saisie notes sous-matière pondération référent provisoire définitif abi modèle vide importer moyenne pondérée note matière',
      html: () => `
        <p>Chaque enseignant saisit les notes des <b>sous-matières</b> qu'il assure. La <b>note de la matière</b> (celle des
        ${_aLien('promo-bulletins', 'Bulletins')}) est la <b>moyenne pondérée</b> de ses sous-notes.</p>
        <h3>Où saisir</h3>
        <ul>
            ${_aSi('nav:saisie', `<li>Onglet ${_aOng('Saisie Notes')} de la barre principale : <b>toutes</b> vos grilles de l'année à la suite (cohorte × semestre × sous-cohorte),
                repliables, filtrables par matière, semestre et sous-cohorte, avec un compteur de ce qui reste à saisir (« ✓ tout est saisi »).</li>`)}
            ${_aSi('promo:saisie', `<li>${_aOng('Promotions › Saisie Notes')} : une grille à la fois (promotion, semestre, sous-cohorte).</li>`)}
        </ul>
        <h3>La grille</h3>
        <ul>
            <li>Les étudiants en lignes ; en colonnes, les sous-matières regroupées par matière, puis <b>Moy.</b> (la moyenne pondérée).</li>
            <li>Vos colonnes sont modifiables ; celles des collègues se lisent sans pouvoir être changées.</li>
            <li>Une note de <b>0 à 20</b>, ou <b>ABI</b> (absence injustifiée, comptée 0). Une valeur invalide est signalée à l'enregistrement.</li>
            <li>Ligne des <b>pondérations</b> : fixée par le <b>référent</b> de la matière (${_aLien('matieres', 'Matières')}) ; 0 exclut une sous-matière de la moyenne.</li>
            <li>Case <b>définitif</b> en tête de colonne : décochée = notes ⏳ provisoires, cochée = ✓ définitives.</li>
        </ul>
        ${_aEx('une moyenne pondérée', `<div class="aide-maquette"><table><thead><tr><th>Étudiant</th><th>R1.01a · DS<br><small>pondération 2</small></th><th>R1.01b · TP<br><small>pondération 1</small></th><th>Moy. R1.01</th></tr></thead><tbody>
            <tr><td>DUPONT Léa</td><td style="text-align:center">12</td><td style="text-align:center">15</td><td style="text-align:center"><b>13,00</b></td></tr>
            <tr><td>MARTIN Hugo</td><td style="text-align:center">ABI</td><td style="text-align:center">14</td><td style="text-align:center"><b>4,67</b></td></tr>
            </tbody></table></div>(2 × 12 + 1 × 15) / 3 = 13 ; avec ABI, le DS compte 0 : (2 × 0 + 14) / 3 = 4,67.`)}
        <h3>Travailler sous Excel</h3>
        ${_aSteps([
            `${_aUi('⤓ Modèle vide')} : un fichier avec les étudiants en lignes et vos sous-matières en colonnes.`,
            'Remplissez-le sous Excel.',
            `${_aUi('⤒ Importer')} : la grille se remplit (vert = ajoutée, ambre = remplace une note différente) — <b>rien n'est enregistré</b> à ce stade.`,
            `Vérifiez, puis ${_aUi('💾 Enregistrer')}.`])}
        <h3>Quand la moyenne n'arrive pas dans les Bulletins</h3>
        <p>La moyenne n'est reportée que si la matière est en mode <b>🧮 calculée</b>. Si l'administration a importé ou saisi la note de la matière
        (mode <b>📥 importée</b>), votre moyenne s'affiche mais <b>n'est pas reportée</b> tant qu'elle ne rebascule pas la matière — l'infobulle de la colonne Moy. le dit.</p>
        ${_aWarn(`n'oubliez pas ${_aUi('💾 Enregistrer')} : changer de grille ou d'onglet avec des notes en attente déclenche la demande « Modifications non enregistrées ».`)}` },

    { id: 'promo-bulletins', rub: R, titre: 'Bulletins (notes et moyennes)', chemin: 'Promotions › Bulletins',
      onglet: 'promo:notes', cible: 'promotions/notes',
      mots: 'bulletins notes moyennes ue semestre acquise compensée bonus pénalité assiduité absences abi neutralisée n vaq validation acquis mobilité import apogée pv export supprimer origine calculée importée écart incomplète redoublant',
      html: () => `
        <p>Pour une sous-cohorte et un semestre : les notes de chaque matière, les moyennes d'UE du semestre et le bilan de l'année.
        C'est la grille de référence avant le jury.</p>
        <h3>Les colonnes</h3>
        <p>Cases ${_aUi('Colonnes')} pour afficher ou masquer chaque groupe : <b>Rappel années précédentes</b>, <b>Statut & bilan année</b>,
        <b>Semestre précédent</b>, <b>UE du semestre</b>, <b>Notes (matières)</b>. Un clic sur un en-tête trie (meilleure moyenne d'abord).</p>
        <p>Une UE se colore selon le règlement : ${_aCode('≥ 10 acquise', _UE_STYLE.ok)} · ${_aCode('compensée', _UE_STYLE.comp)}
        (moyenne annuelle de la compétence ≥ 10) · ${_aCode('non acquise', _UE_STYLE.ko)}. L'année est validée quand au moins 3 compétences le sont
        (${_aCode('OK', 'background:#16a34a;color:#fff')} ${_aCode('INC', 'background:#f59e0b;color:#fff')} incomplète ${_aCode('NOK', 'background:#dc2626;color:#fff')}).</p>
        <h3>D'où vient la note d'une matière ?</h3>
        <ul>
            <li><b>🧮 calculée</b> : moyenne pondérée de la ${_aLien('promo-saisie', 'saisie des enseignants')}, refaite à chaque enregistrement — la case n'est pas modifiable ici ;</li>
            <li><b>📥 importée</b> : note importée (Apogée, PV) ou saisie à la main ici ; le recalcul n'y touche jamais ;</li>
            <li><b>⚠</b> : écart entre la note affichée et la moyenne de la saisie.</li>
        </ul>
        <p>Le bandeau du haut liste les matières où une saisie enseignante existe, avec leur origine et leurs écarts${_aSiModif('promo:notes',
        " ; un clic y bascule une matière d'un mode à l'autre")}.</p>
        <h3>${_aSiModif('promo:notes', 'Saisir ici') || 'Ce que portent les cases'}</h3>
        <ul>
            <li>Une note de 0 à 20 ; <b>ABI</b> (absence injustifiée, comptée 0) ; <b>N</b> (matière neutralisée, faute d'enseignant : elle sort de la moyenne, comme une case vide mais pour une raison affichée).</li>
            <li><b>Pénalité d'assiduité</b>${_aSiModif('promo:notes', ` : un clic ouvre un éditeur qui accepte les <b>heures d'absence injustifiée</b> ou le <b>malus</b> voulu,
                et convertit l'un en l'autre`)}. Barème : rien jusqu'à 8 h, puis −0,05 point par heure de la 9<sup>e</sup> à la 18<sup>e</sup>, puis −0,1 point par heure.
                Le malus se retranche de <b>chaque UE du semestre</b>.</li>
            <li><b>Bonus</b> (sport, art…) : 0,05 point par point au-dessus de 10, plafonné à 0,5 ; il s'ajoute à la <b>moyenne annuelle</b> de chaque UE.</li>
            <li><b>VAQ</b> (validation par acquis) : l'UE sort du calcul de l'année pour ce semestre${_aSiModif('promo:notes',
                ` — un clic sur la cellule de moyenne de l'UE, avec confirmation ; enregistré aussitôt`)}.</li>
            <li>Un semestre en <b>mobilité internationale</b> (MI) n'a pas de notes : ses UE sont validées par équivalence.</li>
        </ul>
        ${_aEx('une pénalité', `20 h d'absence injustifiée → (18 − 8) × 0,05 + (20 − 18) × 0,1 = <b>0,7 point</b> retiré de chaque UE du semestre.
            Un bonus noté 16/20 → (16 − 10) × 0,05 = <b>0,3 point</b> ajouté à chaque moyenne annuelle d'UE.`)}
        ${_aSiModif('promo:notes', `<p>Ces recalculs s'affichent tout de suite ; ${_aUi('💾 Enregistrer les notes')} les enregistre, et le serveur refait le calcul qui fait foi.</p>`)}
        <h3>Avant de tenir un jury</h3>
        <p>Le bandeau <b>moyennes incomplètes</b> signale les moyennes d'UE calculées alors qu'il manque des notes : elles sont <b>provisoires</b>, et
        les matières le plus souvent manquantes sont citées en premier. Un redoublant garde, UE par UE, la meilleure des deux moyennes (repère ↺) —
        voir ${_aLien('promo-devenir', 'Devenir')}.</p>
        ${_aSiModif('promo:notes', `<h3>Les boutons</h3>
        <ul>
            <li>${_aUi('Importer les notes')} : fichier <b>Apogée</b> ou <b>PV de jury</b> (détecté), feuille à choisir si le classeur en a plusieurs ; rapprochement par
                n° Apogée ; bonus et pénalité convertis depuis les points du PV. Trois modes : <b>tout écraser</b> (les matières passent en 📥), <b>préserver</b> les matières
                dont la saisie enseignante est définitive, ou ne remplir que les <b>cases vides</b>. ${_aUi('🔎 Analyser le fichier')} d'abord, puis ${_aUi('Importer')}.</li>
            <li>${_aUi('⬇ Exporter (.xlsx)')} : les notes du semestre au format Apogée.</li>
            <li>${_aUi('🗑 Supprimer les notes')} : toutes celles du semestre pour la sous-cohorte ; le 🗑 d'une ligne ne vide que celles d'un étudiant.</li>
        </ul>`)}` },

    { id: 'promo-jury', rub: R, titre: 'Jury', chemin: 'Promotions › Jury',
      onglet: 'promo:jury', cible: 'promotions/jury',
      mots: 'jury décision adm admj ajac aj red cmp ue validée compensée passage redoublant ajourné ue terminale gim moyenne générale',
      html: () => `
        <p>Pour une sous-cohorte et une année : chaque UE avec ses deux moyennes de semestre, sa <b>moyenne annuelle</b> et son <b>code</b>,
        la moyenne générale de l'année (GIM1, GIM2, GIM3) et la <b>décision</b>.</p>
        <h3>Codes d'UE (sur la moyenne annuelle de l'UE)</h3>
        <table><tbody>
            <tr><td>${_aUe('ADM')}</td><td>Admis : moyenne annuelle ≥ 10.</td></tr>
            <tr><td>${_aUe('AJ')}</td><td>Ajourné : moyenne annuelle &lt; 10.</td></tr>
            <tr><td>${_aUe('ADMJ')}</td><td>Admis par décision du jury${_aSiModif('promo:jury', ' : un clic fait passer une UE de AJ à ADMJ (et inversement)')}.</td></tr>
            <tr><td>${_aUe('CMP')}</td><td>Validée parce que la même compétence est validée à un niveau supérieur.</td></tr>
        </tbody></table>
        <h3>Décision d'année</h3>
        <table><tbody>
            <tr><td>${_aDec('ADM')}</td><td>Toutes les UE validées sur les moyennes.</td></tr>
            <tr><td>${_aDec('ADMJ')}</td><td>Toutes les UE validées, grâce à au moins un ADMJ posé par le jury.</td></tr>
            <tr><td>${_aDec('AJAC')}</td><td>Ajourné mais autorisé à continuer (années 1 et 2) : au moins 3 UE validées, dont toutes les UE <b>terminales</b>
                (marquées *, sans niveau supérieur pour se rattraper).</td></tr>
            <tr><td>${_aDec('AJ')}</td><td>Ajourné.</td></tr>
            <tr><td>${_aDec('RED')}</td><td>Redoublant : posé par le jury sur un candidat ajourné.</td></tr>
        </tbody></table>
        <p>Les décisions se calculent seules à partir des notes ; le jury intervient avec les ADMJ et les RED${
            _aSiModif('promo:jury', `, puis ${_aUi('💾 Enregistrer les décisions')}`)}.</p>
        ${_aEx('en 2e année, avec une UE terminale (UE5 *)', `<ul style="margin:4px 0 0 18px">
            <li>UE1, UE2, UE4 et UE5 validées, UE3 à 8,7 : 4 UE validées, la terminale comprise → ${_aDec('AJAC')}.</li>
            <li>UE1 à UE4 validées, UE5 à 9,2 : 4 UE validées mais la terminale ne l'est pas → ${_aDec('AJ')}.
                Si le jury pose ${_aUe('ADMJ')} sur UE5, toutes les UE sont validées → ${_aDec('ADMJ')}.</li></ul>`)}
        <h3>Ce que la décision entraîne</h3>
        <p>Un ${_aDec('AJ')} ou un ${_aDec('RED')} ne passe pas dans l'année suivante de la cohorte (l'${_aLien('promo-effectifs', 'effectif')} se recalcule).
        Pour un redoublant, la suite se décide dans le ${_aLien('promo-devenir', 'Devenir')} : réinscription dans la promotion suivante, ou départ.</p>
        ${_aSiModif('promo:jury', _aTip(`vérifiez d'abord le bandeau « moyennes incomplètes » des ${_aLien('promo-bulletins', 'Bulletins')} : une décision prise sur une moyenne provisoire serait à refaire.`))}` },

    { id: 'promo-devenir', rub: R, titre: 'Devenir (suite du jury)', chemin: 'Promotions › Devenir',
      onglet: 'promo:devenir', cible: 'promotions/devenir',
      mots: 'devenir poursuite redoublement réinscription césure reprise autre formation école d\'ingénieur master licence pro bts école de commerce insertion professionnelle départ arbitrage ue redoublant',
      html: () => `
        <p>Ce que devient chaque étudiant <b>après le jury</b> de l'année choisie (${_aUi('Année jugée')}) : le devenir porte sur l'année suivante.
        Tout le circuit d'une cohorte à l'autre se règle ici.</p>
        <h3>A. Suite du jury : un étudiant par ligne</h3>
        <table><thead><tr><th>Décision de jury</th><th>Devenirs possibles</th></tr></thead><tbody>
            <tr><td>${_aDec('ADM')} ${_aDec('ADMJ')} ${_aDec('AJAC')} (années 1-2)</td><td>Poursuite en année suivante en <b>FTP</b> ou en <b>ALT</b> (rien de choisi = il poursuit dans sa sous-cohorte),
                <b>césure</b>, <b>autre formation</b>, <b>insertion professionnelle</b>, <b>départ</b> (raison inconnue).</td></tr>
            <tr><td>Année 3 (diplômés)</td><td><b>Autre formation</b> (poursuite d'études), <b>insertion professionnelle</b> ou <b>départ</b> — le statut n'est pas touché : partir après le BUT3 n'est pas un abandon.</td></tr>
            <tr><td>${_aDec('RED')}</td><td><b>Réinscrit en FTP</b> ou <b>en ALT</b> dans la promotion suivante, à l'année redoublée (créée automatiquement si elle n'existe pas encore), <b>abandon</b>, ou <b>autre formation</b>.</td></tr>
            <tr><td>${_aDec('AJ')}</td><td>Non listé : l'ajourné quitte la formation du fait même de la décision. S'il redouble, le jury le passe en RED.</td></tr>
        </tbody></table>
        ${_aSiModif('promo:devenir', `<p>Pour une <b>autre formation</b>, choisissez le type (école d'ingénieur, master, école de commerce, licence pro, BTS, autre) et écrivez où ; pour une
        <b>insertion</b>, l'employeur ou le poste. Chaque choix s'enregistre aussitôt et se répercute dans les ${_aLien('promo-effectifs', 'effectifs')} (pastilles, statuts).</p>`)
        || `<p>Une autre formation est précisée par son type (école d'ingénieur, master, école de commerce, licence pro, BTS, autre) et son nom ; une insertion, par l'employeur ou le poste.</p>`}
        ${_aEx('un redoublant de BUT2', `Un étudiant de 25-28 est ${_aDec('RED')} en année 2. Devenir : « RED → FTP ». Il est réinscrit en <b>26-29, année 2, FTP</b>
            (même fiche au registre, son dossier le suit) ; dans 25-28, il garde son année 2 et quitte l'année 3.`)}
        <h3>B. Les césures</h3>
        <p>Pour chaque césure posée : la sous-cohorte (FTP ou ALT) dans laquelle l'étudiant reprendra, dans la cohorte suivante.</p>
        <h3>C. Les redoublants accueillis dans cette promotion</h3>
        <p>Pour un redoublant venu d'une autre cohorte, le règlement retient, UE par UE et semestre par semestre, la <b>meilleure des deux moyennes</b>
        (passage précédent ou année refaite). Le jury peut imposer l'une ou l'autre : <b>auto</b> (la meilleure), <b>précédent</b> ou <b>refaite</b> — le choix vaut
        aussitôt pour les bulletins, les moyennes et le jury (repères ↺ et ⚖ dans les grilles).</p>
        ${_aSiModif('promo:devenir', _aTip(`depuis les Effectifs, une pastille ${_aCode('RED · à décider', 'background:#fef3c7')} et le rappel « N sans devenir renseigné » montrent ce qui reste à trancher.`))}` },

    { id: 'promo-actions', rub: R, titre: 'Créer ou supprimer une promotion', chemin: 'Promotions › Actions',
      onglet: 'promo:actions', cible: 'promotions/actions',
      mots: 'nouvelle promotion créer cohorte année de rentrée supprimer promotion',
      html: `
        <ul>
            <li>${_aUi('+ Nouvelle promotion')} : saisissez l'<b>année de rentrée</b> (ex. 2027) ; le nom (27-30) est généré, la cohorte dure trois ans et contient
                les sous-cohortes FTP et ALT. Rattachez-la ensuite à son programme (liste ${_aUi('Programme')} des Effectifs) et importez son effectif.</li>
            <li>${_aUi('🗑 Supprimer la promotion sélectionnée')} (superadmin) : supprime la cohorte et ses notes ; les étudiants inscrits ailleurs restent au registre,
                avec leur dossier. Les années universitaires ne sont pas supprimées.</li>
        </ul>
        ${_aTip(`la promotion d'accueil d'un redoublant de BUT1 est créée automatiquement par le ${_aLien('promo-devenir', 'Devenir')} si elle n'existe pas encore.`)}` },
    ];
}

function _aideEtudiants() {
    const R = 'etudiants';
    return [
    { id: 'etu-liste', rub: R, titre: 'Le registre des étudiants', chemin: 'Étudiants', onglet: 'etu:liste', cible: 'etudiants/liste',
      mots: 'registre liste recherche filtre cohorte année statut sexe recrutement jury export csv apogée',
      html: () => `
        <p>Tous les étudiants qu'au moins une cohorte a connus, <b>une ligne par personne</b> — même s'il a redoublé, changé de cohorte
        ou repris après une césure. On y cherche quelqu'un sans savoir dans quelle promotion il est.</p>
        <h3>Chercher et filtrer</h3>
        <ul>
            <li>La recherche porte sur le nom, le prénom et le n° Apogée, sans accents ni majuscules : « dup lea » trouve DUPONT Léa, « 2260 » les numéros qui contiennent 2260.</li>
            <li>Les filtres ${_aUi('Cohorte')}, ${_aUi('FTP + ALT')}, ${_aUi('Année')}, ${_aUi('Statut')}, ${_aUi('Sexe')}, ${_aUi('Recrutement')} et ${_aUi('Jury')} se combinent ; ${_aUi('Réinitialiser')} les efface.</li>
            <li>Avec une cohorte choisie, les filtres lisent le <b>parcours</b> : « 26-29, année 1 » rend l'effectif de cette année-là, comme l'onglet Effectifs.
                Sans cohorte, ils portent sur la situation <b>actuelle</b> de l'étudiant : ${_aUi('Année 2')} seule donne les étudiants en 2e année cette année, toutes cohortes confondues.</li>
        </ul>
        <h3>Les colonnes</h3>
        <p>Nom (avec ${_aCode('2 cohortes', 'background:#ddd6fe')} quand il en a connu plusieurs), prénom, Apogée, sexe, bac, recrutement, rang ParcourSup,
        dernière cohorte, FTP/ALT, <b>année</b> (un point gris devant : sa cohorte est sortie ou il l'a quittée — c'est sa dernière année suivie), statut,
        dernière décision de jury, dernière moyenne annuelle, nombre de notes. Un clic sur un en-tête trie ; un clic sur une ligne ouvre la ${_aLien('etu-fiche', 'fiche')}.</p>
        <p>${_aUi('Exporter (CSV)')} télécharge exactement ce qui est affiché (filtres et tri compris), lisible par Excel.</p>
        <p>Les boutons ${_aUi('Liste')} / ${_aUi('Trombinoscope')} changent de vue : voir ${_aLien('etu-photos', 'photos et trombinoscope')}.${
            _aSi('etu:convoquer', ` ${_aUi('À convoquer')} dresse la liste des étudiants à recevoir : voir ${_aLien('etu-convoquer', 'les étudiants à convoquer')}.`)}</p>` },

    { id: 'etu-fiche', rub: R, titre: "La fiche d'un étudiant", chemin: 'Étudiants › fiche',
      onglet: 'etu:liste', cible: 'etudiants/liste',
      mots: 'fiche étudiant dossier parcours cohortes résultats relevé bulletin état civil photo parcoursup candidature',
      html: () => `
        <p>Un étudiant n'a qu'une fiche, quel que soit le nombre de cohortes qu'il a traversées${_aSiModif('etu:liste',
        ' : ce qui y est saisi décrit <b>la personne</b> et vaut pour toutes ses inscriptions')}.</p>
        <h3>Sous-onglet « Informations »</h3>
        <ul>
            <li><b>Photo</b> et état civil (nom, prénom, n° Apogée, naissance, âge calculé) ;</li>
            <li><b>profil</b> : sexe, recrutement, pays, série de bac, années depuis le bac, études antérieures (grisées quand le bac date de l'année d'entrée) ;</li>
            <li><b>parcours</b> : chaque cohorte traversée, l'année d'entrée, la sous-cohorte, le statut, l'origine (redoublant, reprise après césure), puis année
                par année la décision de jury, la moyenne générale, la mobilité — et l'abandon, la césure ou le devenir s'il y en a ;</li>
            <li><b>dossier ParcourSup</b> (rang, note, spécialités…), repris de l'import${_aSiModif('etu:liste',' mais modifiable pour qui n\'y figure pas')} ;</li>
            <li>le <b>dossier de candidature</b> détaillé, quand l'export CSV complet a été importé (lecture seule).</li>
        </ul>
        <h3>Sous-onglet « Notes et résultats »</h3>
        <p>Le relevé de toute la scolarité, semestre par semestre : pour chaque UE, les matières qui y pèsent avec leur coefficient et leur note, puis la
        moyenne obtenue. Les années faites dans une autre cohorte y figurent aussi.</p>
        <p>Quand l'étudiant a une <b>pénalité d'assiduité</b>, chaque UE du semestre détaille le calcul : moyenne des notes, pénalité retranchée
        (avec le nombre d'heures), puis moyenne de l'UE. Le tableau de l'année reprend, sous les UE, la pénalité de chaque semestre et la
        <b>bonification sport/art</b> ajoutée aux moyennes annuelles. Une moyenne d'UE nettement sous les notes s'explique souvent ainsi.</p>
        ${_aSi('etu:suivi', `<h3>Sous-onglet « Suivi »</h3>
        <p>L'évolution de ses moyennes face à sa promotion, ses motifs de convocation et le journal de suivi : voir ${_aLien('etu-suivi', "le suivi d'un étudiant")}.</p>`)}
        ${_aSi('promo:effectif', _aTip(`depuis les Effectifs, un clic sur un nom ouvre la fiche dans une fenêtre ; ${_aUi('Fiche complète et résultats →')} la rouvre dans l'onglet Étudiants, avec les notes.`))}` },

    { id: 'etu-suivi', rub: R, titre: "Le suivi d'un étudiant", chemin: 'Étudiants › fiche › Suivi',
      onglet: 'etu:suivi', cible: 'etudiants/liste',
      mots: 'suivi évolution moyenne promotion classe écart-type courbe commentaire signalement problème entretien journal baisse',
      html: () => `
        <p>Le sous-onglet ${_aUi('Suivi')} de la fiche réunit ce qu'il faut pour parler avec l'étudiant de son parcours.</p>
        <h3>Évolution</h3>
        <ul>
            <li>Un <b>graphique en étoile</b> : un axe par UE — ou, avec ${_aUi('Domaines')}, par domaine d'ingénierie des ressources —,
                de 0 au centre à 20 au bord ; l'anneau plus marqué est la moyenne de 10 ;</li>
            <li>le <b>semestre choisi</b> (boutons S1, S2…) en bleu, points pleins ; le <b>semestre précédent</b> en bleu clair, points creux ;
                une <b>flèche</b> sur chaque branche va de l'un à l'autre — verte vers l'extérieur en hausse, rouge vers le centre en baisse,
                à partir d'un point d'écart ; la <b>promotion</b> en gris : sa moyenne en trait et, en aplat, <b>± un écart-type</b>. On voit d'un
                coup ses points forts et faibles, ce qui a bougé, et s'il s'écarte de sa promotion ou si le semestre a été dur pour tous.
                Le survol d'une branche donne le détail ;</li>
            <li>le tableau donne tous les semestres : chaque valeur sur le fond des notes, l'écart au semestre précédent (▲ ▼) et la promotion
                (moyenne ± écart-type) ; au survol, l'écart à la promotion en nombre d'écarts-types. Un clic sur un semestre l'affiche dans
                l'étoile. Suivent les heures d'absence, les ABI et les décisions de jury ;</li>
            <li><b>Par matière</b> : une étoile par semestre, une branche par matière notée — sa note face à la moyenne de la promotion
                ± un écart-type dans cette matière (une ABI compte 0). Le cadre du semestre choisi est marqué.</li>
        </ul>
        <p>Les notes ne sont pas datées : l'évolution se lit d'un semestre à l'autre. La moyenne de la promotion écarte ceux qui ont abandonné.</p>
        <h3>Journal de suivi</h3>
        <ul>
            ${_aSiModif('etu:suivi', `<li>${_aUi('+ Commentaire')} : une observation, rattachée si besoin à une matière ;</li>
            <li>${_aUi('+ Signaler un problème')} : la date des faits, un motif (absences, retards, travail non rendu, comportement, fraude, difficultés…), la description.
                Un signalement reste <b>non traité</b> tant que son auteur ou la direction ne l'a pas marqué traité ; un signalement de
                <b>comportement</b> ou de <b>fraude</b> non traité met l'étudiant dans la liste à convoquer ;</li>`)}
            ${_aSi('etu:convoquer', `<li>${_aUi('+ Entretien')} : date, participants, compte rendu, décisions, prochain point ; l'étudiant passe alors <b>reçu</b>.
                Les entretiens ne sont lus que par qui voit la liste ${_aLien('etu-convoquer', 'À convoquer')} ;</li>`)}
            <li>commentaires et signalements sont lus par toute l'équipe ; chacun modifie ou supprime les siens${_aSi('etu:convoquer', ', la direction tous')}.</li>
        </ul>
        ${_aTip("l'étudiant peut demander à lire ce journal : écrivez des faits observables, sans jugement sur la personne, et rien sur sa santé ou sa vie privée.")}` },

    { id: 'etu-convoquer', rub: R, titre: 'Les étudiants à convoquer', chemin: 'Étudiants › À convoquer',
      onglet: 'etu:convoquer', cible: 'etudiants/convoquer',
      mots: 'convoquer convocation entretien alerte notes faibles ue moyenne matières chute baisse comportement fraude signalement critères seuils',
      html: () => `
        <p>La vue ${_aUi('À convoquer')} de l'onglet Étudiants liste les étudiants de l'<b>année active</b> que des critères désignent. Elle est
        recalculée à chaque affichage ; ${_aUi('Critères…')} montre les seuils${_aSiModif('etu:convoquer', ' et permet de les régler (case vide = critère désactivé)')}.</p>
        <h3>Les critères</h3>
        <p>Sur les <b>notes</b> seulement — celles de son dernier semestre noté : celui de l'année en cours, ou, tant que rien n'y est
        noté (la rentrée), le dernier de l'an dernier, marqué de son année (« S2 (25-26) ») —, et sur le comportement signalé :</p>
        <ul>
            <li><b>UE sous la moyenne</b> : une UE du semestre sous 10 ;</li>
            <li><b>Matières faibles</b> : au moins 2 matières sous 8 (une ABI compte 0, comme dans les moyennes) ;</li>
            <li><b>Chute</b> : sa moyenne des UE ou une UE baisse d'au moins 2 points depuis le semestre précédent, sur ses propres notes —
                dans l'année (S1 → S2) comme d'une année à l'autre (S2 → S3, S4 → S5) ;</li>
            <li><b>Comportement</b> ou <b>fraude</b> : un signalement de ce motif non traité. Les autres signalements (absences, retards,
                travail non rendu…) restent au journal sans faire convoquer.</li>
        </ul>
        <p>Un <b>redoublant</b> n'est pas convoqué pour ses notes pendant l'année qu'il refait — celles de l'année ratée sont la raison
        même de son redoublement — ; seul un signalement de comportement ou de fraude le fait convoquer. L'assiduité, le parcours (AJAC)
        et la décision de jury ne font pas convoquer : ils restent lisibles dans la fiche.</p>
        ${_aSiModif('etu:convoquer', `<h3>Convoquer, recevoir, écarter</h3>
        <ul>
            <li>${_aUi('Convoquer')} note la convocation du jour : l'étudiant reste dans la liste jusqu'à son entretien ;</li>
            <li>${_aUi('Entretien…')} ouvre son suivi sur un compte rendu ; enregistré, il le note <b>reçu</b> et l'étudiant sort de la liste ;</li>
            <li>${_aUi('Écarter')} : pas besoin de le recevoir pour ces motifs ; ${_aUi('↺ Effacer')} efface l'état.</li>
        </ul>`)}
        <p>Reçu ou écarté, un étudiant ne revient qu'avec un <b>nouveau motif</b>, signalé comme tel. ${_aUi('Afficher aussi les reçus et écartés')} les montre ;
        ${_aUi('Exporter (CSV)')} télécharge la liste affichée. La colonne Évolution trace sa moyenne des UE semestre après semestre, et en pointillé gris
        celle de sa promotion.</p>` },

    { id: 'etu-photos', rub: R, titre: 'Photos et trombinoscope', chemin: 'Étudiants › Trombinoscope',
      onglet: 'etu:liste', cible: 'etudiants/trombi',
      mots: 'photo trombinoscope trombi pdf grille télécharger imprimer portrait',
      html: () => `
        <h3>La vue Trombinoscope</h3>
        <p>Le bouton ${_aUi('Trombinoscope')} remplace la liste par une grille de photos, <b>avec les mêmes filtres</b>, par ordre alphabétique,
        en deux sections : <b>Temps plein</b> puis <b>Alternance</b>. Sans photo, la vignette porte les initiales ; un statut autre que « Actif »
        (Abandon…) est signalé. Un clic sur une photo ouvre la fiche. La vue choisie est gardée d'une visite à l'autre.</p>
        <h3>Télécharger un trombinoscope (PDF)</h3>
        <ul>
            <li>Depuis la vue Trombinoscope : ${_aUi('Télécharger le trombi (PDF)')} met en page <b>ce qui est affiché</b>, filtres compris.</li>
            ${_aSi('promo:effectif', `<li>Depuis ${_aOng('Promotions › Effectifs')} : ${_aUi('⤓ Trombi (PDF)')} donne le trombinoscope de l'année affichée — les étudiants qui la suivent,
                <b>sans les césures ni les abandons</b>, temps plein puis alternance.</li>`)}
        </ul>
        <p>Le PDF est en A4 paysage, 18 photos par page : titre (« BUT 1 Génie Industriel et Maintenance — Temps plein »), promotion, année universitaire et
        effectif, puis nom, prénom et n° Apogée sous chaque photo.</p>
        ${_aEx('le trombi des BUT1 FTP', `${_aOng('Étudiants')} → ${_aUi('Trombinoscope')} → filtres <b>26-29</b>, <b>Année 1</b>, <b>FTP</b>, statut <b>Actif</b>
            → ${_aUi('Télécharger le trombi (PDF)')} : le fichier <code>Trombi_26-29_BUT1_FTP.pdf</code> est prêt à imprimer.`)}
        ${_aSiModif('etu:liste',`<h3>La photo d'une fiche</h3>
        <p>Sur la fiche : ${_aUi('Ajouter')} ou ${_aUi('Changer')} (n'importe quelle image — elle est convertie en JPEG et réduite automatiquement), ${_aUi('✕')} pour la retirer.</p>`)}` },

    { id: 'etu-trombi-import', rub: R, titre: 'Importer un trombinoscope (photos)', chemin: 'Étudiants › Importer un trombi (PDF)',
      onglet: 'etu:liste', pour: 'modifier', cible: 'etudiants/liste',
      mots: 'importer trombi pdf photos scolarité rapprochement apogée nom approché inversé',
      html: `
        <p>Les trombinoscopes PDF de la scolarité (une photo, le nom, le prénom et le n° Apogée de chaque étudiant) donnent d'un coup une photo à chaque fiche.</p>
        ${_aSteps([
            `${_aUi('Importer un trombi (PDF)')}, en haut de la liste des étudiants.`,
            `Choisissez un ou plusieurs PDF (les six trombis de l'année en une fois, par exemple), puis ${_aUi('Analyser')}.`,
            `Vérifiez : chaque photo est proposée pour une fiche, reconnue par son <b>n° Apogée</b>, sinon par le <b>nom</b> (y compris nom et prénom inversés, ou un nom
             approché : faute de frappe, nom composé abrégé). Les cas douteux sont en tête, sur fond jaune ; une liste permet de corriger, une case d'écarter une photo.`,
            `${_aUi('Associer N photos')} : les photos sont enregistrées (une photo déjà présente est remplacée).`])}
        <ul>
            <li>Une fiche ne reçoit qu'une photo : la proposer pour une deuxième vignette est refusé.</li>
            <li>La case <b>Compléter le n° Apogée</b> (cochée par défaut) reporte le numéro lu sur le PDF dans les fiches qui n'en ont pas — un numéro déjà saisi n'est jamais remplacé.</li>
            <li>Le titre des pages (« BUT 2 … - ALT ») sert à chercher d'abord parmi les étudiants de cette année et de cette sous-cohorte.</li>
        </ul>
        ${_aEx('les cas à vérifier', `« MARTINES Paul » sur le PDF, « MARTINEZ Paul » sur la fiche : <b>nom approché</b>. « JEAN PIERRE Durand » sur le PDF,
            « DURAND Jean Pierre » sur la fiche : <b>nom inversé</b>. La proposition est juste dans les deux cas : on laisse cochée.`)}` },
    ];
}

function _aideSuivi() {
    const R = 'suivi';
    return [
    { id: 'suivi-fiches', rub: R, titre: 'Fiches de suivi (tuteurs)', chemin: 'Stages / Alternance › Tuteurs',
      onglet: ['nav:stages', 'nav:alternance'], cible: ['stages/fiches', 'alternance/fiches'],
      mots: 'stage stagiaire alternance alternant tuteur universitaire tuteur entreprise entreprise mission sujet fiche suivi ville département',
      html: `
        <p>Deux onglets jumeaux, pour une ${_aUi('Année universitaire')} :</p>
        <ul>
            <li>${_aOng('Stages')} : les <b>stagiaires FTP de 2<sup>e</sup> et 3<sup>e</sup> année</b> ;</li>
            <li>${_aOng('Alternance')} : les <b>alternants des trois années</b>.</li>
        </ul>
        <p>Les étudiants sont listés par cohorte. Chaque fiche dit l'entreprise (ville, département), le tuteur entreprise, la mission
        (sujet du stage, ou poste et missions de l'alternant) et le <b>tuteur universitaire</b>.</p>
        <h3>Remplir une fiche</h3>
        <p>Un clic sur un étudiant ouvre sa fiche :</p>
        <ul>
            <li><b>Entreprise / organisme</b> : la liste propose les entreprises déjà connues (toutes années) — en choisir une reprend son lieu ;</li>
            <li><b>Ville</b>, <b>Département</b> (numéro « 83 » ou nom « Var ») ;</li>
            <li><b>Tuteur entreprise</b> (Prénom Nom), sa <b>fonction</b>, son <b>e-mail</b> et son <b>téléphone</b> — un tuteur déjà connu dans cette entreprise reprend ses coordonnées ;</li>
            <li><b>Mission</b> ;</li>
            <li><b>Tuteur universitaire</b> : un enseignant de l'année affichée (les vacataires sont signalés « (vac.) »).</li>
        </ul>
        <p>Pour un <b>alternant</b>, la fiche saisie une année reste valable les années suivantes tant qu'elle n'est pas remplacée (« fiche reprise de
        2025-2026 ») ; pour un <b>stagiaire</b>, elle ne vaut que pour l'année du stage.</p>
        <h3>Filtres</h3>
        <p>La recherche (étudiant, entreprise, tuteur), ${_aUi('À compléter seulement')} (fiches sans entreprise, sans tuteur entreprise ou sans tuteur
        universitaire) et ${_aUi('Mes suivis')} (les étudiants dont vous êtes le tuteur universitaire). En tête, un résumé : nombre d'étudiants, combien ont une
        entreprise, combien sont encore sans tuteur universitaire.</p>
        <h3>Qui fait quoi</h3>
        <ul>
            <li>L'administration et le <b>responsable</b> du domaine (stages pour les stagiaires FTP, ALT pour les alternants) remplissent toutes les fiches et
                <b>attribuent les tuteurs universitaires</b>.</li>
            <li>Un enseignant connecté avec son mot de passe consulte toutes les fiches et complète celles des étudiants <b>qu'il suit</b>.</li>
        </ul>
        ${_aTip(`un stagiaire en mobilité internationale au semestre du stage n'a pas de stage à suivre : il est simplement signalé sous sa cohorte.`)}` },

    { id: 'suivi-stats', rub: R, titre: 'Statistiques des stages et de l\'alternance', chemin: 'Stages / Alternance › Statistiques',
      onglet: ['nav:stages', 'nav:alternance'], cible: ['stages/stats', 'alternance/stats'],
      mots: 'statistiques entreprises tuteurs départements couverture suivis par enseignant',
      html: `
        <p>Le sous-onglet ${_aUi('Statistiques')} résume l'année affichée :</p>
        <ul>
            <li>la <b>couverture</b> des fiches : combien ont une entreprise, un tuteur entreprise, un tuteur universitaire (et combien restent sans) ;</li>
            <li>les <b>suivis par enseignant</b> : le nombre d'étudiants de chaque tuteur universitaire ;</li>
            <li>les <b>lieux par département</b> ;</li>
            <li>les <b>entreprises</b> et leurs tuteurs, pour l'année ou toutes années confondues.</li>
        </ul>` },
    ];
}

function _aideProgramme() {
    const R = 'programme';
    return [
    { id: 'prog-vue', rub: R, titre: 'Le programme national', chemin: 'Programme', onglet: 'nav:programme',
      mots: 'programme national pn maquette compétences ue coefficients ressources saé référentiel',
      html: () => `
        <p>Un <b>programme</b> décrit la maquette du BUT : pour chaque semestre, ses <b>matières</b> (ressources et SAÉ), les <b>compétences</b>
        (UE) dans lesquelles elles comptent, leurs <b>coefficients</b> et leurs <b>volumes horaires</b>. Il est réutilisable : plusieurs promotions
        peuvent suivre le même (ex. PN_2026).</p>
        <ul>
            <li>La liste ${_aUi('Programme')} choisit le programme affiché ; les boutons ${_aUi('Année 1')} ${_aUi('Année 2')} ${_aUi('Année 3')} montrent les semestres
                correspondants (S1 + S2, S3 + S4, S5 + S6), côte à côte.</li>
            ${_aSiModif(['prog:coeff', 'prog:matieres'], `<li>${_aUi('💾 Enregistrer')} enregistre les grilles Coefficients et Matières ; quitter avec des modifications en attente le demande.</li>`)}
            <li>Ce sont les coefficients du programme d'une promotion qui font les moyennes de ses bulletins et de son jury${_aSiModif('promo:effectif',
                ` ; elle y est rattachée dans ${_aOng('Promotions › Effectifs')} (liste ${_aUi('Programme')})`)}.</li>
        </ul>
        ${_aSiModif('prog:coeff', _aWarn(`modifier les coefficients d'un programme change aussitôt les moyennes de <b>toutes</b> les promotions qui le suivent.${
            _aSi('prog:actions', ` Pour une nouvelle maquette, ${_aUi('Dupliquer')} le programme (sous-onglet Actions) et rattacher la nouvelle promotion à la copie.`)}`))}` },

    { id: 'prog-coeff', rub: R, titre: 'Coefficients', chemin: 'Programme › Coefficients',
      onglet: 'prog:coeff', cible: 'programme/coeff',
      mots: 'coefficients ue compétence poids matière bonus pénalité aide à la réussite ordre',
      html: () => `
        <p>Pour chaque semestre, un tableau : les matières en lignes, les <b>compétences (UE)</b> en colonnes, et dans chaque case le
        <b>coefficient</b> de la matière dans l'UE. Une même matière compte souvent dans plusieurs UE, avec des poids différents : c'est le modèle du BUT.</p>
        <ul>
            <li>Les types de matière se distinguent par leur couleur : SAÉ, ressource, portfolio, stage… Les matières <b>sans coefficient</b> (bonus, pénalité,
                aide à la réussite) sont calculées à part et grisées.</li>
            ${_aSiModif('prog:coeff', `<li>${_aUi('▲')} ${_aUi('▼')} changent l'ordre d'affichage, ${_aUi('🗑')} supprime une matière du semestre.</li>`)}
        </ul>
        ${_aEx('la moyenne d\'une UE (coefficients fictifs)', `Une UE où comptent une SAÉ (coefficient 30) et deux ressources (12 et 8). Un étudiant
            qui a 14, 10 et 9 : (30 × 14 + 12 × 10 + 8 × 9) / 50 = <b>12,24</b>. Les pénalités et bonus s'appliquent ensuite
            (${_aLien('promo-bulletins', 'Bulletins')}).`)}` },

    { id: 'prog-matieres', rub: R, titre: 'Matières et volumes', chemin: 'Programme › Matières',
      onglet: 'prog:matieres', cible: 'programme/matieres',
      mots: 'matière code apogée libellé court type volumes cm td tp pt heures hetd total semestre préconisation nationale référentiel préco coût prévisionnel mutualisé groupes budget',
      html: () => `
        <p>La définition de chaque matière du programme : <b>type</b>, <b>code</b> (R1.01, SAE1.02…), <b>libellé court</b> et <b>libellé</b>, <b>code Apogée</b>
        (sert aux imports de notes), et ses <b>volumes</b> : CM, TD et TP pour une ressource ; TD, TP et PT (projet tutoré) pour une SAÉ.
        Les colonnes Total h et HETD totalisent chaque matière et chaque semestre.</p>
        <p>Les colonnes <b>Préco CM/TD</b> et <b>Préco TP</b> rappellent la <b>préconisation nationale</b> du référentiel : heures de CM et TD,
        heures de TP. Elles se lisent seulement ; l'info-bulle d'une cellule donne le volume national total, TP compris. Les SAÉ n'en ont pas toujours.</p>
        <p>La partie <b>Alternants (ALT)</b> du tableau est leur maquette : CM, TD, TP et PT de chaque matière. Une case vide reprend
        l'heure de la formation initiale (affichée en gris) ; on ne saisit donc que ce qui change. ${_aUi('Fait')} décoché retire une SAÉ ou une PAÉ
        que les alternants ne réalisent pas. En bas de chaque semestre, la <b>diminution des alternants</b> (leurs heures face à celles de la
        formation initiale, avec le chiffre hors projet tutoré) ; le bilan de chaque année et celui des 3 années, sous les tableaux, donnent aussi
        le volume qui ferait −20 %.</p>
        <p>Au-dessus de chaque semestre, le <b>coût prévisionnel</b>. Cochez ${_aUi('Mutualisé FTP + ALT')} si les deux publics suivent les cours
        ensemble : un CM et les <b>groupes de la promotion</b> (TD, TP, PT), sur la plus grande des deux maquettes. Sinon, indiquez les
        <b>groupes FTP</b> et les <b>groupes ALT</b> : chaque formation compte avec ses propres heures et son CM. Le coût, en HETD, multiplie les
        heures par les groupes ; il est donné par formation (FTP, ALT, ou commun si mutualisé) et au total, pour chaque semestre, chaque année et
        les 3 années (même celles que le filtre masque). C'est une estimation propre au programme, enregistrée avec lui : elle ne lit ni ne
        modifie les groupes définis dans Promotions.</p>
        ${_aEx('un coût prévisionnel (chiffres fictifs)', `Des ressources avec 100 h de CM, 150 h de TD et 120 h de TP, et une SAÉ de 30 h de PT, avec les
            coefficients HETD par défaut (CM 1,5 ; TD 1 ; TP 2/3 ; PT 1). Mutualisé, avec 2 groupes de TD, 4 de TP et 4 de PT :
            100 × 1,5 + 150 × 2 + 120 × 4 × 2/3 + 30 × 4 = <b>890 HETD</b> (commun). Non mutualisé, avec ces groupes pour les FTP (890 HETD) et,
            pour les alternants, une maquette à 80 h de CM, 120 h de TD et 96 h de TP, sans la SAÉ, en 1 groupe de TD et 2 de TP :
            80 × 1,5 + 120 × 1 + 96 × 2 × 2/3 = 368 HETD — soit FTP 890 · ALT 368 · total <b>1 258 HETD</b>, et des alternants à −26 %
            (296 h au lieu de 400 h).`)}
        <p>La colonne <b>Domaine</b> (grand domaine d'ingénierie) classe les <b>ressources</b> pour
        ${_aLien('stats-categories', 'Statistiques › Domaines')} et pour l'évolution du suivi d'un étudiant ; elle ne change aucune moyenne.
        ${_aSiModif('prog:matieres', `La liste des domaines, commune à tous les programmes, se modifie avec ${_aUi('Gérer les domaines…')} : renommer un domaine le renomme dans toutes les matières.`)}</p>
        <p>Ces volumes sont ceux du <b>programme</b>${_aSi('svc:matieres', ` : ils servent de référence (colonne PN) dans ${_aLien('matieres', 'Service › Matières')}, où l'on répartit
        les heures réellement données entre FTP, ALT et sous-matières`)}.</p>
        ${_aSi('prog:actions', _aTip(`une nouvelle matière se crée depuis le sous-onglet ${_aUi('Actions')} (${_aUi('+ Créer matière')}) ; elle apparaît ensuite ici et dans les Coefficients.`))}` },

    { id: 'prog-contenu', rub: R, titre: 'Contenu des matières', chemin: 'Programme › Contenu',
      onglet: 'prog:contenu', cible: 'programme/contenu',
      mots: 'contenu description matière programme national pn pdf mes matières enseignant',
      html: `
        <p>Le contenu pédagogique de chaque matière de l'année active, semestre par semestre.</p>
        <ul>
            <li>${_aUi('Consultation')} : pour chaque sous-matière, la description écrite par ses enseignants et, à côté, le contenu du <b>programme national</b> (PN), commun à la matière.</li>
            <li>${_aUi('Mes matières')} : les matières où vous intervenez, pour écrire ou mettre à jour leur description (bouton ${_aUi('Enregistrer')} par matière).
                L'administration y renseigne aussi le contenu PN (${_aUi('Enregistrer le PN')}), appliqué à toutes les sous-matières de la matière.</li>
            <li>${_aUi('📄 Télécharger le PDF du PN')}, quand le document est disponible sur le serveur.</li>
        </ul>` },

    { id: 'prog-actions', rub: R, titre: 'Gérer les programmes', chemin: 'Programme › Actions',
      onglet: 'prog:actions', cible: 'programme/actions',
      mots: 'nouveau programme renommer dupliquer supprimer créer matière réinitialiser exporter importer json transfert',
      html: `
        <p>Les actions s'appliquent au programme choisi dans la barre du haut :</p>
        <ul>
            <li>${_aUi('+ Nouveau programme')}, ${_aUi('Renommer')}, ${_aUi('Dupliquer')} ; ${_aUi('🗑 Supprimer')} est réservé au superadmin ;</li>
            <li>${_aUi('+ Créer matière')} : semestre, type (SAÉ, ressource, pénalité, bonus), code, libellés, volumes et code Apogée — pensez à ${_aUi('Enregistrer')} ensuite ;</li>
            <li>${_aUi('↺ Réinitialiser (fichier d\'origine)')} : revient au programme tel qu'il a été chargé au départ ;</li>
            <li>${_aUi('⤓ Exporter (JSON)')} / ${_aUi('⤒ Importer')} : transférer les programmes d'une installation à l'autre (du poste local au serveur, par exemple).</li>
        </ul>` },
    ];
}

function _aideStats() {
    const R = 'stats';
    const sec = (cle, titre, mots, html) => ({ id: 'stats-' + cle, rub: R, titre, chemin: 'Statistiques › ' + titre,
                                               onglet: 'st:' + cle, cible: 'statistiques/' + cle, mots, html });
    return [
    sec('apercu', "Vue d'ensemble", 'tableau de bord indicateurs chiffres clés',
        `<p>Le tableau de bord du département, calculé sur les promotions, l'année active et les années archivées :</p>
        <ul>
            <li>les <b>chiffres clés</b> : étudiants, moyenne générale, notes saisies, enseignants, heures de maquette, matières, années gérées, âge moyen à l'entrée, boursiers ;</li>
            <li>la <b>répartition des étudiants</b> (par promotion, par sous-cohorte) ;</li>
            <li>les <b>résultats</b> : répartition des notes de matières, décisions de jury de l'année ;</li>
            <li>la <b>charge d'enseignement</b> : heures par type et par semaine.</li>
        </ul>
        <p>Tout est <b>agrégé</b> : aucun étudiant n'est nommé. ${_aUi('↻ Actualiser')} recalcule après des modifications ; les graphiques se lisent au survol.</p>`),
    sec('etudiants', 'Étudiants', 'profil effectifs femmes âge origine boursiers entrants complétude des fiches',
        `<ul>
            <li><b>Effectifs</b> par promotion et par sous-cohorte, part de femmes par promotion ;</li>
            <li><b>Profil d'entrée</b> : recrutement, série de bac, années depuis le bac, études antérieures ;</li>
            <li><b>Âge, origine et situation des entrants</b> : âge à l'entrée, départements et communes de résidence, bourse et échelons, sportifs et artistes —
                chaque personne comptée une fois, dans la cohorte qui l'a recrutée ;</li>
            <li>ce que le <b>dossier de candidature</b> annonce de la réussite (mention au bac, maths de terminale, avis du chef d'établissement…) ;</li>
            <li>les <b>échecs de 1<sup>re</sup> année</b>, toutes cohortes ;</li>
            <li>la <b>complétude des fiches</b> : quels champs restent à renseigner.</li>
        </ul>`),
    sec('recrutement', 'Recrutement', 'parcoursup classement note rang spécialités série profil réussite corrélation',
        `<p>Le dossier ParcourSup, et ce qu'il annonce des résultats en BUT :</p>
        <ul>
            <li><b>Niveau du recrutement</b> : note ParcourSup moyenne et rang médian, par promotion et sous-cohorte ;</li>
            <li><b>Profil des candidats recrutés</b> : série de bac, combinaisons de spécialités, spécialité abandonnée, scolarité, profil à la candidature ;</li>
            <li><b>Recrutement × réussite</b> : moyenne de BUT et UE validées par tranche de classement, par note ParcourSup, par spécialités…</li>
        </ul>
        ${_aTip(`le croisement demande des étudiants qui aient à la fois un classement importé et des notes de BUT : quand il est vide, l'écran dit pourquoi
            (promotion pas encore notée, classement pas importé). Une corrélation faible est un résultat en soi.`)}`),
    sec('parcours', 'Parcours & jury', 'parcours jury validation ue redoublements sorties transferts devenir mobilité tuteurs entreprises',
        `<ul>
            <li><b>Jury</b> : taux de validation des UE (ADM, ADMJ ou compensée), moyennes annuelles et de semestre par compétence ;</li>
            <li><b>Cohortes</b> : redoublements traités, sorties de formation, transferts de cohorte, et où partent ceux qui quittent la formation (onglet ${_aLien('promo-devenir', 'Devenir')}) ;</li>
            <li><b>Mouvements et encadrement</b> : mobilité internationale, tuteurs universitaires, entreprises d'accueil.</li>
        </ul>`),
    sec('resultats', 'Résultats', 'notes distribution moyennes quartiles matières sous la moyenne comparaisons série recrutement',
        `<ul>
            <li><b>Distribution</b> des notes de matières et des moyennes générales, avec médiane et quartiles ;</li>
            <li><b>Matières</b> : moyennes les plus hautes et les plus basses, part sous la moyenne ;</li>
            <li><b>Comparaisons</b> par semestre, par promotion, par sous-cohorte ;</li>
            <li><b>Croisements profil × résultats</b> : par série de bac, par voie de recrutement.</li>
        </ul>`),
    sec('categories', 'Domaines', 'domaine mécanique électronique maintenance mécatronique ingénierie ressources classement compétences',
        `<p>Les résultats des <b>ressources</b> regroupées selon leur <b>domaine d'ingénierie</b> (mécanique, électronique…), choisi dans
        Programme › Matières. Les SAÉ n'y entrent pas.</p>
        <ul>
            <li>La moyenne d'un étudiant dans un domaine pondère ses notes par le <b>poids</b> de chaque ressource (somme de ses coefficients dans les UE) ;
                un groupe est résumé par la moyenne de ses étudiants, affichée à partir de 5 étudiants ;</li>
            <li><b>Par domaine</b>, toutes années puis année par année ;</li>
            <li><b>Par promotion</b>, par sous-cohorte FTP / ALT, et selon le <b>profil d'entrée</b> (bac, sexe, recrutement, études antérieures) ;</li>
            <li><b>Réussite en 1re année</b> : les moyennes de 1re année selon l'issue (validée, AJAC, échec, abandon) ;</li>
            <li>la liste des ressources notées <b>sans domaine</b>, à classer.</li>
        </ul>
        ${_aEx('lire une case', `« Mécanique : 8,40 n=42 » sur la ligne Échec : les 42 étudiants en échec en 1re année y avaient en moyenne 8,40 dans les ressources de mécanique.`)}`),
    sec('enseignement', 'Enseignement', 'heures maquette enseignants hetd médiane charge par semaine corps statut sessions salles',
        `<ul>
            <li><b>Volume horaire</b> : heures de maquette par type et par semestre, charge par semaine, part mutualisée ;</li>
            <li><b>Enseignants</b> : effectif en service, HETD médiane, répartition par corps et par statut, distribution des services (moyenne, médiane, quartiles) ;</li>
            <li><b>Matières et sessions</b> par semestre, sessions par face et salles.</li>
        </ul>`),
    sec('annees', 'Années', 'comparaison années universitaires archivées évolution',
        `<p>La comparaison des années universitaires gérées par le site — enseignants, matières, sessions, heures de maquette — pour suivre leur évolution.
        Sans année archivée, l'écran le signale.</p>`),
    ];
}

function _aideAdmin() {
    const R = 'admin';
    return [
    { id: 'enseignants', rub: R, titre: 'Les enseignants', chemin: 'Enseignant', onglet: 'nav:enseignants', cible: 'enseignants',
      mots: 'enseignant liste ajouter modifier supprimer corps statut titulaire vacataire mcf prag prce plp service statutaire contact',
      html: () => `
        <p>La liste des enseignants de l'<b>année active</b> : coordonnées, contact préféré (déclaré par chacun dans son onglet Mon Compte),
        structure, corps et statut.${_aSiModif('nav:enseignants', ` ${_aUi('+ Ajouter')}, ${_aUi('Éditer')} et ${_aUi('Supprimer')} sur chaque ligne.`)}</p>
        <ul>
            <li>Le <b>nom</b> sert d'identifiant de connexion : il doit être unique et correspondre au nom de famille de l'enseignant.</li>
            <li>Le <b>corps</b> fixe le service statutaire utilisé par le ${_aLien('bilan', 'Bilan Global')} : MCF 192 HETD, PRAG / PRCE / PLP 384 HETD.</li>
            <li>Le <b>statut</b> : titulaire ou vacataire (un vacataire voit moins d'informations dans la répartition, et n'a pas d'heures complémentaires calculées).</li>
        </ul>
        ${_aTip(`la liste est propre à chaque année universitaire : un enseignant arrivé en cours de route s'ajoute dans l'année concernée.`)}` },

    { id: 'enseignants-acces', rub: R, titre: "Donner un accès à un enseignant", chemin: 'Enseignant › Éditer › Accès Promotions',
      onglet: 'nav:enseignants', pour: 'superadmin', cible: 'enseignants',
      mots: 'mot de passe autoriser réinitialiser révoquer droits d\'administration admin responsabilités resp ftp alt stages accès promotions',
      html: `
        <p>Dans la fiche d'un enseignant (${_aUi('Éditer')}), le bloc <b>Accès Promotions</b> — réservé au superadmin :</p>
        <table><tbody>
            <tr><td>${_aUi('Autoriser la création du mot de passe')}</td><td>L'enseignant pourra créer son mot de passe sur l'écran de connexion (${_aLien('connexion', 'voir')}). État affiché : « autorisé, en attente de création ».</td></tr>
            <tr><td>${_aUi('Réinitialiser le mot de passe')}</td><td>Supprime le mot de passe actuel : le bouton « Initialiser mon mot de passe » réapparaît (mot de passe oublié).</td></tr>
            <tr><td>${_aUi('Révoquer l\'accès')}</td><td>Supprime le mot de passe et interdit d'en recréer un : retour à la connexion par le nom seul.</td></tr>
            <tr><td><b>Droits d'administration</b></td><td>Fait de l'enseignant un <b>admin</b> : tout le travail courant, sauf les droits réservés au superadmin (droits, mots de passe, restauration, journal, années, HETD, suppression de promotions et de programmes).</td></tr>
            <tr><td><b>Responsabilités</b></td><td><b>Formation FTP</b>, <b>Formation ALT</b>, <b>Stages</b> : ajoutent à sa session normale les droits de ces domaines (${_aLien('sessions', 'détail')}). Cumulables.</td></tr>
        </tbody></table>
        ${_aWarn(`droits d'administration et responsabilités ne s'appliquent qu'aux connexions faites <b>avec le mot de passe</b> que l'enseignant a lui-même défini :
            ils peuvent être accordés avant, mais restent « inactifs » (étiquette en pointillé dans la liste). Réinitialiser ou révoquer le mot de passe les suspend sans les retirer.`)}
        <p>Dans la liste, le superadmin voit les étiquettes ${_aCode('admin', 'background:#dcfce7;color:#166534')} et ${_aCode('resp. FTP', 'background:#ede9fe;color:#5b21b6')} à côté des noms.</p>` },

    { id: 'salles', rub: R, titre: 'Les salles', chemin: 'Salles', onglet: 'nav:salles', cible: 'salles',
      mots: 'salle capacité type ajouter conflit',
      html: `
        <p>La liste des salles de l'année active : <b>nom</b>, <b>type</b>, <b>capacité</b>. Elles se choisissent pour chaque type d'enseignement dans
        ${_aLien('matieres', 'Service › Matières')}, filtrent la ${_aLien('rep-annuelle', 'répartition')} et servent au ${_aUi('Contrôle')} des conflits de salle.</p>` },

    { id: 'parametres', rub: R, titre: 'Paramètres du site', chemin: 'Paramètres', onglet: 'nav:parametres', cible: 'parametres',
      mots: 'paramètres année active coefficients hetd accès aux onglets voir modifier profils réglage',
      html: () => `
        ${_aSuper(`<h3>Année universitaire active</h3>
        <p>L'année de travail de tous les onglets (sauf le Service, qui a son propre sélecteur). ${_aUi('Appliquer')} la change pour tout le monde.
        Voir ${_aLien('annees', 'les années')} et le pas-à-pas ${_aLien('ex-annee', 'changer d\'année')}.</p>
        <h3>Coefficients de conversion en HETD</h3>
        <p>Une heure de chaque type multipliée par son coefficient, pour le ${_aLien('bilan', 'Bilan Global')} et la colonne Heures des matières.
        Valeurs usuelles : CM 1,5 · TD 1 · TP 0,667 (2/3) · PT 1.</p>
        <h3>Accès aux onglets</h3>
        <p>Un tableau : les onglets en lignes, les profils en colonnes (Admin, Resp. FTP, Resp. ALT, Resp. stages, Enseignant avec mdp, Enseignant sans mdp),
        avec pour chacun <b>Voir</b> (l'onglet s'affiche) et <b>Modif.</b> (on peut y enregistrer — contrôlé par le serveur).</p>
        <ul>
            <li>Fond jaune : fermé par défaut à ce profil ; « — » : sans objet.</li>
            <li>Un enseignant connecté <b>sans</b> mot de passe ne peut recevoir aucun droit de modification : n'importe qui peut se connecter sous son nom.</li>
            <li>Un onglet dont tous les sous-onglets sont décochés disparaît — l'aide de cet onglet aussi.</li>
            <li>${_aUi('💾 Enregistrer les accès')} ; pris en compte à la prochaine connexion, ou au rechargement de la page.</li>
        </ul>
        <p>Le tableau des accès en vigueur est rappelé dans ${_aLien('sessions', 'Profils, sessions et droits')}.</p>`)}
        <h3>Sauvegarde complète du site</h3>
        <p>${_aUi('⤓ Télécharger la sauvegarde')} : voir ${_aLien('sauvegardes', 'Sauvegardes et restauration')}.</p>` },

    { id: 'sauvegardes', rub: R, titre: 'Sauvegardes et restauration', chemin: 'Paramètres', onglet: 'nav:parametres', cible: 'parametres',
      mots: 'sauvegarde backup zip restaurer restauration copie de sécurité avant-import automatique quotidienne',
      html: () => `
        <h3>La sauvegarde complète (.zip)</h3>
        <p>${_aOng('Paramètres')} → ${_aUi('⤓ Télécharger la sauvegarde')} : <b>toutes</b> les données du site en un fichier — bases de toutes les années
        (enseignants, matières, salles, emplois du temps), promotions et effectifs (étudiants, notes, jury, tuteurs, photos), programmes, fichiers de notes
        et de contraintes, réglages et coefficients. Conservez-la <b>hors du serveur</b>.</p>
        ${_aSuper(`<p>${_aUi('⤒ Restaurer depuis un fichier…')} <b>écrase</b> les données actuelles par celles du fichier ; une copie de l'existant
        (« avant-import ») est mise de côté sur le serveur juste avant. La sauvegarde porte un inventaire de son contenu : après restauration, le site
        recompte ce qu'il a en base et signale tout écart.</p>`)}
        <h3>Les sauvegardes automatiques</h3>
        <p>Chaque jour, la base de chaque année modifiée est copiée automatiquement (les 5 plus récentes de chaque année sont gardées).${_aSuper(` ${_aOng('Journal')} les liste, avec
        ${_aUi('Créer une sauvegarde maintenant')}, ${_aUi('Restaurer')} et ${_aUi('Supprimer')}.`)}</p>
        ${_aWarn(`ces copies quotidiennes ne contiennent que la base <b>d'une année</b> (enseignants, matières, salles, emploi du temps) : les promotions,
            les notes et les photos ne sont que dans la sauvegarde complète. Téléchargez-la régulièrement, et toujours avant une opération lourde
            (restauration, changement d'année, import massif).`)}` },

    { id: 'journal', rub: R, titre: 'Journal : sauvegardes et activité', chemin: 'Journal', onglet: 'nav:journal', cible: 'journal',
      mots: 'journal audit activité connexions échecs modifications traçabilité sauvegardes',
      html: `
        <p>Réservé au superadmin, en deux sous-onglets :</p>
        <ul>
            <li>${_aUi('Sauvegardes')} : les copies automatiques de la base de chaque année — les <b>5 dernières</b> de chaque année sont gardées,
                les plus anciennes sont effacées —, avec ${_aUi('Créer une sauvegarde maintenant')}, ${_aUi('Restaurer')} et ${_aUi('Supprimer')}
                (${_aLien('sauvegardes', 'détail')}).</li>
            <li>${_aUi('Activité')} : connexions, échecs et blocages, modifications (qui, quand, depuis quelle adresse, sur quel écran). Filtres :
                ${_aUi('Type')} (Connexions, Échecs / blocages, Modifications), recherche (adresse IP, utilisateur, chemin…), nombre de lignes
                (200 à 2000), ${_aUi('Rafraîchir')}.</li>
        </ul>` },

    { id: 'mon-compte', rub: R, titre: 'Mon Compte', chemin: 'Mon Compte', onglet: 'nav:mon-compte', cible: 'mon-compte',
      mots: 'mon compte coordonnées email téléphone employeur préférence de contact heures hors gim hetd privé public',
      html: `
        <p>L'onglet de chaque enseignant, pour l'année active :</p>
        <h3>Mes coordonnées</h3>
        <p>E-mail, téléphone, employeur et <b>préférence de contact</b> (texte libre, visible dans la liste des enseignants : « de préférence par mail, pas le mercredi »).
        Nom, corps et statut sont gérés par l'administration.</p>
        <h3>Heures hors GIM</h3>
        <p>Les heures (en HETD) faites dans un autre département ou établissement : intitulé, nombre d'HETD, ${_aUi('+ Ajouter')}. Elles s'ajoutent à votre
        ${_aLien('bilan', 'Bilan Global')} et au calcul de vos heures complémentaires.</p>
        <ul>
            <li><b>Privé</b> (par défaut) : visible par vous seul ;</li>
            <li><b>Public</b> : visible aussi par l'administration — jamais par les autres enseignants. ${_aUi('🔒')} / ${_aUi('👁')} basculent une ligne.</li>
        </ul>
        ${_aEx('déclarer des heures', `« Dépt GEII, IUT de Toulon » — 24 HETD — Public : l'administration les voit dans votre Bilan Global, vos collègues non.`)}` },
    ];
}

function _aideExemples() {
    const R = 'exemples';
    // Chaque pas-à-pas ne garde que les étapes que la session peut faire (_aSi, _aSiModif)
    return [
    { id: 'ex-rentree', rub: R, titre: "Préparer la rentrée d'une nouvelle promotion", onglet: 'promo:effectif', pour: 'modifier',
      mots: 'rentrée septembre nouvelle promotion préparer effectif parcoursup groupes trombinoscope',
      html: () => `
        ${_aSteps([
            _aSiModif('promo:actions', `<b>Créer la promotion</b> — ${_aOng('Promotions › Actions')}, ${_aUi('+ Nouvelle promotion')}, année de rentrée 2027 → « 27-30 ».
             Les trois années universitaires qu'elle couvre sont créées au besoin, chacune à partir de l'année précédente. ${_aLien('promo-actions', 'Détail')}`),
            _aSiModif('promo:actions', `<b>La rattacher à son programme</b> — ${_aOng('Effectifs')}, liste ${_aUi('Programme')} en tête de page. ${_aLien('prog-vue', 'Détail')}`),
            `<b>Importer l'effectif</b> — section FTP puis section ALT, ${_aUi('Importer un effectif')} avec le PV ou l'export Apogée de rentrée. ${_aLien('promo-import', 'Détail')}`,
            `<b>Compléter avec ParcourSup</b> — ${_aUi('⤒ Importer ParcourSup')} : classement STI2D, puis hors STI2D, puis l'export CSV complet pour les dossiers ;
             les étudiants restés sans dossier se complètent sur leur fiche.`,
            _aSiModif('etu:liste',`<b>Les photos</b> — ${_aOng('Étudiants')}, ${_aUi('Importer un trombi (PDF)')} avec les trombinoscopes de la scolarité. ${_aLien('etu-trombi-import', 'Détail')}`),
            _aSiModif('promo:groupes', `<b>Les groupes</b> — ${_aOng('Groupes')} : nombre de groupes du S1, ${_aUi('⚙ Répartition automatique')}, ${_aUi('✓ Vérifier les règles')},
             ${_aUi('⤓ Télécharger')} pour les enseignants. ${_aLien('promo-groupes', 'Détail')}`),
            _aSiModif('promo:calendrier', `<b>Le calendrier</b> — ${_aOng('Calendrier')} : dates des semestres, vacances, stages, semaines en entreprise. ${_aLien('promo-calendrier', 'Détail')}`),
            `<b>Le trombinoscope</b> — ${_aOng('Effectifs')}, ${_aUi('⤓ Trombi (PDF)')}, à diffuser à l'équipe.`])}` },

    { id: 'ex-edt', rub: R, titre: "Construire l'emploi du temps d'un semestre", onglet: 'rep:annuelle', pour: 'modifier',
      mots: 'emploi du temps edt planning semestre préparer construire hyperplanning répartition',
      html: () => `
        ${_aSteps([
            _aSi(['promo:calendrier', 'promo:groupes'], `<b>Le cadre</b> — ${[
                _aSi('promo:calendrier', `${_aOng('Promotions › Calendrier')} (semaines de cours, vacances, stages, entreprise)`),
                _aSi('promo:groupes', `${_aOng('Promotions › Groupes')} (nombre de groupes, semestres mutualisés)`)].filter(Boolean).join(' et ')}.`),
            _aSi('svc:contraintes', `<b>Les contraintes</b> — les enseignants remplissent ${_aOng('Service › Contraintes Enseignant')}${
                _aSi('svc:contraintes-matiere', ` ; les contraintes de matière se notent dans ${_aOng('Contraintes Matière')}`)}.`),
            _aSiModif('svc:matieres', `<b>Les matières</b> — ${_aOng('Service › Matières')} : pour chaque sous-matière, volumes, durée de séance, salle, enseignant (par groupe si besoin). ${_aLien('matieres', 'Détail')}`),
            `<b>La répartition annuelle</b> — choisissez les semestres, placez les heures semaine par semaine avec ${_aUi('▲')} ${_aUi('▼')} jusqu'à ce que chaque ${_aUi('Reste')} soit à zéro,
             en surveillant les taux horaires des promos. ${_aLien('rep-annuelle', 'Détail')}`,
            `<b>Contrôler</b> — ${_aUi('Contrôle')} (charge des enseignants, conflits de salle) et ${_aUi('Ordonnancement')} ; corrigez, puis ${_aUi('Enregistrer')}.`,
            `<b>Diffuser</b> — ${_aUi('Export Excel')} de la répartition.`,
            _aSi('rep:jour', `<b>Semaine par semaine</b> — ${_aOng('Répartition journalière')} : pour chaque semaine et chaque cohorte, déposez les cours dans Hyperplanning, cochez
             ${_aUi('Posée à l\'EDT')}, puis ${_aUi('Optimisée')}. Le bandeau dit ce qu'il reste. ${_aLien('rep-jour', 'Détail')}`),
            _aSi('svc:comparaison', `<b>Vérifier</b> — ${_aOng('Service › Comparaison')} avec l'état récapitulatif d'Hyperplanning. ${_aLien('comparaison', 'Détail')}`)])}
        ${_aTip(`pour préparer l'année suivante pendant que l'année en cours tourne, choisissez-la dans la liste ${_aUi('Année')} du Service : rien ne change pour les autres.`)}` },

    { id: 'ex-notes', rub: R, titre: 'Saisir ses notes', onglet: ['nav:saisie', 'promo:saisie'],
      mots: 'saisir notes enseignant devoir ds tp moyenne définitif excel',
      html: () => `
        ${_aSteps([
            _aSi('nav:saisie', `Onglet ${_aOng('Saisie Notes')} : vos grilles de l'année s'affichent. Filtrez par matière ou par semestre ; repliez celles qui sont finies.`)
                || `${_aOng('Promotions › Saisie Notes')} : choisissez la promotion, la sous-cohorte et le semestre.`,
            `Tapez les notes (0 à 20, ou ABI pour une absence injustifiée) dans vos colonnes — ou ${_aUi('⤓ Modèle vide')}, remplissez sous Excel, ${_aUi('⤒ Importer')}.`,
            `Si vous êtes <b>référent</b> de la matière, réglez les pondérations des sous-matières (0 = exclue).`,
            `${_aUi('💾 Enregistrer')}. La moyenne pondérée part dans les Bulletins (matière en mode 🧮).`,
            `Quand vos notes sont finales, cochez <b>définitif</b> en tête de vos colonnes.`])}
        ${_aLien('promo-saisie', 'Tout sur la saisie des notes')}` },

    { id: 'ex-jury', rub: R, titre: 'Préparer et tenir un jury', onglet: 'promo:jury', pour: 'modifier',
      mots: 'jury préparer tenir fin d\'année semestre décisions devenir pv apogée',
      html: () => `
        ${_aSteps([
            _aSi('promo:notes', `<b>Les notes sont-elles complètes ?</b> — ${_aOng('Promotions › Bulletins')}, chaque semestre de l'année : bandeau « moyennes incomplètes », matières 📥/🧮 et écarts ⚠. ${_aLien('promo-bulletins', 'Détail')}`),
            _aSiModif('promo:notes', `<b>Les cas particuliers</b> — pénalités d'assiduité, bonus, VAQ, mobilités (MI), mentions ABI et N.`),
            _aSiModif('promo:notes', `${_aUi('💾 Enregistrer les notes')} ; au besoin, ${_aUi('Importer les notes')} d'Apogée en préservant les saisies définitives.`),
            `<b>Le jury</b> — ${_aOng('Jury')}, l'année et la sous-cohorte : vérifiez les codes d'UE, posez les ${_aUe('ADMJ')} et les ${_aDec('RED')} décidés, ${_aUi('💾 Enregistrer les décisions')}. ${_aLien('promo-jury', 'Détail')}`,
            _aSiModif('promo:devenir', `<b>Le devenir</b> — ${_aOng('Devenir')} : poursuite FTP/ALT, réinscription des redoublants, césures, départs ; arbitrage des UE des redoublants accueillis. ${_aLien('promo-devenir', 'Détail')}`),
            _aSi('promo:effectif', `<b>L'année suivante</b> — elle se compose seule : ${_aOng('Effectifs')}, année N+1${_aSiModif('promo:effectif', ' (ajustez si besoin)')}.`),
            _aSiModif('promo:notes', `<b>Pour Apogée</b> — ${_aUi('⬇ Exporter (.xlsx)')} dans les Bulletins.`)])}` },

    { id: 'ex-redoublant', rub: R, titre: "Suivre un redoublant d'une cohorte à l'autre", onglet: 'promo:devenir', pour: 'modifier',
      mots: 'redoublant redoublement red réinscription cohorte suivante meilleure note arbitrage',
      html: () => `
        ${_aSteps([
            `Au jury de l'année 2 de 25-28, l'étudiant est ajourné : le jury pose ${_aDec('RED')}.`,
            `${_aOng('Devenir')} de 25-28, année jugée 2 : « RED → FTP » (ou ALT). Il est réinscrit en <b>26-29, année 2</b> ; sa fiche au registre (identité, dossier, photo) le suit.`,
            _aSi('promo:effectif', `Dans 26-29, ${_aOng('Effectifs')} année 2 : il apparaît avec la pastille ${_aCode('redoublant', 'background:#ddd6fe')}.`),
            `Ses notes de l'année refaite s'ajoutent ; pour chaque UE, la <b>meilleure</b> des deux moyennes compte (repère ↺), sauf arbitrage contraire du jury
             dans le ${_aOng('Devenir')} de 26-29 (« redoublants accueillis » : auto, précédent, refaite).`])}` },

    { id: 'ex-tuteurs', rub: R, titre: 'Attribuer les tuteurs et suivre ses étudiants', onglet: ['nav:stages', 'nav:alternance'],
      mots: 'tuteur attribuer stage alternance entreprise suivre étudiants',
      html: () => `
        ${_aSteps([
            `${[_aSi('nav:stages', `${_aOng('Stages')} (stagiaires FTP 2<sup>e</sup>-3<sup>e</sup> année)`),
                _aSi('nav:alternance', `${_aOng('Alternance')} (alternants)`)].filter(Boolean).join(' ou ')} : choisissez l'année universitaire.`,
            `Cochez ${_aUi('À compléter seulement')} : il ne reste que les fiches incomplètes.`,
            `Un clic sur un étudiant : entreprise (choisie dans la liste si elle est connue), lieu, tuteur entreprise et ses coordonnées, mission.`,
            `Le responsable (ou l'administration) choisit le <b>tuteur universitaire</b> ; le sous-onglet ${_aUi('Statistiques')} montre la charge de chacun.`,
            `Un enseignant tuteur coche ${_aUi('Mes suivis')} pour retrouver ses étudiants et compléter leurs fiches.`])}
        ${_aLien('suivi-fiches', 'Tout sur les fiches de suivi')}` },

    { id: 'ex-service', rub: R, titre: 'Vérifier son service et donner ses contraintes', onglet: 'svc:repartition-enseignant',
      mots: 'vérifier mon service heures complémentaires contraintes enseignant hors gim',
      html: () => `
        ${_aSteps([
            `${_aOng('Service › Bilan Global')} : votre nom est présélectionné ; vérifiez chaque matière, le nombre de groupes et le total d'HETD.`,
            _aSi('nav:mon-compte', `Des heures dans un autre département ? Déclarez-les dans ${_aOng('Mon Compte')} (privées ou visibles par l'administration).`),
            `Lisez vos heures complémentaires (titulaire dont le corps est renseigné).`,
            _aSi('svc:contraintes', `Pour l'an prochain : liste ${_aUi('Année')} du Service → année suivante, puis ${_aOng('Contraintes Enseignant')} : texte et/ou fichier.`),
            `Une erreur dans votre service ? Signalez-la à l'administration ou au responsable FTP.`])}` },

    { id: 'ex-acces', rub: R, titre: "Ouvrir l'accès d'un enseignant", onglet: 'nav:enseignants', pour: 'superadmin',
      mots: 'ouvrir accès enseignant mot de passe droits responsable admin',
      html: `
        ${_aSteps([
            `${_aOng('Enseignant')} → ${_aUi('Éditer')} sur sa ligne → ${_aUi('Autoriser la création du mot de passe')}.`,
            `Prévenez-le : sur l'écran de connexion, il tape son nom de famille, clique ${_aUi('Initialiser mon mot de passe')} et choisit son mot de passe.`,
            `S'il a des responsabilités, cochez-les (Formation FTP, Formation ALT, Stages) ; s'il administre, cochez <b>Droits d'administration</b>.`,
            `À sa prochaine connexion avec mot de passe, il choisit sa session (admin ou normale).`,
            `Pour affiner ce que chaque profil voit et modifie : ${_aOng('Paramètres › Accès aux onglets')}.`])}
        ${_aLien('enseignants-acces', 'Détail des accès')}` },

    { id: 'ex-annee', rub: R, titre: "Passer à une nouvelle année universitaire", onglet: 'nav:parametres', pour: 'superadmin',
      mots: 'nouvelle année universitaire basculer changer d\'année active septembre',
      html: `
        ${_aSteps([
            `<b>Sauvegarder</b> — ${_aOng('Paramètres')}, ${_aUi('⤓ Télécharger la sauvegarde')} complète.`,
            `<b>Préparer</b> — la base de la nouvelle année existe dès qu'une promotion la couvre (elle part d'une copie de l'année précédente : enseignants,
             matières, salles…). Préparez-la à l'avance depuis le Service (liste ${_aUi('Année')}) : enseignants arrivés ou partis, matières, volumes.`,
            `<b>Basculer</b> — le moment venu, ${_aOng('Paramètres')} → ${_aUi('Année universitaire active')} → ${_aUi('Appliquer')} : tout le site travaille sur la nouvelle année.`,
            `<b>Vérifier</b> — le sélecteur des promotions affiche la nouvelle année de chaque cohorte (BUT1, BUT2, BUT3, OLD).`])}` },
    ];
}

function _aideFaq() {
    const R = 'faq';
    // onglet : la question ne se pose qu'aux sessions qui ouvrent cet écran ; pour :
    // 'modifier' quand elle décrit un geste réservé à ceux qui peuvent y enregistrer
    const q = (id, titre, mots, html, onglet, pour) => ({ id: 'faq-' + id, rub: R, titre, mots, html,
                                                          onglet: onglet || null, pour: pour || null });
    return [
    q('onglet', 'Je ne vois pas un onglet', 'onglet absent manquant caché invisible',
        () => `<p>Les raisons possibles :</p>
        <ul>
            ${state.role === 'teacher' && !state.promoAccess ? `<li>vous êtes connecté <b>sans mot de passe</b> : une partie des onglets demande une
                connexion avec mot de passe (${_aLien('connexion', 'voir')}) ;</li>` : ''}
            <li>votre <b>profil</b> ne l'ouvre pas (${_aLien('sessions', 'profils et droits')}) — ou vous êtes dans la mauvaise <b>session</b> :
                un enseignant administrateur doit passer en session admin ;</li>
            <li>le superadmin l'a fermé à votre profil.</li>
        </ul>`),
    q('mdp', "J'ai oublié mon mot de passe (ou le bouton « Initialiser » n'apparaît pas)", 'mot de passe oublié perdu initialiser bouton absent',
        `<p>Il n'y a pas de récupération par e-mail. Demandez à l'administration de <b>réinitialiser</b> votre mot de passe : en tapant votre nom sur l'écran de
        connexion, le bouton ${_aUi('Initialiser mon mot de passe')} apparaît alors. S'il n'apparaît pas, c'est que la création n'a pas été autorisée, ou qu'un
        mot de passe existe déjà : là encore, c'est l'administration qui débloque.</p>`),
    q('annee', 'Je ne vois pas les données attendues : quelle année est affichée ?', 'année mauvaise année données manquantes vide',
        () => {
            const ou = [
                _aSi('nav:service', `la liste ${_aUi('Année')} du ${_aOng('Service')} (propre au Service)`),
                _aSi('nav:promotions', `l'${_aUi('Année de la cohorte')} dans les ${_aOng('Promotions')}`),
                _aSi(['nav:stages', 'nav:alternance'], `l'${_aUi('Année universitaire')} du suivi des stages et de l'alternance`),
            ].filter(Boolean);
            return `<p>${ou.length ? `Vérifiez l'année affichée : ${ou.join(', ')} — le reste suit l'année active.`
                                   : `Le site affiche l'année universitaire active, réglée par le superadmin.`}
                ${_aLien('annees', 'Les années, en détail')}</p>`;
        }),
    q('disparu', "Un étudiant n'apparaît plus dans l'effectif", 'étudiant disparu absent effectif année suivante introuvable',
        () => `<p>Dans l'effectif d'une année, il manque normalement :</p>
        <ul>
            <li>les <b>ajournés</b> et <b>redoublants</b> de l'année précédente (${_aDec('AJ')} ${_aDec('RED')}) — ils restent visibles sur l'année qu'ils ont faite, et un redoublant
                est réinscrit dans la cohorte suivante par le ${_aLien('promo-devenir', 'Devenir')} ;</li>
            <li>les <b>abandons</b>, <b>césures</b>, <b>retraits</b> (⊘) et ceux qui entrent plus tard : ils sont dans « <b>Autres fiches de la cohorte</b> », en bas
                de l'effectif, avec la raison${_aSiModif('promo:effectif', ` et le bouton ${_aUi('↩')} pour réintégrer`)}.</li>
        </ul>
        ${_aSi('nav:etudiants', `<p>Pour retrouver quelqu'un sans savoir où il est : ${_aOng('Étudiants')}, recherche par nom ou n° Apogée.</p>`)}`, 'promo:effectif'),
    q('supprimer', 'Retirer ou supprimer un étudiant : lequel choisir ?', 'retirer supprimer étudiant fiche effacer abandon',
        `<ul>
            <li>Il <b>arrête</b> la formation : statut ${_aStatut('Abandon')} avec la semaine, ou ${_aUi('⊘')} (retiré à partir de l'année affichée). Ses notes passées restent.</li>
            <li>La fiche est une <b>erreur</b> (doublon, mauvais import) : ${_aUi('🗑')} — elle disparaît des trois années avec toutes ses notes, <b>sans retour</b>.</li>
        </ul>`, 'promo:effectif', 'modifier'),
    q('note-absente', "Ma moyenne n'arrive pas dans les Bulletins", 'moyenne pas reportée bulletins note matière importée calculée',
        `<p>Trois vérifications :</p>
        <ul>
            <li>avez-vous <b>enregistré</b> (${_aUi('💾 Enregistrer')}) ?</li>
            <li>toutes les sous-notes sont-elles saisies ? Tant qu'il en manque une, la moyenne n'est pas calculable ;</li>
            <li>la matière est-elle en mode <b>📥 importée</b> ? Après un import Apogée ou une saisie de l'administration, la moyenne de la saisie n'est plus reportée :
                demandez à l'administration de rebasculer la matière en <b>🧮 calculée</b>.</li>
        </ul>`, ['nav:saisie', 'promo:saisie']),
    q('notes-perdues', 'Mes notes ont disparu après rechargement', 'notes perdues disparues non enregistrées invalide',
        `<p>Les notes de la saisie ne s'enregistrent qu'avec ${_aUi('💾 Enregistrer')}. Une valeur qui n'est ni une note de 0 à 20, ni ABI, est refusée et signalée.
        En quittant une grille modifiée, le site propose toujours d'enregistrer (${_aLien('enregistrer', 'voir')}) — sauf si l'on ferme brutalement l'onglet du navigateur.</p>`,
        ['nav:saisie', 'promo:saisie']),
    q('incomplete', "Une moyenne d'UE est marquée « incomplète »", 'moyenne incomplète provisoire manquante bandeau',
        `<p>Elle est calculée alors que des notes manquent : elle est <b>provisoire</b>. Le bandeau des ${_aLien('promo-bulletins', 'Bulletins')} cite les matières
        absentes, les plus fréquentes d'abord. Une matière neutralisée (N) ou une UE validée par acquis (VAQ) ne comptent pas comme manquantes : leur mise hors calcul est voulue.</p>`, 'promo:notes'),
    q('orange', 'Pourquoi des semaines sont orange dans la répartition ?', 'orange semaine couleur vacances stage entreprise répartition',
        `<p>Ce sont des semaines de <b>vacances</b> ou de <b>stage</b> (FTP) ou en <b>entreprise</b> (ALT), d'après le ${_aLien('promo-calendrier', 'calendrier')} de la promotion :
        on évite d'y placer des heures.</p>`, 'rep:annuelle'),
    q('reste', 'Le « Reste » est en rouge', 'reste rouge total h module heures à placer',
        `<p>Les heures placées ne font pas encore le volume prévu (${_aUi('H. module')}) : il en manque, ou il y en a trop (reste négatif). Le reste compte toutes les semaines,
        même celles qu'un filtre (Impair / Pair) masque.</p>`, 'rep:annuelle'),
    q('erreur-rep', "J'ai fait une erreur dans la répartition", 'erreur annuler retour arrière abandonner répartition brouillon',
        `<p>Tant que ce n'est pas enregistré : ${_aUi('↶ Retour arrière')} (<kbd>Ctrl</kbd>+<kbd>Z</kbd>) clic par clic, ou ${_aUi('Abandonner')} pour revenir à la version enregistrée.
        Après enregistrement : corrigez les cases à la main, ou demandez au superadmin de restaurer une sauvegarde de l'année.</p>`, 'rep:annuelle', 'modifier'),
    q('ftp-alt', "Un étudiant passe de FTP en alternance (ou l'inverse)", 'passer ftp alt alternance changement sous-cohorte bascule',
        () => `<p>En cours de cursus : ${_aOng('Effectifs')}, l'année à partir de laquelle il change, bouton ${_aUi('⇄ ALT')} sur sa ligne — les années précédentes gardent leur sous-cohorte.
        ${_aSi('promo:devenir', `Après un jury : le ${_aLien('promo-devenir', 'Devenir')} (« poursuite en ALT »).`)}
        ${_aSi('nav:alternance', `Pensez ensuite à sa fiche dans ${_aOng('Alternance')}.`)}</p>`, 'promo:effectif', 'modifier'),
    q('mobilite', "Un étudiant part un semestre à l'étranger", 'mobilité internationale étranger semestre erasmus cégep équivalence',
        `<p>${_aOng('Effectifs')}, colonne <b>MI</b> : choisissez le semestre, puis l'établissement d'accueil. Ses UE de ce semestre sont validées par équivalence, sans note ;
        il reste dans l'effectif, et sa moyenne annuelle ne retient que l'autre semestre.</p>`, 'promo:effectif', 'modifier'),
    q('cesure', 'Un étudiant prend une césure', 'césure année blanche interruption reprise',
        `<p>La césure se décide dans le ${_aLien('promo-devenir', 'Devenir')}, après le jury de l'année qui la précède : il sort de l'effectif de l'année de césure et reprend cette année-là dans la
        cohorte suivante, dans la sous-cohorte choisie (section « Césures »). Le statut ${_aStatut('Césure')} ne se pose pas depuis les Effectifs.</p>`, 'promo:devenir'),
    q('photo', 'Une photo manque ou ne correspond pas', 'photo absente fausse mauvaise trombinoscope changer',
        `<p>Sur la fiche de l'étudiant : ${_aUi('Changer')} (ou ${_aUi('Ajouter')}) avec la bonne image, ou ${_aUi('✕')} pour la retirer. Lors d'un import de trombinoscope, vérifiez les lignes
        sur fond jaune avant d'associer : c'est là que se glissent les erreurs. ${_aLien('etu-trombi-import', 'Import des photos')}</p>`, 'etu:liste', 'modifier'),
    q('hors-gim', 'Qui voit mes heures hors GIM ?', 'heures hors gim confidentialité privé public',
        `<p>Une ligne <b>privée</b> : vous seul. Une ligne <b>publique</b> : vous et l'administration — jamais les autres enseignants. ${_aLien('mon-compte', 'Mon Compte')}</p>`,
        'nav:mon-compte'),
    q('grise', 'Les cases sont grisées, je ne peux rien modifier', 'grisé lecture seule consultation bloqué modifier impossible',
        `<p>Votre session consulte l'écran sans droit de modification (ou la colonne, la fiche, est celle d'un collègue). Les pastilles en tête de chaque section
        de l'aide disent qui peut modifier l'écran qu'elle décrit.</p>`),
    q('sauvegarde', 'Mes données sont-elles sauvegardées ?', 'sauvegarde perte données sécurité backup',
        `<p>La base de chaque année est copiée automatiquement chaque jour (5 copies gardées par année). La sauvegarde <b>complète</b> — la seule qui contienne aussi les promotions,
        les notes et les photos — se télécharge depuis ${_aOng('Paramètres')} : à faire régulièrement. ${_aLien('sauvegardes', 'Détail')}</p>`, 'nav:parametres'),
    ];
}

function _aideGlossaire() {
    const R = 'glossaire';
    const g = (id, titre, termes) => ({ id: 'glo-' + id, rub: R, titre, mots: 'glossaire définition sigle',
        html: `<dl>${termes.map(([t, d]) => `<dt>${t}</dt><dd>${d}</dd>`).join('')}</dl>` });
    return [
    g('formation', 'Formations et cohortes', [
        ['BUT', 'Bachelor universitaire de technologie, en trois ans (BUT1, BUT2, BUT3), six semestres S1 à S6.'],
        ['GIM', 'Génie Industriel et Maintenance, le département.'],
        ['Promotion, cohorte', 'Les étudiants entrés la même année, suivis sur trois ans ; nommée par ses années (26-29).'],
        ['Sous-cohorte', 'FTP ou ALT, à l\'intérieur d\'une promotion ; elle peut changer d\'une année à l\'autre.'],
        ['FTP', 'Formation à temps plein (formation initiale), avec des stages.'],
        ['ALT', 'Alternance (apprentissage) : périodes à l\'IUT et en entreprise.'],
        ['MUT', 'Mutualisé : enseignement commun à FTP et ALT.'],
        ['Année de la cohorte', 'Année d\'étude (1, 2 ou 3) d\'une promotion, qui correspond à une année universitaire.'],
        ['Année active', 'L\'année universitaire de travail du site, réglée par le superadmin.'],
        ['Registre', 'La liste des étudiants en tant que personnes (onglet Étudiants), une fiche par personne quelles que soient ses cohortes.'],
    ]),
    g('enseignement', 'Enseignement et service', [
        ['CM, TD, TP, PT', 'Cours magistral, travaux dirigés, travaux pratiques, projet tutoré.'],
        ['TP12, TP8', 'Travaux pratiques en groupes de 12 ou de 8 étudiants.'],
        ['Ressource', 'Matière d\'enseignement (code R1.01…).'],
        ['SAÉ', 'Situation d\'apprentissage et d\'évaluation, le projet du BUT (code SAE1.01…).'],
        ['Sous-matière', 'Une partie d\'une matière confiée à un enseignant ou évaluée à part (R1.03a, R1.03b…).'],
        ['Référent', 'L\'enseignant qui fixe les pondérations des sous-matières d\'une matière.'],
        ['HETD', 'Heure équivalent TD : l\'unité du service (CM × 1,5, TD × 1, TP × 2/3, PT × 1 par défaut).'],
        ['Service statutaire', '192 HETD pour un MCF, 384 HETD pour un PRAG, un PRCE ou un PLP.'],
        ['Heures complémentaires', 'HETD faites au-delà du service statutaire (titulaires).'],
        ['Heures hors GIM', 'Heures faites dans un autre département ou établissement, déclarées dans Mon Compte.'],
        ['PN', 'Programme national : la maquette officielle du BUT (matières, volumes, contenus).'],
        ['Taux horaire', 'Heures de cours d\'un étudiant d\'une promo dans une semaine.'],
        ['Posée, optimisée', 'Avancement d\'une semaine dans l\'emploi du temps : cours déposés, puis placement fait.'],
    ]),
    g('notes', 'Notes, UE et jury', [
        ['UE', 'Unité d\'enseignement : une compétence sur un semestre. Cinq compétences en GIM (UE1 à UE5).'],
        ['Moyenne annuelle d\'UE', 'Moyenne des deux semestres de la compétence sur l\'année : c\'est elle qui fait le code d\'UE.'],
        ['Acquise, compensée', 'Une UE de semestre est acquise à 10 ; compensée si la moyenne annuelle de sa compétence atteint 10.'],
        ['UE terminale', 'UE sans niveau l\'année suivante : elle doit être validée pour un passage AJAC.'],
        ['GIM1, GIM2, GIM3', 'Moyenne générale de l\'année (moyenne des moyennes annuelles d\'UE).'],
        [_aDec('ADM'), 'Admis.'],
        [_aDec('ADMJ'), 'Admis par décision du jury (aussi un code d\'UE).'],
        [_aDec('AJAC'), 'Ajourné mais autorisé à continuer (passage avec dettes).'],
        [_aDec('AJ'), 'Ajourné.'],
        [_aDec('RED'), 'Redoublant.'],
        [_aUe('CMP'), 'UE validée parce que validée à un niveau supérieur.'],
        ['ABI', 'Absence injustifiée : la note vaut 0.'],
        ['N', 'Matière neutralisée (faute d\'enseignant) : hors moyenne.'],
        ['VAQ', 'Validation par acquis d\'une UE : elle sort du calcul de l\'année pour ce semestre.'],
        ['MI', 'Mobilité internationale : semestre à l\'étranger, UE validées par équivalence.'],
        ['Bonus', 'Bonification (sport, art…) ajoutée à la moyenne annuelle de chaque UE, 0,5 point au plus.'],
        ['Pénalité d\'assiduité', 'Malus retiré de chaque UE du semestre au-delà de 8 h d\'absence injustifiée.'],
        ['Provisoire, définitif', 'État des notes d\'une colonne de saisie, choisi par son enseignant.'],
        ['🧮 calculée, 📥 importée', 'Origine de la note d\'une matière : moyenne de la saisie, ou note importée / saisie par l\'administration.'],
    ]),
    g('parcours', 'Statuts et parcours', [
        [_aStatut('Actif'), 'Suit la formation.'],
        [_aStatut('Abandon'), 'A quitté la formation (avec la semaine).'],
        [_aStatut('RED'), 'Redoublant, d\'après le jury.'],
        [_aStatut('Césure'), 'Interrompt sa formation une année, décidée dans le Devenir.'],
        ['Devenir', 'Ce que fait l\'étudiant après le jury : poursuite, redoublement, césure, autre formation, insertion, départ.'],
        ['Report du jury', 'Composition automatique de l\'effectif d\'une année à partir des décisions de l\'année précédente.'],
        ['Entrant', 'Étudiant entré directement en année 2 ou 3.'],
        ['Tuteur universitaire', 'L\'enseignant qui suit un stagiaire ou un alternant.'],
        ['Tuteur entreprise', 'Le correspondant de l\'étudiant dans l\'entreprise.'],
    ]),
    g('outils', 'Outils et fichiers', [
        ['Apogée', 'Le logiciel de scolarité : n° Apogée de l\'étudiant, exports d\'effectif et de notes.'],
        ['ParcourSup', 'La plateforme de candidature : classement, dossier, note globale.'],
        ['eCandidat, ADIUT', 'Autres voies de candidature (eCandidat ; ADIUT pour les candidats étrangers). HP : hors procédure.'],
        ['PV de jury', 'Le procès-verbal (tableur) du jury, importable comme effectif ou comme notes.'],
        ['Hyperplanning', 'Le logiciel d\'emploi du temps de l\'IUT, comparé dans Service › Comparaison.'],
        ['Brouillon', 'Copie de travail de la répartition annuelle, enregistrée d\'un bloc.'],
        ['Trombinoscope', 'Les photos d\'une promotion, à l\'écran ou en PDF.'],
    ]),
    ];
}
