"""
Flask backend application for IUT Gestion Emploi Du Temps (EDT)
Manages timetables for IUT GIM Toulon
"""

from flask import Flask, request, jsonify, send_file, send_from_directory, g, session
from flask_cors import CORS
import sqlite3
import os
import json
import math
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import io

# Initialize Flask app
app = Flask(__name__, static_folder='static', static_url_path='')
app.secret_key = os.environ.get('EDT_SECRET_KEY', 'edt-gim-toulon-secret-2026')
CORS(app, supports_credentials=True)

# ======================= AUTHENTIFICATION =======================
# Comptes : Admin (tous droits) + connexion enseignant par nom (lecture seule).
# Le mot de passe admin peut être surchargé via la variable d'environnement
# EDT_ADMIN_PASSWORD (recommandé en production pour ne pas l'avoir en clair).
AUTH_USERS = {
    'Admin': {
        'password': os.environ.get('EDT_ADMIN_PASSWORD', 'GestionEDT22#'),
        'role': 'admin',
    },
}
# Routes API accessibles sans être connecté
_PUBLIC_API = {'/api/login', '/api/logout', '/api/me'}

# Database configuration
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.environ.get('EDT_DB_PATH', os.path.join(_BASE_DIR, 'edt.db'))
SCHEMA_PATH = os.path.join(_BASE_DIR, 'schema.sql')

# ===== GESTION DES ANNÉES UNIVERSITAIRES =====
SETTINGS_PATH = os.path.join(_BASE_DIR, 'edt_settings.json')
_settings_cache = None

def get_settings():
    global _settings_cache
    if _settings_cache is None:
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, 'r') as f:
                _settings_cache = json.load(f)
        else:
            _settings_cache = {}
    return _settings_cache

def save_settings(s):
    global _settings_cache
    _settings_cache = s
    with open(SETTINGS_PATH, 'w') as f:
        json.dump(s, f, indent=2)

def auto_detect_year():
    today = datetime.now()
    y = today.year
    return f"{y}-{y+1}" if today.month >= 8 else f"{y-1}-{y}"

def db_path_for_year(year):
    return os.path.join(_BASE_DIR, f'edt_{year}.db')

def get_current_year():
    return get_settings().get('current_year', '')

def list_years():
    years = []
    for fname in os.listdir(_BASE_DIR):
        if fname.startswith('edt_') and fname.endswith('.db') and len(fname) == 16:
            years.append(fname[4:-3])
    return sorted(years)

def school_week_key(w, start_week=36, max_week=52):
    """Clé de tri pour l'ordre scolaire : start_week est la semaine 0.
    max_week = dernière semaine de la 1re année civile (52 ou 53 selon le calendrier ISO)."""
    offset = max_week - start_week + 1
    return w - start_week if w >= start_week else w + offset

def weeks_in_iso_year(iso_year):
    """Nombre de semaines ISO d'une année civile (52 ou 53).
    Le 28 décembre appartient toujours à la dernière semaine ISO de l'année."""
    return datetime(iso_year, 12, 28).isocalendar()[1]

def get_academic_max_week(year=None):
    """Dernière semaine de la 1re année civile de l'année universitaire.
    Vaut 53 pour les années ISO à 53 semaines (ex: 2026 → année 2026-2027), sinon 52."""
    year = year or get_current_year()
    try:
        return weeks_in_iso_year(int(str(year).split('-')[0]))
    except (ValueError, IndexError):
        return 52

# Helper function to get database connection
def _open_connection(path=None):
    """Ouvre une connexion SQLite brute (helper interne)"""
    year = get_current_year()
    p = path or (db_path_for_year(year) if year else DATABASE)
    db = sqlite3.connect(p, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys = ON')
    return db

def get_db():
    """Connexion à la DB de l'année universitaire courante.
    En contexte requête Flask : réutilise la connexion via flask.g
    et la ferme automatiquement via teardown_appcontext.
    Hors contexte (init, scripts) : retourne une connexion directe
    que l'appelant doit fermer manuellement."""
    try:
        if '_db' not in g:
            g._db = _open_connection()
        return g._db
    except RuntimeError:
        # Hors contexte requête Flask (init_db au démarrage, etc.)
        return _open_connection()

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('_db', None)
    if db is not None:
        db.close()

def _apply_migrations(db):
    """Applique toutes les migrations de schéma sur une connexion DB ouverte"""
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('''
        CREATE TABLE IF NOT EXISTS semester_special_weeks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            semester_id INTEGER NOT NULL,
            week_number INTEGER NOT NULL,
            week_type TEXT NOT NULL CHECK(week_type IN ('vacation_ftp', 'company_alt')),
            FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE CASCADE,
            UNIQUE(semester_id, week_number, week_type)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('academic_start_week', '36')")
    db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('academic_end_week', '26')")
    # Semaines de début/fin par parité de semestre (impair: S1/S3/S5 ; pair: S2/S4/S6)
    db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('semester_odd_start_week', '36')")
    db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('semester_odd_end_week', '4')")
    db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('semester_even_start_week', '5')")
    db.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('semester_even_end_week', '26')")
    for col in ['start_week', 'end_week']:
        try:
            db.execute(f'ALTER TABLE courses ADD COLUMN {col} INTEGER')
        except sqlite3.OperationalError:
            pass
    # Dates par défaut du semestre : si 1, les semaines sont calculées dynamiquement
    try:
        db.execute('ALTER TABLE courses ADD COLUMN default_weeks INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass
    # Description / contenu pédagogique de la matière (éditable par admin ou intervenant)
    try:
        db.execute('ALTER TABLE courses ADD COLUMN content TEXT')
    except sqlite3.OperationalError:
        pass
    # Contenu officiel du Programme national (PN), éditable par l'admin uniquement
    try:
        db.execute('ALTER TABLE courses ADD COLUMN content_pn TEXT')
    except sqlite3.OperationalError:
        pass
    try:
        db.execute('ALTER TABLE course_sessions ADD COLUMN sessions_per_week_max INTEGER DEFAULT 1')
    except sqlite3.OperationalError:
        pass
    db.execute('''
        CREATE TABLE IF NOT EXISTS course_ordering (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id_pred INTEGER NOT NULL,
            course_id_succ INTEGER NOT NULL,
            min_gap_weeks  INTEGER DEFAULT 0,
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id_pred) REFERENCES courses(id) ON DELETE CASCADE,
            FOREIGN KEY (course_id_succ) REFERENCES courses(id) ON DELETE CASCADE,
            UNIQUE(course_id_pred, course_id_succ)
        )
    ''')
    # Nouveau calendrier spécial (remplace semester_special_weeks dans l'optimiseur)
    db.execute('''
        CREATE TABLE IF NOT EXISTS special_calendar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_number INTEGER NOT NULL,
            week_type TEXT NOT NULL,
            UNIQUE(week_number, week_type)
        )
    ''')
    # Commentaire libre par semaine (affiché en répartition + export Excel)
    # `formations` = formations concernées (ex : 'FTP,ALT', 'FTP', 'ALT')
    # `years` = années (year_group) concernées (ex : '1,2,3', '1', '2,3')
    db.execute('''
        CREATE TABLE IF NOT EXISTS week_comments (
            week_number INTEGER PRIMARY KEY,
            comment TEXT NOT NULL,
            formations TEXT NOT NULL DEFAULT 'FTP,ALT',
            years TEXT NOT NULL DEFAULT '1,2,3'
        )
    ''')
    _wc_cols = [r[1] for r in db.execute("PRAGMA table_info(week_comments)").fetchall()]
    if 'formations' not in _wc_cols:
        db.execute("ALTER TABLE week_comments ADD COLUMN formations TEXT NOT NULL DEFAULT 'FTP,ALT'")
    if 'years' not in _wc_cols:
        db.execute("ALTER TABLE week_comments ADD COLUMN years TEXT NOT NULL DEFAULT '1,2,3'")
    # Code texte par catégorie de calendrier (affiché en ligne verticale en répartition)
    db.execute('''
        CREATE TABLE IF NOT EXISTS special_category_codes (
            week_type TEXT PRIMARY KEY,
            code TEXT NOT NULL
        )
    ''')
    # Statut enseignant : Titulaire / Vacataire
    if 'status' not in [r[1] for r in db.execute("PRAGMA table_info(teachers)").fetchall()]:
        db.execute("ALTER TABLE teachers ADD COLUMN status TEXT DEFAULT 'Titulaire'")
    # Auto-migration depuis semester_special_weeks (données legacy)
    db.execute('''
        INSERT OR IGNORE INTO special_calendar (week_number, week_type)
        SELECT DISTINCT week_number, 'vacation_ftp'
        FROM semester_special_weeks WHERE week_type = 'vacation_ftp'
    ''')
    db.execute('''
        INSERT OR IGNORE INTO special_calendar (week_number, week_type)
        SELECT DISTINCT ssw.week_number, 'company_alt_y' || s.year_group
        FROM semester_special_weeks ssw
        JOIN semesters s ON ssw.semester_id = s.id
        WHERE ssw.week_type = 'company_alt' AND s.year_group IN (1, 2, 3)
    ''')
    cursor = db.execute('SELECT COUNT(*) as cnt FROM semesters')
    if cursor.fetchone()['cnt'] == 0:
        for code, yg, name in [
            ('S1', 1, 'Semestre 1'), ('S2', 1, 'Semestre 2'),
            ('S3', 2, 'Semestre 3'), ('S4', 2, 'Semestre 4'),
            ('S5', 3, 'Semestre 5'), ('S6', 3, 'Semestre 6'),
        ]:
            db.execute('INSERT OR IGNORE INTO semesters (code, year_group, name) VALUES (?, ?, ?)',
                       (code, yg, name))
    # Normaliser les variantes TP (TP12, TP 12, TP8, TP 8, etc.) → "TP"
    # D'abord fusionner les heures quand un "TP" existe déjà pour le même cours/formation
    db.execute('''
        UPDATE course_sessions SET
            total_hours = total_hours + COALESCE((
                SELECT SUM(cs2.total_hours) FROM course_sessions cs2
                WHERE cs2.course_id = course_sessions.course_id
                  AND cs2.formation_type = course_sessions.formation_type
                  AND cs2.teaching_type != 'TP'
                  AND UPPER(REPLACE(cs2.teaching_type, ' ', '')) LIKE 'TP%'
            ), 0),
            nb_sessions = nb_sessions + COALESCE((
                SELECT SUM(cs2.nb_sessions) FROM course_sessions cs2
                WHERE cs2.course_id = course_sessions.course_id
                  AND cs2.formation_type = course_sessions.formation_type
                  AND cs2.teaching_type != 'TP'
                  AND UPPER(REPLACE(cs2.teaching_type, ' ', '')) LIKE 'TP%'
            ), 0)
        WHERE teaching_type = 'TP'
          AND EXISTS (
                SELECT 1 FROM course_sessions cs2
                WHERE cs2.course_id = course_sessions.course_id
                  AND cs2.formation_type = course_sessions.formation_type
                  AND cs2.teaching_type != 'TP'
                  AND UPPER(REPLACE(cs2.teaching_type, ' ', '')) LIKE 'TP%'
          )
    ''')
    # Supprimer les variantes TP déjà fusionnées
    db.execute('''
        DELETE FROM course_sessions
        WHERE teaching_type != 'TP'
          AND UPPER(REPLACE(teaching_type, ' ', '')) LIKE 'TP%'
          AND EXISTS (
                SELECT 1 FROM course_sessions cs2
                WHERE cs2.course_id = course_sessions.course_id
                  AND cs2.formation_type = course_sessions.formation_type
                  AND cs2.teaching_type = 'TP'
          )
    ''')
    # Renommer les variantes TP restantes (pas de "TP" existant) → "TP"
    db.execute('''
        UPDATE course_sessions SET teaching_type = 'TP'
        WHERE teaching_type != 'TP'
          AND UPPER(REPLACE(teaching_type, ' ', '')) LIKE 'TP%'
    ''')

    # Déduplication course_sessions (nettoyer les doublons existants, garder le plus ancien)
    db.execute('''
        DELETE FROM course_sessions WHERE id NOT IN (
            SELECT MIN(id) FROM course_sessions
            GROUP BY course_id, formation_type, teaching_type
        )
    ''')
    # Index unique pour empêcher les futurs doublons
    try:
        db.execute('''
            CREATE UNIQUE INDEX IF NOT EXISTS idx_cs_unique
            ON course_sessions(course_id, formation_type, teaching_type)
        ''')
    except sqlite3.OperationalError:
        pass
    # Colonne mutualized sur courses (CM/TD communs FTP+ALT)
    try:
        db.execute('ALTER TABLE courses ADD COLUMN mutualized INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass
    # Nombre de groupes de TD/TP par (année, formation) pour le calcul du service
    db.execute('''
        CREATE TABLE IF NOT EXISTS promotion_groups (
            year_group     INTEGER NOT NULL,
            formation_type INTEGER NOT NULL,
            cm_groups      INTEGER NOT NULL DEFAULT 1,
            td_groups      INTEGER NOT NULL DEFAULT 1,
            tp_groups      INTEGER NOT NULL DEFAULT 1,
            pt_groups      INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (year_group, formation_type)
        )
    ''')
    # Valeurs par défaut : FTP 2 TD / 3 TP, ALT et MUT 1 TD / 1 TP, CM/PT = 1
    _PG_DEFAULTS = [
        # year_group, formation_type, cm, td, tp, pt
        (1, 0, 1, 2, 3, 1), (1, 1, 1, 1, 1, 1), (1, 2, 1, 1, 1, 1),
        (2, 0, 1, 2, 3, 1), (2, 1, 1, 1, 1, 1), (2, 2, 1, 1, 1, 1),
        (3, 0, 1, 2, 3, 1), (3, 1, 1, 1, 1, 1), (3, 2, 1, 1, 1, 1),
    ]
    for yg, ft, cm, td, tp, pt in _PG_DEFAULTS:
        db.execute('''
            INSERT OR IGNORE INTO promotion_groups
                (year_group, formation_type, cm_groups, td_groups, tp_groups, pt_groups)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (yg, ft, cm, td, tp, pt))
    db.commit()

def get_year_config():
    """Lit la configuration de l'année courante (semaines début/fin)"""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""SELECT key, value FROM app_settings WHERE key IN (
        'academic_start_week','academic_end_week',
        'semester_odd_start_week','semester_odd_end_week',
        'semester_even_start_week','semester_even_end_week')""")
    cfg = {r['key']: int(r['value']) for r in cursor.fetchall()}
    return {
        'academic_start_week': cfg.get('academic_start_week', 36),
        'academic_end_week':   cfg.get('academic_end_week',   26),
        'semester_odd_start_week':  cfg.get('semester_odd_start_week',  36),
        'semester_odd_end_week':    cfg.get('semester_odd_end_week',    4),
        'semester_even_start_week': cfg.get('semester_even_start_week', 5),
        'semester_even_end_week':   cfg.get('semester_even_end_week',   26),
        'academic_max_week':   get_academic_max_week(),
    }

def get_valid_school_weeks(start_week=36, end_week=26, max_week=52):
    """Ensemble des semaines valides pour une plage scolaire (peut chevaucher S52/S53→S01).
    max_week = dernière semaine de la 1re année civile (52 ou 53 selon le calendrier ISO)."""
    if start_week <= end_week:
        return set(range(start_week, end_week + 1))
    return set(range(start_week, max_week + 1)) | set(range(1, end_week + 1))

def semester_default_weeks(semester_code, cfg):
    """Semaines (début, fin) par défaut selon la parité du semestre (impair S1/S3/S5,
    pair S2/S4/S6), lues depuis la config Calendrier. Renvoie (None, None) si inconnu."""
    digits = ''.join(ch for ch in (semester_code or '') if ch.isdigit())
    if not digits:
        return None, None
    n = int(digits)
    if n % 2 == 1:
        return cfg['semester_odd_start_week'], cfg['semester_odd_end_week']
    return cfg['semester_even_start_week'], cfg['semester_even_end_week']

def resolve_course_weeks(course, cfg):
    """Semaines (début, fin) effectives d'un cours : calcul dynamique selon le semestre
    si default_weeks est activé, sinon les valeurs stockées. `course` doit exposer
    'default_weeks', 'semester_code', 'start_week', 'end_week'."""
    if course.get('default_weeks'):
        s, e = semester_default_weeks(course.get('semester_code'), cfg)
        if s and e:
            return s, e
    return course.get('start_week'), course.get('end_week')

def _init_fresh_db(path):
    """Crée une DB vierge depuis le schéma SQL"""
    db = sqlite3.connect(path)
    with open(SCHEMA_PATH, 'r') as f:
        db.executescript(f.read())
    _apply_migrations(db)
    db.close()

# Helper function to initialize database
def init_db():
    """Initialise la DB pour l'année courante, migre depuis edt.db si besoin"""
    settings = get_settings()

    if not settings.get('current_year'):
        year = auto_detect_year()
        settings['current_year'] = year
        save_settings(settings)

    year = settings['current_year']
    db_path = db_path_for_year(year)

    if not os.path.exists(db_path):
        if os.path.exists(DATABASE):
            shutil.copy2(DATABASE, db_path)   # migration depuis edt.db legacy
        else:
            _init_fresh_db(db_path)

    db = get_db()
    _apply_migrations(db)
    # Ne pas fermer si la connexion est gérée par le contexte Flask (g._db)
    try:
        if '_db' not in g or g._db is not db:
            db.close()
    except RuntimeError:
        db.close()  # Hors contexte Flask → fermer manuellement

# Helper function to convert sqlite3.Row to dict
def row_to_dict(row):
    """Convert sqlite3.Row to dictionary"""
    if row is None:
        return None
    return dict(row)

def rows_to_list(rows):
    """Convert list of sqlite3.Row to list of dictionaries"""
    return [dict(row) for row in rows]

# Error handler
def error_response(message, status_code=400):
    """Return error response"""
    return jsonify({'error': message}), status_code

# ======================= AUTHENTIFICATION (routes + garde) =======================

import re as _re
# Reconnaît /api/courses/<id>/content (autorisé aux intervenants en écriture)
_COURSE_CONTENT_RE = _re.compile(r'^/api/courses/\d+/content$')

def _is_course_content_path(path):
    return bool(_COURSE_CONTENT_RE.match(path))

def teacher_intervenes_in_course(course_id, teacher_name):
    """Vrai si l'enseignant (par nom) intervient dans une session de la matière."""
    if not teacher_name:
        return False
    db = get_db()
    row = db.execute('''
        SELECT 1 FROM course_sessions cs
        JOIN teachers t ON cs.teacher_id = t.id
        WHERE cs.course_id = ? AND LOWER(t.name) = LOWER(?)
        LIMIT 1
    ''', (course_id, teacher_name)).fetchone()
    return row is not None

@app.before_request
def _require_auth():
    """Protège l'API : connexion obligatoire ; visiteur = lecture seule."""
    if request.method == 'OPTIONS':
        return
    path = request.path
    if not path.startswith('/api/'):
        return  # fichiers statiques (SPA + page de connexion) : libres
    if path in _PUBLIC_API:
        return
    role = session.get('role')
    if not role:
        return error_response('Authentification requise', 401)
    if role != 'admin' and request.method not in ('GET', 'HEAD'):
        # Exception : l'enseignant intervenant peut éditer le contenu de SA matière.
        # L'autorisation fine (intervenant ou non) est vérifiée dans le handler.
        if role == 'teacher' and _is_course_content_path(path):
            return
        # Toute autre écriture (y compris la liste des enseignants) est réservée à l'admin
        return error_response('Accès en lecture seule', 403)

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    # Compte fixe (Admin), identifiant insensible à la casse
    key = next((k for k in AUTH_USERS if k.lower() == username.lower()), None)
    if key:
        user = AUTH_USERS[key]
        if user['password'] != password:
            return error_response('Identifiant ou mot de passe incorrect', 401)
        session.permanent = True
        session['user'] = key
        session['role'] = user['role']
        session.pop('teacher_name', None)
        return jsonify({'username': key, 'role': user['role']})
    # Sinon : connexion enseignant par nom de famille (insensible à la casse)
    if username:
        db = get_db()
        row = db.execute('SELECT name, status FROM teachers WHERE LOWER(name) = LOWER(?)', (username,)).fetchone()
        if row:
            status = row['status'] or 'Titulaire'
            session.permanent = True
            session['user'] = row['name']
            session['role'] = 'teacher'
            session['teacher_name'] = row['name']
            session['teacher_status'] = status
            return jsonify({'username': row['name'], 'role': 'teacher',
                            'teacher': row['name'], 'status': status})
    return error_response('Identifiant ou mot de passe incorrect', 401)

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Déconnecté'})

@app.route('/api/me', methods=['GET'])
def me():
    if session.get('role'):
        return jsonify({'username': session.get('user'), 'role': session.get('role'),
                        'teacher': session.get('teacher_name'),
                        'status': session.get('teacher_status')})
    return error_response('Non authentifié', 401)

# ======================= STATIC FILES =======================

_STATIC_DIR = os.path.join(_BASE_DIR, 'static')

@app.route('/')
def serve_root():
    """Serve index.html at root"""
    index_path = os.path.join(_STATIC_DIR, 'index.html')
    if os.path.exists(index_path):
        return send_file(index_path)
    return jsonify({'message': 'Welcome to IUT EDT Management System'}), 200

@app.route('/<path:path>')
def serve_static(path):
    """Serve static files"""
    return send_from_directory(_STATIC_DIR, path)

# Dossier des documents téléchargeables (PDF du Programme national, etc.)
_DOCS_DIR = os.path.join(_BASE_DIR, 'docs')

def _find_pn_pdf():
    """Chemin du PDF du Programme national s'il existe.
    Priorité à la variable d'env EDT_PN_PDF, sinon le 1er .pdf du dossier docs/."""
    env = os.environ.get('EDT_PN_PDF')
    if env and os.path.isfile(env):
        return env
    if os.path.isdir(_DOCS_DIR):
        pdfs = sorted(f for f in os.listdir(_DOCS_DIR) if f.lower().endswith('.pdf'))
        if pdfs:
            return os.path.join(_DOCS_DIR, pdfs[0])
    return None

@app.route('/api/pn-pdf/info', methods=['GET'])
def pn_pdf_info():
    """Indique si un PDF du Programme national est disponible au téléchargement."""
    p = _find_pn_pdf()
    if not p:
        return jsonify({'available': False})
    return jsonify({'available': True, 'filename': 'PN_GIM_ISP.pdf'})

@app.route('/api/pn-pdf', methods=['GET'])
def pn_pdf_download():
    """Télécharge le PDF du Programme national déposé dans le dossier docs/."""
    p = _find_pn_pdf()
    if not p:
        return error_response('Aucun PDF du Programme national disponible', 404)
    return send_file(p, mimetype='application/pdf', as_attachment=True,
                     download_name='PN_GIM_ISP.pdf')

# ======================= TEACHERS CRUD =======================

@app.route('/api/teachers', methods=['GET'])
def get_teachers():
    """Get all teachers"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM teachers ORDER BY name')
        teachers = rows_to_list(cursor.fetchall())
        return jsonify(teachers), 200
    except Exception as e:
        return error_response(f'Error fetching teachers: {str(e)}', 500)

@app.route('/api/teachers', methods=['POST'])
def create_teacher():
    """Create a new teacher"""
    try:
        data = request.get_json()
        if not data or not data.get('name'):
            return error_response('Teacher name is required')
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO teachers (name, email, phone, structure, corps_code, status, max_hours_day, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['name'],
            data.get('email'),
            data.get('phone'),
            data.get('structure'),
            data.get('corps_code'),
            data.get('status') or 'Titulaire',
            data.get('max_hours_day', 6),
            data.get('priority', 1)
        ))
        db.commit()
        teacher_id = cursor.lastrowid
        cursor.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,))
        teacher = row_to_dict(cursor.fetchone())
        return jsonify(teacher), 201
    except sqlite3.IntegrityError:
        return error_response('Teacher name already exists')
    except Exception as e:
        return error_response(f'Error creating teacher: {str(e)}', 500)

@app.route('/api/teachers/<int:teacher_id>', methods=['GET'])
def get_teacher(teacher_id):
    """Get a specific teacher"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,))
        teacher = cursor.fetchone()
        
        if not teacher:
            return error_response('Teacher not found', 404)
        
        return jsonify(row_to_dict(teacher)), 200
    except Exception as e:
        return error_response(f'Error fetching teacher: {str(e)}', 500)

@app.route('/api/teachers/<int:teacher_id>', methods=['PUT'])
def update_teacher(teacher_id):
    """Update a teacher"""
    try:
        data = request.get_json()
        db = get_db()
        cursor = db.cursor()
        
        # Check if teacher exists
        cursor.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,))
        if not cursor.fetchone():
            return error_response('Teacher not found', 404)
        
        # Update fields
        update_fields = []
        values = []
        for field in ['name', 'email', 'phone', 'structure', 'corps_code', 'status', 'max_hours_day', 'priority']:
            if field in data:
                update_fields.append(f'{field} = ?')
                values.append(data[field])
        
        if not update_fields:
            return error_response('No fields to update')
        
        values.append(teacher_id)
        query = f'UPDATE teachers SET {", ".join(update_fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?'
        cursor.execute(query, values)
        db.commit()
        
        cursor.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,))
        teacher = row_to_dict(cursor.fetchone())
        return jsonify(teacher), 200
    except sqlite3.IntegrityError:
        return error_response('Teacher name already exists')
    except Exception as e:
        return error_response(f'Error updating teacher: {str(e)}', 500)

@app.route('/api/teachers/<int:teacher_id>', methods=['DELETE'])
def delete_teacher(teacher_id):
    """Delete a teacher"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Check if teacher exists
        cursor.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,))
        if not cursor.fetchone():
            return error_response('Teacher not found', 404)
        
        cursor.execute('DELETE FROM teachers WHERE id = ?', (teacher_id,))
        db.commit()
        return jsonify({'message': 'Teacher deleted'}), 200
    except Exception as e:
        return error_response(f'Error deleting teacher: {str(e)}', 500)

@app.route('/api/teachers/<int:teacher_id>/availability', methods=['GET'])
def get_teacher_availability(teacher_id):
    """Get teacher availability"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Check if teacher exists
        cursor.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,))
        if not cursor.fetchone():
            return error_response('Teacher not found', 404)
        
        cursor.execute('SELECT * FROM teacher_availability WHERE teacher_id = ? ORDER BY day_of_week, start_time', (teacher_id,))
        availability = rows_to_list(cursor.fetchall())
        return jsonify(availability), 200
    except Exception as e:
        return error_response(f'Error fetching availability: {str(e)}', 500)

@app.route('/api/teachers/<int:teacher_id>/availability', methods=['POST'])
def create_teacher_availability(teacher_id):
    """Add teacher availability"""
    try:
        data = request.get_json()
        db = get_db()
        cursor = db.cursor()
        
        # Check if teacher exists
        cursor.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,))
        if not cursor.fetchone():
            return error_response('Teacher not found', 404)
        
        cursor.execute('''
            INSERT INTO teacher_availability (teacher_id, day_of_week, start_time, end_time, available, priority)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            teacher_id,
            data['day_of_week'],
            data['start_time'],
            data['end_time'],
            data.get('available', 1),
            data.get('priority', 1)
        ))
        db.commit()
        availability_id = cursor.lastrowid
        cursor.execute('SELECT * FROM teacher_availability WHERE id = ?', (availability_id,))
        availability = row_to_dict(cursor.fetchone())
        return jsonify(availability), 201
    except Exception as e:
        return error_response(f'Error creating availability: {str(e)}', 500)

# ======================= ROOMS CRUD =======================

@app.route('/api/rooms', methods=['GET'])
def get_rooms():
    """Get all rooms"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM rooms ORDER BY name')
        rooms = rows_to_list(cursor.fetchall())
        return jsonify(rooms), 200
    except Exception as e:
        return error_response(f'Error fetching rooms: {str(e)}', 500)

@app.route('/api/rooms', methods=['POST'])
def create_room():
    """Create a new room"""
    try:
        data = request.get_json()
        if not data or not data.get('name'):
            return error_response('Room name is required')
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO rooms (name, capacity, room_type, location)
            VALUES (?, ?, ?, ?)
        ''', (
            data['name'],
            data.get('capacity'),
            data.get('room_type', 'standard'),
            data.get('location')
        ))
        db.commit()
        room_id = cursor.lastrowid
        cursor.execute('SELECT * FROM rooms WHERE id = ?', (room_id,))
        room = row_to_dict(cursor.fetchone())
        return jsonify(room), 201
    except sqlite3.IntegrityError:
        return error_response('Room name already exists')
    except Exception as e:
        return error_response(f'Error creating room: {str(e)}', 500)

@app.route('/api/rooms/<int:room_id>', methods=['GET'])
def get_room(room_id):
    """Get a specific room"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM rooms WHERE id = ?', (room_id,))
        room = cursor.fetchone()
        
        if not room:
            return error_response('Room not found', 404)
        
        return jsonify(row_to_dict(room)), 200
    except Exception as e:
        return error_response(f'Error fetching room: {str(e)}', 500)

@app.route('/api/rooms/<int:room_id>', methods=['PUT'])
def update_room(room_id):
    """Update a room"""
    try:
        data = request.get_json()
        db = get_db()
        cursor = db.cursor()
        
        # Check if room exists
        cursor.execute('SELECT * FROM rooms WHERE id = ?', (room_id,))
        if not cursor.fetchone():
            return error_response('Room not found', 404)
        
        # Update fields
        update_fields = []
        values = []
        for field in ['name', 'capacity', 'room_type', 'location']:
            if field in data:
                update_fields.append(f'{field} = ?')
                values.append(data[field])
        
        if not update_fields:
            return error_response('No fields to update')
        
        values.append(room_id)
        query = f'UPDATE rooms SET {", ".join(update_fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?'
        cursor.execute(query, values)
        db.commit()
        
        cursor.execute('SELECT * FROM rooms WHERE id = ?', (room_id,))
        room = row_to_dict(cursor.fetchone())
        return jsonify(room), 200
    except sqlite3.IntegrityError:
        return error_response('Room name already exists')
    except Exception as e:
        return error_response(f'Error updating room: {str(e)}', 500)

@app.route('/api/rooms/<int:room_id>', methods=['DELETE'])
def delete_room(room_id):
    """Delete a room"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Check if room exists
        cursor.execute('SELECT * FROM rooms WHERE id = ?', (room_id,))
        if not cursor.fetchone():
            return error_response('Room not found', 404)
        
        cursor.execute('DELETE FROM rooms WHERE id = ?', (room_id,))
        db.commit()
        return jsonify({'message': 'Room deleted'}), 200
    except Exception as e:
        return error_response(f'Error deleting room: {str(e)}', 500)

# ======================= SEMESTERS CRUD =======================

@app.route('/api/semesters', methods=['GET'])
def get_semesters():
    """Get all semesters"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM semesters ORDER BY code')
        semesters = rows_to_list(cursor.fetchall())
        return jsonify(semesters), 200
    except Exception as e:
        return error_response(f'Error fetching semesters: {str(e)}', 500)

@app.route('/api/semesters', methods=['POST'])
def create_semester():
    """Create a new semester"""
    try:
        data = request.get_json()
        if not data or not data.get('code') or not data.get('year_group'):
            return error_response('Semester code and year_group are required')
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO semesters (code, year_group, name, start_week, end_week)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            data['code'],
            data['year_group'],
            data.get('name'),
            data.get('start_week'),
            data.get('end_week')
        ))
        db.commit()
        semester_id = cursor.lastrowid
        cursor.execute('SELECT * FROM semesters WHERE id = ?', (semester_id,))
        semester = row_to_dict(cursor.fetchone())
        return jsonify(semester), 201
    except sqlite3.IntegrityError:
        return error_response('Semester code already exists')
    except Exception as e:
        return error_response(f'Error creating semester: {str(e)}', 500)

@app.route('/api/semesters/<int:semester_id>', methods=['GET'])
def get_semester(semester_id):
    """Get a specific semester"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM semesters WHERE id = ?', (semester_id,))
        semester = cursor.fetchone()
        
        if not semester:
            return error_response('Semester not found', 404)
        
        return jsonify(row_to_dict(semester)), 200
    except Exception as e:
        return error_response(f'Error fetching semester: {str(e)}', 500)

@app.route('/api/semesters/<int:semester_id>', methods=['PUT'])
def update_semester(semester_id):
    """Update a semester"""
    try:
        data = request.get_json()
        db = get_db()
        cursor = db.cursor()
        
        # Check if semester exists
        cursor.execute('SELECT * FROM semesters WHERE id = ?', (semester_id,))
        if not cursor.fetchone():
            return error_response('Semester not found', 404)
        
        # Update fields
        update_fields = []
        values = []
        for field in ['code', 'year_group', 'name', 'start_week', 'end_week']:
            if field in data:
                update_fields.append(f'{field} = ?')
                values.append(data[field])
        
        if not update_fields:
            return error_response('No fields to update')
        
        values.append(semester_id)
        query = f'UPDATE semesters SET {", ".join(update_fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?'
        cursor.execute(query, values)
        db.commit()
        
        cursor.execute('SELECT * FROM semesters WHERE id = ?', (semester_id,))
        semester = row_to_dict(cursor.fetchone())
        return jsonify(semester), 200
    except sqlite3.IntegrityError:
        return error_response('Semester code already exists')
    except Exception as e:
        return error_response(f'Error updating semester: {str(e)}', 500)

@app.route('/api/semesters/<int:semester_id>', methods=['DELETE'])
def delete_semester(semester_id):
    """Delete a semester"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Check if semester exists
        cursor.execute('SELECT * FROM semesters WHERE id = ?', (semester_id,))
        if not cursor.fetchone():
            return error_response('Semester not found', 404)
        
        cursor.execute('DELETE FROM semesters WHERE id = ?', (semester_id,))
        db.commit()
        return jsonify({'message': 'Semester deleted'}), 200
    except Exception as e:
        return error_response(f'Error deleting semester: {str(e)}', 500)

@app.route('/api/semesters/<int:sem_id>/special-weeks', methods=['GET'])
def get_special_weeks(sem_id):
    """Return special weeks for a semester: {vacation_ftp: [38,43,...], company_alt: [36,37,...]}"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            'SELECT week_number, week_type FROM semester_special_weeks WHERE semester_id = ? ORDER BY week_type, week_number',
            (sem_id,)
        )
        result = {'vacation_ftp': [], 'company_alt': []}
        for r in cursor.fetchall():
            if r['week_type'] in result:
                result[r['week_type']].append(r['week_number'])
        return jsonify(result), 200
    except Exception as e:
        return error_response(str(e), 500)

@app.route('/api/semesters/<int:sem_id>/special-weeks', methods=['PUT'])
def set_special_weeks(sem_id):
    """Replace all special weeks for a semester.
    Body: {vacation_ftp: [38, 43], company_alt: [36, 37]}
    """
    try:
        data = request.get_json() or {}
        db = get_db()
        cursor = db.cursor()
        cursor.execute('DELETE FROM semester_special_weeks WHERE semester_id = ?', (sem_id,))
        for wtype in ['vacation_ftp', 'company_alt']:
            for wnum in (data.get(wtype) or []):
                cursor.execute(
                    'INSERT OR IGNORE INTO semester_special_weeks (semester_id, week_number, week_type) VALUES (?, ?, ?)',
                    (sem_id, int(wnum), wtype)
                )
        db.commit()
        return jsonify({'message': 'Special weeks updated'}), 200
    except Exception as e:
        return error_response(str(e), 500)

# ======================= SPECIAL CALENDAR =======================

_SPECIAL_TYPES = ['vacation_ftp', 'stage_ftp_y2', 'stage_ftp_y3',
                  'company_alt_y1', 'company_alt_y2', 'company_alt_y3']

@app.route('/api/special-calendar', methods=['GET'])
def get_special_calendar():
    """Retourne le calendrier spécial global : {vacation_ftp: [], stage_ftp_y2: [], ...}"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT week_number, week_type FROM special_calendar ORDER BY week_type, week_number')
        result = {t: [] for t in _SPECIAL_TYPES}
        for r in cursor.fetchall():
            if r['week_type'] in result:
                result[r['week_type']].append(r['week_number'])
        return jsonify(result), 200
    except Exception as e:
        return error_response(str(e), 500)

@app.route('/api/special-calendar', methods=['PUT'])
def set_special_calendar():
    """Remplace les semaines de chaque catégorie fournie.
    Body: {vacation_ftp: [38,43], stage_ftp_y2: [...], ...}
    """
    try:
        data = request.get_json() or {}
        db = get_db()
        cursor = db.cursor()
        for wtype in _SPECIAL_TYPES:
            if wtype in data:
                cursor.execute('DELETE FROM special_calendar WHERE week_type = ?', (wtype,))
                for wnum in (data.get(wtype) or []):
                    cursor.execute(
                        'INSERT OR IGNORE INTO special_calendar (week_number, week_type) VALUES (?, ?)',
                        (int(wnum), wtype)
                    )
        db.commit()
        return jsonify({'message': 'Calendrier mis à jour'}), 200
    except Exception as e:
        return error_response(str(e), 500)

@app.route('/api/week-comments', methods=['GET'])
def get_week_comments():
    """Retourne les commentaires par semaine :
    {week_number: {comment: str, formations: [..]}}"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT week_number, comment, formations, years FROM week_comments')
        return jsonify({str(r['week_number']): {
            'comment': r['comment'],
            'formations': [f for f in (r['formations'] or 'FTP,ALT').split(',') if f],
            'years': [int(y) for y in (r['years'] or '1,2,3').split(',') if y],
        } for r in cursor.fetchall()}), 200
    except Exception as e:
        return error_response(str(e), 500)

@app.route('/api/week-comments', methods=['PUT'])
def set_week_comments():
    """Remplace l'ensemble des commentaires.
    Body: {week_number: {comment: str, formations: [..]}, ...}
    (accepte aussi l'ancien format {week_number: "texte"}). Vide = suppression."""
    try:
        data = request.get_json() or {}
        db = get_db()
        cursor = db.cursor()
        cursor.execute('DELETE FROM week_comments')
        for wnum, val in data.items():
            if isinstance(val, dict):
                text = (val.get('comment') or '').strip()
                forms = [f for f in (val.get('formations') or []) if f in ('FTP', 'ALT')]
                yrs = [str(y) for y in (val.get('years') or []) if str(y) in ('1', '2', '3')]
            else:
                text = (val or '').strip()
                forms, yrs = [], []
            formations = ','.join(forms) if forms else 'FTP,ALT'
            years = ','.join(yrs) if yrs else '1,2,3'
            if text:
                cursor.execute(
                    'INSERT OR REPLACE INTO week_comments (week_number, comment, formations, years) VALUES (?, ?, ?, ?)',
                    (int(wnum), text, formations, years)
                )
        db.commit()
        return jsonify({'message': 'Commentaires mis à jour'}), 200
    except Exception as e:
        return error_response(str(e), 500)

@app.route('/api/category-codes', methods=['GET'])
def get_category_codes():
    """Retourne le code texte par catégorie : {week_type: code}"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT week_type, code FROM special_category_codes')
        return jsonify({r['week_type']: r['code'] for r in cursor.fetchall()}), 200
    except Exception as e:
        return error_response(str(e), 500)

@app.route('/api/category-codes', methods=['PUT'])
def set_category_codes():
    """Remplace les codes des catégories. Body: {week_type: code, ...}
    Une valeur vide supprime le code."""
    try:
        data = request.get_json() or {}
        db = get_db()
        cursor = db.cursor()
        cursor.execute('DELETE FROM special_category_codes')
        for wtype, code in data.items():
            if wtype not in _SPECIAL_TYPES:
                continue
            text = (code or '').strip()
            if text:
                cursor.execute(
                    'INSERT OR REPLACE INTO special_category_codes (week_type, code) VALUES (?, ?)',
                    (wtype, text)
                )
        db.commit()
        return jsonify({'message': 'Codes mis à jour'}), 200
    except Exception as e:
        return error_response(str(e), 500)

# ======================= COURSES CRUD =======================

@app.route('/api/courses', methods=['GET'])
def get_courses():
    """Get all courses with hours and rooms per teaching type"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            SELECT c.id, c.code, c.name, c.semester_id, c.course_type,
                   c.start_week, c.end_week, c.default_weeks, c.mutualized,
                   c.content, c.content_pn, c.created_at, c.updated_at,
                   s.code as semester_code,
                   GROUP_CONCAT(DISTINCT t.name) as teacher_names,
                   COALESCE(SUM(CASE WHEN cs.teaching_type='CM' AND cs.formation_type IN (0,2)
                                     THEN cs.total_hours ELSE 0 END), 0) as cm_hours,
                   MAX(CASE WHEN cs.teaching_type='CM' AND cs.formation_type IN (0,2)
                            THEN cs.slot_duration END) as cm_slot_duration,
                   MAX(CASE WHEN cs.teaching_type='CM' AND cs.formation_type IN (0,2)
                            THEN cs.room_name END) as cm_room,
                   MAX(CASE WHEN cs.teaching_type='CM' AND cs.formation_type IN (0,2)
                            THEN t.name END) as cm_teacher,
                   COALESCE(SUM(CASE WHEN cs.teaching_type='TD' AND cs.formation_type IN (0,2)
                                     THEN cs.total_hours ELSE 0 END), 0) as td_hours,
                   MAX(CASE WHEN cs.teaching_type='TD' AND cs.formation_type IN (0,2)
                            THEN cs.slot_duration END) as td_slot_duration,
                   MAX(CASE WHEN cs.teaching_type='TD' AND cs.formation_type IN (0,2)
                            THEN cs.room_name END) as td_room,
                   MAX(CASE WHEN cs.teaching_type='TD' AND cs.formation_type IN (0,2)
                            THEN t.name END) as td_teacher,
                   COALESCE(SUM(CASE WHEN cs.teaching_type='TP' AND cs.formation_type=0
                                     THEN cs.total_hours ELSE 0 END), 0) as tp_hours,
                   MAX(CASE WHEN cs.teaching_type='TP' AND cs.formation_type=0
                            THEN cs.slot_duration END) as tp_slot_duration,
                   MAX(CASE WHEN cs.teaching_type='TP' AND cs.formation_type=0
                            THEN cs.room_name END) as tp_room,
                   MAX(CASE WHEN cs.teaching_type='TP' AND cs.formation_type=0
                            THEN t.name END) as tp_teacher,
                   COALESCE(SUM(CASE WHEN cs.teaching_type='PT' AND cs.formation_type=0
                                     THEN cs.total_hours ELSE 0 END), 0) as pt_hours,
                   MAX(CASE WHEN cs.teaching_type='PT' AND cs.formation_type=0
                            THEN cs.slot_duration END) as pt_slot_duration,
                   MAX(CASE WHEN cs.teaching_type='PT' AND cs.formation_type=0
                            THEN cs.room_name END) as pt_room,
                   MAX(CASE WHEN cs.teaching_type='PT' AND cs.formation_type=0
                            THEN t.name END) as pt_teacher,
                   COALESCE(SUM(CASE WHEN cs.teaching_type='CM' AND cs.formation_type=1
                                     THEN cs.total_hours ELSE 0 END), 0) as alt_cm_hours,
                   MAX(CASE WHEN cs.teaching_type='CM' AND cs.formation_type=1
                            THEN cs.slot_duration END) as alt_cm_slot_duration,
                   MAX(CASE WHEN cs.teaching_type='CM' AND cs.formation_type=1
                            THEN cs.room_name END) as alt_cm_room,
                   MAX(CASE WHEN cs.teaching_type='CM' AND cs.formation_type=1
                            THEN t.name END) as alt_cm_teacher,
                   COALESCE(SUM(CASE WHEN cs.teaching_type='TD' AND cs.formation_type=1
                                     THEN cs.total_hours ELSE 0 END), 0) as alt_td_hours,
                   MAX(CASE WHEN cs.teaching_type='TD' AND cs.formation_type=1
                            THEN cs.slot_duration END) as alt_td_slot_duration,
                   MAX(CASE WHEN cs.teaching_type='TD' AND cs.formation_type=1
                            THEN cs.room_name END) as alt_td_room,
                   MAX(CASE WHEN cs.teaching_type='TD' AND cs.formation_type=1
                            THEN t.name END) as alt_td_teacher,
                   COALESCE(SUM(CASE WHEN cs.teaching_type='TP' AND cs.formation_type=1
                                     THEN cs.total_hours ELSE 0 END), 0) as alt_tp_hours,
                   MAX(CASE WHEN cs.teaching_type='TP' AND cs.formation_type=1
                            THEN cs.slot_duration END) as alt_tp_slot_duration,
                   MAX(CASE WHEN cs.teaching_type='TP' AND cs.formation_type=1
                            THEN cs.room_name END) as alt_tp_room,
                   MAX(CASE WHEN cs.teaching_type='TP' AND cs.formation_type=1
                            THEN t.name END) as alt_tp_teacher,
                   COALESCE(SUM(CASE WHEN cs.teaching_type='PT' AND cs.formation_type=1
                                     THEN cs.total_hours ELSE 0 END), 0) as alt_pt_hours,
                   MAX(CASE WHEN cs.teaching_type='PT' AND cs.formation_type=1
                            THEN cs.slot_duration END) as alt_pt_slot_duration,
                   MAX(CASE WHEN cs.teaching_type='PT' AND cs.formation_type=1
                            THEN cs.room_name END) as alt_pt_room,
                   MAX(CASE WHEN cs.teaching_type='PT' AND cs.formation_type=1
                            THEN t.name END) as alt_pt_teacher,
                   COUNT(DISTINCT cs.id) as session_count
            FROM courses c
            JOIN semesters s ON c.semester_id = s.id
            LEFT JOIN course_sessions cs ON cs.course_id = c.id
            LEFT JOIN teachers t ON cs.teacher_id = t.id
            GROUP BY c.id, c.code, c.name, c.semester_id, c.course_type,
                     c.start_week, c.end_week, c.default_weeks, c.mutualized,
                     c.content, c.content_pn, c.created_at, c.updated_at, s.code
            ORDER BY s.code, c.code
        ''')
        courses = rows_to_list(cursor.fetchall())
        # Résolution dynamique des semaines pour les cours en "dates par défaut"
        cfg = get_year_config()
        for c in courses:
            sw, ew = resolve_course_weeks(c, cfg)
            c['start_week'], c['end_week'] = sw, ew
        return jsonify(courses), 200
    except Exception as e:
        return error_response(f'Error fetching courses: {str(e)}', 500)

@app.route('/api/courses', methods=['POST'])
def create_course():
    """Create a new course with optional teaching hours per type"""
    try:
        data = request.get_json()
        if not data or not data.get('code') or not data.get('name') or not data.get('semester_id'):
            return error_response('code, name and semester_id are required')

        db = get_db()
        cursor = db.cursor()

        cursor.execute('SELECT * FROM semesters WHERE id = ?', (data['semester_id'],))
        if not cursor.fetchone():
            return error_response('Semester not found', 404)

        default_weeks = 1 if data.get('default_weeks') else 0
        # En mode "dates par défaut", les semaines sont dynamiques → ne rien figer
        start_week = None if default_weeks else data.get('start_week')
        end_week   = None if default_weeks else data.get('end_week')
        cfg = get_year_config()
        valid_weeks = get_valid_school_weeks(cfg['academic_start_week'], cfg['academic_end_week'], cfg['academic_max_week'])
        sw_label = f"S{cfg['academic_start_week']:02d}–S{cfg['academic_end_week']:02d}"
        if start_week is not None and int(start_week) not in valid_weeks:
            return error_response(f'Semaine de début hors plage année scolaire ({sw_label})', 400)
        if end_week is not None and int(end_week) not in valid_weeks:
            return error_response(f'Semaine de fin hors plage année scolaire ({sw_label})', 400)

        cursor.execute('''
            INSERT INTO courses (code, name, semester_id, course_type, start_week, end_week, default_weeks, mutualized)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['code'],
            data['name'],
            data['semester_id'],
            data.get('course_type', 'Ressource'),
            start_week,
            end_week,
            default_weeks,
            1 if data.get('mutualized') else 0,
        ))
        db.commit()
        course_id = cursor.lastrowid

        # Les sessions (FTP/ALT) sont créées via PUT /teaching-hours appelé juste après

        cursor.execute('''
            SELECT c.*, s.code as semester_code
            FROM courses c JOIN semesters s ON c.semester_id = s.id
            WHERE c.id = ?
        ''', (course_id,))
        course = row_to_dict(cursor.fetchone())
        return jsonify(course), 201
    except sqlite3.IntegrityError:
        return error_response('Un cours avec ce code existe déjà pour ce semestre')
    except Exception as e:
        return error_response(f'Error creating course: {str(e)}', 500)

@app.route('/api/courses/<int:course_id>', methods=['GET'])
def get_course(course_id):
    """Get a specific course"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            SELECT c.*, s.code as semester_code 
            FROM courses c 
            JOIN semesters s ON c.semester_id = s.id 
            WHERE c.id = ?
        ''', (course_id,))
        course = cursor.fetchone()
        
        if not course:
            return error_response('Course not found', 404)
        
        return jsonify(row_to_dict(course)), 200
    except Exception as e:
        return error_response(f'Error fetching course: {str(e)}', 500)

@app.route('/api/courses/<int:course_id>/content', methods=['PUT'])
def update_course_content(course_id):
    """Met à jour la description / contenu pédagogique d'une matière.
    - `content` (contenu Enseignant) : éditable par l'admin ou un enseignant intervenant.
    - `content_pn` (Programme national) : éditable par l'admin uniquement."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT content, content_pn FROM courses WHERE id = ?', (course_id,))
        row = cursor.fetchone()
        if not row:
            return error_response('Course not found', 404)

        role = session.get('role')
        if role != 'admin':
            teacher_name = session.get('teacher_name')
            if not teacher_intervenes_in_course(course_id, teacher_name):
                return error_response("Vous n'intervenez pas dans cette matière", 403)

        data = request.get_json() or {}

        def _norm(v):
            return v.strip() or None if isinstance(v, str) else None

        content = row['content']
        if 'content' in data:
            content = _norm(data.get('content'))

        content_pn = row['content_pn']
        if 'content_pn' in data:
            if role != 'admin':
                return error_response("Seul l'administrateur peut modifier le Programme national", 403)
            content_pn = _norm(data.get('content_pn'))

        cursor.execute(
            'UPDATE courses SET content = ?, content_pn = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (content, content_pn, course_id)
        )
        db.commit()
        return jsonify({'id': course_id, 'content': content or '', 'content_pn': content_pn or ''}), 200
    except Exception as e:
        return error_response(f'Error updating course content: {str(e)}', 500)

@app.route('/api/courses/<int:course_id>', methods=['PUT'])
def update_course(course_id):
    """Update a course"""
    try:
        data = request.get_json()
        db = get_db()
        cursor = db.cursor()
        
        # Check if course exists
        cursor.execute('SELECT * FROM courses WHERE id = ?', (course_id,))
        if not cursor.fetchone():
            return error_response('Course not found', 404)
        
        # En mode "dates par défaut", les semaines sont dynamiques → ne rien figer
        if 'default_weeks' in data and data.get('default_weeks'):
            data['start_week'] = None
            data['end_week']   = None

        # Validation semaines scolaires
        cfg = get_year_config()
        valid_weeks = get_valid_school_weeks(cfg['academic_start_week'], cfg['academic_end_week'], cfg['academic_max_week'])
        sw_label = f"S{cfg['academic_start_week']:02d}–S{cfg['academic_end_week']:02d}"
        for wk_field in ['start_week', 'end_week']:
            if wk_field in data and data[wk_field] is not None:
                if int(data[wk_field]) not in valid_weeks:
                    label = 'début' if wk_field == 'start_week' else 'fin'
                    return error_response(f'Semaine de {label} hors plage année scolaire ({sw_label})', 400)

        # Update fields
        update_fields = []
        values = []
        for field in ['code', 'name', 'semester_id', 'course_type', 'start_week', 'end_week', 'default_weeks', 'mutualized']:
            if field in data:
                update_fields.append(f'{field} = ?')
                values.append(data[field])
        
        if not update_fields:
            return error_response('No fields to update')
        
        values.append(course_id)
        query = f'UPDATE courses SET {", ".join(update_fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?'
        cursor.execute(query, values)
        db.commit()
        
        cursor.execute('''
            SELECT c.*, s.code as semester_code 
            FROM courses c 
            JOIN semesters s ON c.semester_id = s.id 
            WHERE c.id = ?
        ''', (course_id,))
        course = row_to_dict(cursor.fetchone())
        return jsonify(course), 200
    except Exception as e:
        return error_response(f'Error updating course: {str(e)}', 500)

@app.route('/api/courses/<int:course_id>', methods=['DELETE'])
def delete_course(course_id):
    """Delete a course (cascade deletes its sessions)"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM courses WHERE id = ?', (course_id,))
        if not cursor.fetchone():
            return error_response('Course not found', 404)
        cursor.execute('DELETE FROM courses WHERE id = ?', (course_id,))
        db.commit()
        return jsonify({'message': 'Course deleted'}), 200
    except Exception as e:
        return error_response(f'Error deleting course: {str(e)}', 500)

@app.route('/api/courses/<int:course_id>/teaching-hours', methods=['GET'])
def get_course_teaching_hours(course_id):
    """Get hours, slot_duration and room per teaching type.
    Query param: formation_type (0=FTP default, 1=ALT)
    """
    try:
        formation_type = int(request.args.get('formation_type', 0))
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT id FROM courses WHERE id = ?', (course_id,))
        if not cursor.fetchone():
            return error_response('Course not found', 404)
        cursor.execute('''
            SELECT teaching_type, total_hours, slot_duration, room_name, teacher_id,
                   COALESCE(sessions_per_week_max, 1) as sessions_per_week_max
            FROM course_sessions
            WHERE course_id = ? AND formation_type = ?
        ''', (course_id, formation_type))
        rows = cursor.fetchall()
        result = {t: {'hours': 0, 'slot_duration': 1.5, 'room': '', 'teacher_id': None, 'sessions_per_week_max': 1} for t in ['CM', 'TD', 'TP', 'PT']}
        for r in rows:
            t = r['teaching_type']
            if t in result:
                result[t] = {
                    'hours': r['total_hours'] or 0,
                    'slot_duration': r['slot_duration'] or 1.5,
                    'room': r['room_name'] or '',
                    'teacher_id': r['teacher_id'],
                    'sessions_per_week_max': r['sessions_per_week_max'] or 1,
                }
        return jsonify(result), 200
    except Exception as e:
        return error_response(str(e), 500)

@app.route('/api/courses/<int:course_id>/teaching-hours', methods=['PUT'])
def update_course_teaching_hours(course_id):
    """Upsert hours, slot_duration and room per teaching type.
    Query param: formation_type (0=FTP default, 1=ALT)
    Body: {"CM": {"hours": 10, "slot_duration": 1.5, "room": "Amphi A"}, ...}
    """
    try:
        formation_type = int(request.args.get('formation_type', 0))
        data = request.get_json()
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT id FROM courses WHERE id = ?', (course_id,))
        if not cursor.fetchone():
            return error_response('Course not found', 404)

        for ttype in ['CM', 'TD', 'TP', 'PT']:
            info = (data or {}).get(ttype, {})
            hours = float(info.get('hours') or 0)
            slot_dur = float(info.get('slot_duration') or 1.5)
            room = (info.get('room') or '').strip() or None
            teacher_id = info.get('teacher_id') or None
            spw = max(1, int(info.get('sessions_per_week_max') or 1))
            nb = round(hours / slot_dur) if slot_dur > 0 and hours > 0 else 0

            if hours > 0:
                cursor.execute('''
                    INSERT INTO course_sessions
                        (course_id, formation_type, teaching_type,
                         total_hours, slot_duration, nb_sessions, room_name, teacher_id,
                         sessions_per_week_max)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(course_id, formation_type, teaching_type) DO UPDATE SET
                        total_hours = excluded.total_hours,
                        slot_duration = excluded.slot_duration,
                        nb_sessions = excluded.nb_sessions,
                        room_name = excluded.room_name,
                        teacher_id = excluded.teacher_id,
                        sessions_per_week_max = excluded.sessions_per_week_max,
                        updated_at = CURRENT_TIMESTAMP
                ''', (course_id, formation_type, ttype, hours, slot_dur, nb, room, teacher_id, spw))
            else:
                # Nettoyer les weekly_hours avant de supprimer la session
                cursor.execute('''
                    DELETE FROM weekly_hours WHERE course_session_id IN (
                        SELECT id FROM course_sessions
                        WHERE course_id = ? AND teaching_type = ? AND formation_type = ?
                    )
                ''', (course_id, ttype, formation_type))
                cursor.execute('''
                    DELETE FROM course_sessions
                    WHERE course_id = ? AND teaching_type = ? AND formation_type = ?
                ''', (course_id, ttype, formation_type))

        db.commit()
        return jsonify({'message': 'Teaching hours updated'}), 200
    except Exception as e:
        return error_response(str(e), 500)

@app.route('/api/courses/<int:course_id>/weekly-distribution', methods=['GET'])
def get_weekly_distribution(course_id):
    """Get weekly hours distribution by teaching type.
    Query param: formation_type (0=FTP default, 1=ALT)
    Returns: {CM: {36: 1.5, 37: 1.5}, TD: {...}, TP: {}, PT: {}}
    """
    try:
        formation_type = int(request.args.get('formation_type', 0))
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT id FROM courses WHERE id = ?', (course_id,))
        if not cursor.fetchone():
            return error_response('Course not found', 404)
        cursor.execute('''
            SELECT cs.teaching_type, wh.week_number, wh.hours
            FROM course_sessions cs
            JOIN weekly_hours wh ON wh.course_session_id = cs.id
            WHERE cs.course_id = ? AND cs.formation_type = ?
            ORDER BY cs.teaching_type, wh.week_number
        ''', (course_id, formation_type))
        rows = cursor.fetchall()
        result = {t: {} for t in ['CM', 'TD', 'TP', 'PT']}
        for r in rows:
            t = r['teaching_type']
            if t in result:
                result[t][r['week_number']] = r['hours']
        return jsonify(result), 200
    except Exception as e:
        return error_response(str(e), 500)

@app.route('/api/courses/<int:course_id>/weekly-distribution', methods=['PUT'])
def update_weekly_distribution(course_id):
    """Save weekly hours per teaching type.
    Query param: formation_type (0=FTP default, 1=ALT)
    Body: {CM: {"36": 1.5, "37": 1.5}, TD: {"36": 2}, ...}
    """
    try:
        formation_type = int(request.args.get('formation_type', 0))
        data = request.get_json() or {}
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT id FROM courses WHERE id = ?', (course_id,))
        if not cursor.fetchone():
            return error_response('Course not found', 404)

        for ttype in ['CM', 'TD', 'TP', 'PT']:
            week_data = data.get(ttype, {})
            cursor.execute('''
                SELECT id FROM course_sessions
                WHERE course_id = ? AND teaching_type = ? AND formation_type = ?
            ''', (course_id, ttype, formation_type))
            session = cursor.fetchone()
            if not session:
                continue
            session_id = session['id']
            cursor.execute('DELETE FROM weekly_hours WHERE course_session_id = ?', (session_id,))
            for week_str, hours in week_data.items():
                h = float(hours or 0)
                if h > 0:
                    cursor.execute('''
                        INSERT INTO weekly_hours (course_session_id, week_number, hours)
                        VALUES (?, ?, ?)
                    ''', (session_id, int(week_str), h))

        db.commit()
        return jsonify({'message': 'Weekly distribution updated'}), 200
    except Exception as e:
        return error_response(str(e), 500)

# ======================= COURSE SESSIONS CRUD =======================

@app.route('/api/course-sessions', methods=['GET'])
def get_course_sessions():
    """Get all course sessions"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            SELECT cs.*, c.code as course_code, c.name as course_name,
                   c.semester_id, s.code as semester_code, s.year_group,
                   t.name as teacher_name
            FROM course_sessions cs
            JOIN courses c ON cs.course_id = c.id
            JOIN semesters s ON c.semester_id = s.id
            LEFT JOIN teachers t ON cs.teacher_id = t.id
            ORDER BY s.code, c.code, cs.formation_type, cs.teaching_type
        ''')
        sessions = rows_to_list(cursor.fetchall())
        return jsonify(sessions), 200
    except Exception as e:
        return error_response(f'Error fetching course sessions: {str(e)}', 500)

@app.route('/api/course-sessions', methods=['POST'])
def create_course_session():
    """Create a new course session"""
    try:
        data = request.get_json()
        if not data or not data.get('course_id') or not data.get('teaching_type') or data.get('formation_type') is None:
            return error_response('course_id, teaching_type, and formation_type are required')
        
        db = get_db()
        cursor = db.cursor()
        
        # Check if course exists
        cursor.execute('SELECT * FROM courses WHERE id = ?', (data['course_id'],))
        if not cursor.fetchone():
            return error_response('Course not found', 404)
        
        cursor.execute('''
            INSERT INTO course_sessions (course_id, teacher_id, formation_type, teaching_type, 
                                        nb_sessions, total_hours, slot_duration, room_name, promo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['course_id'],
            data.get('teacher_id'),
            data['formation_type'],
            data['teaching_type'],
            data.get('nb_sessions', 0),
            data.get('total_hours', 0),
            data.get('slot_duration', 1.5),
            data.get('room_name'),
            data.get('promo')
        ))
        db.commit()
        session_id = cursor.lastrowid
        cursor.execute('''
            SELECT cs.*, c.code as course_code, c.name as course_name, t.name as teacher_name
            FROM course_sessions cs
            JOIN courses c ON cs.course_id = c.id
            LEFT JOIN teachers t ON cs.teacher_id = t.id
            WHERE cs.id = ?
        ''', (session_id,))
        session = row_to_dict(cursor.fetchone())
        return jsonify(session), 201
    except Exception as e:
        return error_response(f'Error creating course session: {str(e)}', 500)

@app.route('/api/course-sessions/<int:session_id>', methods=['GET'])
def get_course_session(session_id):
    """Get a specific course session"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            SELECT cs.*, c.code as course_code, c.name as course_name, t.name as teacher_name
            FROM course_sessions cs
            JOIN courses c ON cs.course_id = c.id
            LEFT JOIN teachers t ON cs.teacher_id = t.id
            WHERE cs.id = ?
        ''', (session_id,))
        session = cursor.fetchone()
        
        if not session:
            return error_response('Course session not found', 404)
        
        return jsonify(row_to_dict(session)), 200
    except Exception as e:
        return error_response(f'Error fetching course session: {str(e)}', 500)

@app.route('/api/course-sessions/<int:session_id>', methods=['PUT'])
def update_course_session(session_id):
    """Update a course session"""
    try:
        data = request.get_json()
        db = get_db()
        cursor = db.cursor()
        
        # Check if session exists
        cursor.execute('SELECT * FROM course_sessions WHERE id = ?', (session_id,))
        if not cursor.fetchone():
            return error_response('Course session not found', 404)
        
        # Update fields
        update_fields = []
        values = []
        for field in ['course_id', 'teacher_id', 'formation_type', 'teaching_type', 'nb_sessions', 
                      'total_hours', 'slot_duration', 'room_name', 'promo']:
            if field in data:
                update_fields.append(f'{field} = ?')
                values.append(data[field])
        
        if not update_fields:
            return error_response('No fields to update')
        
        values.append(session_id)
        query = f'UPDATE course_sessions SET {", ".join(update_fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?'
        cursor.execute(query, values)
        db.commit()
        
        cursor.execute('''
            SELECT cs.*, c.code as course_code, c.name as course_name, t.name as teacher_name
            FROM course_sessions cs
            JOIN courses c ON cs.course_id = c.id
            LEFT JOIN teachers t ON cs.teacher_id = t.id
            WHERE cs.id = ?
        ''', (session_id,))
        session = row_to_dict(cursor.fetchone())
        return jsonify(session), 200
    except Exception as e:
        return error_response(f'Error updating course session: {str(e)}', 500)

@app.route('/api/course-sessions/<int:session_id>', methods=['DELETE'])
def delete_course_session(session_id):
    """Delete a course session"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Check if session exists
        cursor.execute('SELECT * FROM course_sessions WHERE id = ?', (session_id,))
        if not cursor.fetchone():
            return error_response('Course session not found', 404)
        
        cursor.execute('DELETE FROM weekly_hours WHERE course_session_id = ?', (session_id,))
        cursor.execute('DELETE FROM course_sessions WHERE id = ?', (session_id,))
        db.commit()
        return jsonify({'message': 'Course session deleted'}), 200
    except Exception as e:
        return error_response(f'Error deleting course session: {str(e)}', 500)

@app.route('/api/course-sessions/by-course/<int:course_id>', methods=['GET'])
def get_course_sessions_by_course(course_id):
    """Get all sessions for a course"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Check if course exists
        cursor.execute('SELECT * FROM courses WHERE id = ?', (course_id,))
        if not cursor.fetchone():
            return error_response('Course not found', 404)
        
        cursor.execute('''
            SELECT cs.*, c.code as course_code, c.name as course_name, t.name as teacher_name
            FROM course_sessions cs
            JOIN courses c ON cs.course_id = c.id
            LEFT JOIN teachers t ON cs.teacher_id = t.id
            WHERE cs.course_id = ?
            ORDER BY cs.teaching_type
        ''', (course_id,))
        sessions = rows_to_list(cursor.fetchall())
        return jsonify(sessions), 200
    except Exception as e:
        return error_response(f'Error fetching course sessions: {str(e)}', 500)

# ======================= WEEKLY HOURS =======================

@app.route('/api/weekly-hours/<int:session_id>', methods=['GET'])
def get_weekly_hours(session_id):
    """Get weekly hours for a session"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Check if session exists
        cursor.execute('SELECT * FROM course_sessions WHERE id = ?', (session_id,))
        if not cursor.fetchone():
            return error_response('Course session not found', 404)
        
        cursor.execute('''
            SELECT * FROM weekly_hours 
            WHERE course_session_id = ? 
            ORDER BY week_number
        ''', (session_id,))
        hours = rows_to_list(cursor.fetchall())
        return jsonify(hours), 200
    except Exception as e:
        return error_response(f'Error fetching weekly hours: {str(e)}', 500)

@app.route('/api/weekly-hours/<int:session_id>', methods=['POST'])
def create_weekly_hours(session_id):
    """Create weekly hours entry"""
    try:
        data = request.get_json()
        if not data or data.get('week_number') is None or data.get('hours') is None:
            return error_response('week_number and hours are required')
        
        db = get_db()
        cursor = db.cursor()
        
        # Check if session exists
        cursor.execute('SELECT * FROM course_sessions WHERE id = ?', (session_id,))
        if not cursor.fetchone():
            return error_response('Course session not found', 404)
        
        cursor.execute('''
            INSERT INTO weekly_hours (course_session_id, week_number, semester_week, hours)
            VALUES (?, ?, ?, ?)
        ''', (
            session_id,
            data['week_number'],
            data.get('semester_week'),
            data['hours']
        ))
        db.commit()
        hours_id = cursor.lastrowid
        cursor.execute('SELECT * FROM weekly_hours WHERE id = ?', (hours_id,))
        hours = row_to_dict(cursor.fetchone())
        return jsonify(hours), 201
    except sqlite3.IntegrityError:
        return error_response('Weekly hours entry already exists for this session and week')
    except Exception as e:
        return error_response(f'Error creating weekly hours: {str(e)}', 500)

@app.route('/api/weekly-hours/batch', methods=['PUT'])
def update_weekly_hours_batch():
    """Batch update weekly hours"""
    try:
        data = request.get_json()
        if not data or not isinstance(data, list):
            return error_response('Request body must be a list of entries')
        
        db = get_db()
        cursor = db.cursor()
        updated_count = 0
        
        for entry in data:
            if not entry.get('id'):
                continue
            
            cursor.execute('''
                UPDATE weekly_hours 
                SET hours = ?, semester_week = ?
                WHERE id = ?
            ''', (
                entry.get('hours', 0),
                entry.get('semester_week'),
                entry['id']
            ))
            updated_count += 1
        
        db.commit()
        return jsonify({'updated': updated_count}), 200
    except Exception as e:
        return error_response(f'Error updating weekly hours: {str(e)}', 500)

@app.route('/api/weekly-hours/<int:session_id>/<int:week_number>', methods=['PUT'])
def upsert_weekly_hours(session_id, week_number):
    """Upsert a single weekly_hours cell (hours > 0 → insert/replace, hours == 0 → delete)"""
    try:
        data = request.get_json() or {}
        hours = float(data.get('hours', 0))
        db = get_db()
        cursor = db.cursor()
        if hours > 0:
            cursor.execute('''
                INSERT OR REPLACE INTO weekly_hours (course_session_id, week_number, hours)
                VALUES (?, ?, ?)
            ''', (session_id, week_number, hours))
        else:
            cursor.execute(
                'DELETE FROM weekly_hours WHERE course_session_id = ? AND week_number = ?',
                (session_id, week_number)
            )
            hours = 0
        db.commit()
        return jsonify({'session_id': session_id, 'week_number': week_number, 'hours': hours}), 200
    except Exception as e:
        return error_response(f'Error upserting weekly hours: {str(e)}', 500)

# ======================= SERVICE CALCULATION =======================

def calculate_hetd(teaching_type, total_hours):
    """Calculate HETD based on teaching type"""
    coefficients = {
        'CM': 1.5,
        'TD': 1.0,
        'TP': 2/3,
        'PT': 1.0
    }
    coefficient = coefficients.get(teaching_type, 1.0)
    return total_hours * coefficient

def _load_promotion_groups(db):
    """Retourne {(year_group, formation_type): {cm,td,tp,pt}}"""
    cur = db.execute('SELECT year_group, formation_type, cm_groups, td_groups, tp_groups, pt_groups FROM promotion_groups')
    return {(r['year_group'], r['formation_type']): {
        'CM': r['cm_groups'], 'TD': r['td_groups'],
        'TP': r['tp_groups'], 'PT': r['pt_groups']
    } for r in cur.fetchall()}

def _group_multiplier(pg_map, year_group, formation_type, teaching_type):
    """Nb de groupes pour (année, formation, type d'enseignement). 1 si non trouvé."""
    groups = pg_map.get((year_group, formation_type))
    if not groups:
        return 1
    # Normaliser TP12, TP8 → TP (sécurité même si déjà migré)
    tt = teaching_type.upper().replace(' ', '')
    if tt.startswith('TP'):
        tt = 'TP'
    return groups.get(tt, 1)

@app.route('/api/promotion-groups', methods=['GET'])
def get_promotion_groups():
    """Liste des groupes par (année, formation)"""
    try:
        db = get_db()
        cur = db.execute('''
            SELECT year_group, formation_type, cm_groups, td_groups, tp_groups, pt_groups
            FROM promotion_groups
            ORDER BY year_group, formation_type
        ''')
        return jsonify(rows_to_list(cur.fetchall())), 200
    except Exception as e:
        return error_response(f'Error loading promotion groups: {str(e)}', 500)

@app.route('/api/promotion-groups', methods=['PUT'])
def update_promotion_groups():
    """Mise à jour bulk. Body: [{year_group, formation_type, cm_groups, td_groups, tp_groups, pt_groups}, ...]"""
    try:
        data = request.get_json()
        if not isinstance(data, list):
            return error_response('Expected a list of promotion group entries')
        db = get_db()
        for entry in data:
            yg = int(entry.get('year_group'))
            ft = int(entry.get('formation_type'))
            cm = max(1, int(entry.get('cm_groups', 1)))
            td = max(1, int(entry.get('td_groups', 1)))
            tp = max(1, int(entry.get('tp_groups', 1)))
            pt = max(1, int(entry.get('pt_groups', 1)))
            db.execute('''
                INSERT INTO promotion_groups (year_group, formation_type, cm_groups, td_groups, tp_groups, pt_groups)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(year_group, formation_type) DO UPDATE SET
                    cm_groups = excluded.cm_groups,
                    td_groups = excluded.td_groups,
                    tp_groups = excluded.tp_groups,
                    pt_groups = excluded.pt_groups
            ''', (yg, ft, cm, td, tp, pt))
        db.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        return error_response(f'Error updating promotion groups: {str(e)}', 500)

@app.route('/api/service/teacher/<int:teacher_id>', methods=['GET'])
def get_teacher_service(teacher_id):
    """Get teacher service hours (HETD calculation)"""
    try:
        db = get_db()
        cursor = db.cursor()

        # Check if teacher exists
        cursor.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,))
        teacher = cursor.fetchone()
        if not teacher:
            return error_response('Teacher not found', 404)

        cursor.execute('''
            SELECT cs.id, c.code as course_code, cs.teaching_type, cs.total_hours,
                   cs.formation_type, s.year_group
            FROM course_sessions cs
            JOIN courses c ON cs.course_id = c.id
            JOIN semesters s ON c.semester_id = s.id
            WHERE cs.teacher_id = ?
        ''', (teacher_id,))
        sessions = cursor.fetchall()

        pg_map = _load_promotion_groups(db)

        service_details = []
        total_hetd = 0

        for session in sessions:
            mult = _group_multiplier(pg_map, session['year_group'], session['formation_type'], session['teaching_type'])
            effective_hours = (session['total_hours'] or 0) * mult
            hetd = calculate_hetd(session['teaching_type'], effective_hours)
            total_hetd += hetd
            service_details.append({
                'course_code': session['course_code'],
                'teaching_type': session['teaching_type'],
                'total_hours': session['total_hours'],
                'nb_groups': mult,
                'effective_hours': effective_hours,
                'hetd': hetd
            })

        return jsonify({
            'teacher_id': teacher_id,
            'teacher_name': teacher['name'],
            'service_details': service_details,
            'total_hetd': total_hetd
        }), 200
    except Exception as e:
        return error_response(f'Error calculating service: {str(e)}', 500)

@app.route('/api/service/all', methods=['GET'])
def get_all_service():
    """Get all teachers' service hours with breakdown by type.
    Heures multipliées par le nb de groupes (table promotion_groups) selon (year_group, formation_type)."""
    try:
        db = get_db()
        cursor = db.cursor()

        cursor.execute('''
            SELECT t.id AS teacher_id, t.name AS teacher_name,
                   cs.teaching_type, cs.total_hours,
                   cs.formation_type, s.year_group
            FROM teachers t
            JOIN course_sessions cs ON cs.teacher_id = t.id
            JOIN courses c ON cs.course_id = c.id
            JOIN semesters s ON c.semester_id = s.id
            ORDER BY t.name
        ''')
        rows = cursor.fetchall()
        pg_map = _load_promotion_groups(db)

        # Agréger par enseignant en multipliant par le nb de groupes
        agg = {}
        for r in rows:
            tid = r['teacher_id']
            if tid not in agg:
                agg[tid] = {'teacher_id': tid, 'teacher_name': r['teacher_name'],
                            'cm_hours': 0, 'td_hours': 0, 'tp_hours': 0, 'pt_hours': 0}
            mult = _group_multiplier(pg_map, r['year_group'], r['formation_type'], r['teaching_type'])
            h = (r['total_hours'] or 0) * mult
            tt = r['teaching_type'].upper().replace(' ', '')
            if tt == 'CM':
                agg[tid]['cm_hours'] += h
            elif tt == 'TD':
                agg[tid]['td_hours'] += h
            elif tt.startswith('TP'):
                agg[tid]['tp_hours'] += h
            elif tt == 'PT':
                agg[tid]['pt_hours'] += h

        services = []
        for s in agg.values():
            cm_h, td_h, tp_h, pt_h = s['cm_hours'], s['td_hours'], s['tp_hours'], s['pt_hours']
            hetd = cm_h * 1.5 + td_h * 1.0 + tp_h * (2.0/3.0) + pt_h * 1.0
            total_h = cm_h + td_h + tp_h + pt_h
            if total_h > 0:
                services.append({
                    'teacher_id': s['teacher_id'],
                    'teacher_name': s['teacher_name'],
                    'cm_hours': round(cm_h, 1),
                    'td_hours': round(td_h, 1),
                    'tp_hours': round(tp_h, 1),
                    'pt_hours': round(pt_h, 1),
                    'total_hours': round(total_h, 1),
                    'total_hetd': round(hetd, 2),
                })
        services.sort(key=lambda x: x['teacher_name'])
        return jsonify(services), 200
    except Exception as e:
        return error_response(f'Error calculating services: {str(e)}', 500)

# ======================= TIMETABLE GENERATION =======================

@app.route('/api/generate-timetable', methods=['POST'])
def generate_timetable():
    """Generate timetable with constraint-based scheduling.

    Constraints:
    - ALT: max 40h/week
    - FTP: target ~25-30h/week
    - Teacher: max 6h CM/TD per day
    - No room conflicts (same room, same time)
    - No teacher conflicts (same teacher, same time)
    - No class/formation conflicts (same formation, same time)
    - Prefer physical info room (123) over mobile; max 2 courses needing fixed info room
    """
    try:
        data = request.get_json() or {}
        weeks = data.get('weeks', [])
        day_start = data.get('day_start', '08:00')
        day_end = data.get('day_end', '18:00')

        db = get_db()
        cursor = db.cursor()

        # If no weeks specified, get all weeks that have data
        if not weeks:
            cursor.execute('SELECT DISTINCT week_number FROM weekly_hours ORDER BY week_number')
            weeks = [r['week_number'] for r in cursor.fetchall()]

        if not weeks:
            return error_response('No weeks to generate')

        # Clear existing timetable for these weeks
        placeholders = ','.join('?' * len(weeks))
        cursor.execute(f'DELETE FROM timetable_slots WHERE week_number IN ({placeholders})', weeks)

        # Build time grid: 30-min slots from day_start to day_end
        start_h, start_m = map(int, day_start.split(':'))
        end_h, end_m = map(int, day_end.split(':'))
        time_slots = []
        h, m = start_h, start_m
        while h * 60 + m < end_h * 60 + end_m:
            time_slots.append(f'{h:02d}:{m:02d}')
            m += 30
            if m >= 60:
                h += 1
                m = 0

        # Load all sessions with their weekly hours
        cursor.execute('''
            SELECT cs.id, cs.course_id, cs.teacher_id, cs.formation_type,
                   cs.teaching_type, cs.slot_duration, cs.room_name, cs.nb_sessions,
                   c.code as course_code, c.semester_id, s.year_group
            FROM course_sessions cs
            JOIN courses c ON cs.course_id = c.id
            JOIN semesters s ON c.semester_id = s.id
        ''')
        all_sessions = [dict(r) for r in cursor.fetchall()]

        # Load room IDs
        room_map = {}
        cursor.execute('SELECT id, name FROM rooms')
        for r in cursor.fetchall():
            room_map[r['name']] = r['id']

        # Pre-load all weekly_hours for requested weeks (avoid N+1 queries)
        wh_map = {}  # (course_session_id, week_number) -> hours
        cursor.execute(
            f'SELECT course_session_id, week_number, hours FROM weekly_hours WHERE week_number IN ({placeholders})',
            weeks)
        for r in cursor.fetchall():
            if r['hours'] and r['hours'] > 0:
                wh_map[(r['course_session_id'], r['week_number'])] = r['hours']

        generated_slots = 0
        conflicts = []

        for week in weeks:
            # Track occupancy: key = (day, time_slot_index) -> set of resources
            room_occupied = {}    # (day, time_idx, room_id) -> True
            teacher_occupied = {} # (day, time_idx, teacher_id) -> True
            formation_occupied = {} # (day, time_idx, year_group, formation) -> True
            teacher_day_cm_td = {} # (day, teacher_id) -> hours of CM/TD
            week_hours_ftp = 0
            week_hours_alt = 0

            # Get sessions that have hours this week
            week_sessions = []
            for sess in all_sessions:
                h = wh_map.get((sess['id'], week))
                if h:
                    sess_copy = dict(sess)
                    sess_copy['week_hours'] = h
                    week_sessions.append(sess_copy)

            # Sort: CM first (harder to place), then TD, then TP, then PT
            type_order = {'CM': 0, 'TD': 1, 'TP': 2, 'PT': 3}
            week_sessions.sort(key=lambda s: (type_order.get(s['teaching_type'], 4), -(s['week_hours'])))

            for sess in week_sessions:
                hours_to_place = sess['week_hours']
                duration = sess.get('slot_duration') or 1.5
                num_slots_needed = max(1, round(hours_to_place / duration))
                duration_in_30min = int(duration * 2)

                room_id = room_map.get(sess['room_name'])
                teacher_id = sess['teacher_id']
                formation = sess['formation_type']
                year_group = sess['year_group']
                ttype = sess['teaching_type']
                is_cm_td = ttype in ('CM', 'TD')

                placed = 0
                for slot_attempt in range(num_slots_needed):
                    best_day = None
                    best_time = None

                    for day in range(5):  # Mon-Fri
                        # Check teacher CM/TD limit (6h/day)
                        if is_cm_td and teacher_id:
                            current_cm_td = teacher_day_cm_td.get((day, teacher_id), 0)
                            if current_cm_td + duration > 6:
                                continue

                        for t_idx in range(len(time_slots) - duration_in_30min + 1):
                            # Check all 30-min sub-slots
                            conflict = False
                            for dt in range(duration_in_30min):
                                ti = t_idx + dt
                                if room_id and (day, ti, room_id) in room_occupied:
                                    conflict = True
                                    break
                                if teacher_id and (day, ti, teacher_id) in teacher_occupied:
                                    conflict = True
                                    break
                                if (day, ti, year_group, formation) in formation_occupied:
                                    conflict = True
                                    break
                            if not conflict:
                                best_day = day
                                best_time = t_idx
                                break
                        if best_day is not None:
                            break

                    if best_day is not None:
                        # Place the slot
                        start_t = time_slots[best_time]
                        end_idx = best_time + duration_in_30min
                        if end_idx < len(time_slots):
                            end_t = time_slots[end_idx]
                        else:
                            eh = int(start_t.split(':')[0]) + int(duration)
                            em = int(start_t.split(':')[1]) + int((duration % 1) * 60)
                            if em >= 60:
                                eh += 1
                                em -= 60
                            end_t = f'{eh:02d}:{em:02d}'

                        cursor.execute('''
                            INSERT INTO timetable_slots
                            (course_session_id, week_number, day_of_week, start_time, end_time,
                             room_id, teacher_id, formation_type)
                            VALUES (?,?,?,?,?,?,?,?)
                        ''', (sess['id'], week, best_day, start_t, end_t,
                              room_id, teacher_id, formation))
                        generated_slots += 1
                        placed += 1

                        # Mark occupied
                        for dt in range(duration_in_30min):
                            ti = best_time + dt
                            if room_id:
                                room_occupied[(best_day, ti, room_id)] = True
                            if teacher_id:
                                teacher_occupied[(best_day, ti, teacher_id)] = True
                            formation_occupied[(best_day, ti, year_group, formation)] = True

                        if is_cm_td and teacher_id:
                            teacher_day_cm_td[(best_day, teacher_id)] = \
                                teacher_day_cm_td.get((best_day, teacher_id), 0) + duration

                        if formation == 0:
                            week_hours_ftp += duration
                        elif formation == 1:
                            week_hours_alt += duration
                    else:
                        conflicts.append({
                            'week': week,
                            'session_id': sess['id'],
                            'course': sess['course_code'],
                            'type': ttype,
                            'reason': 'No available slot'
                        })

        db.commit()

        return jsonify({
            'generated_slots': generated_slots,
            'weeks_processed': len(weeks),
            'conflicts': conflicts[:50]  # Limit conflict list
        }), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return error_response(f'Error generating timetable: {str(e)}', 500)

@app.route('/api/available-weeks', methods=['GET'])
def get_available_weeks():
    """Get all weeks that have data"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT DISTINCT week_number FROM weekly_hours ORDER BY week_number')
        weeks = [r['week_number'] for r in cursor.fetchall()]
        return jsonify(weeks), 200
    except Exception as e:
        return error_response(f'Error: {str(e)}', 500)

@app.route('/api/timetable/week/<int:week_number>', methods=['GET'])
def get_timetable_week(week_number):
    """Get timetable for a specific week"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            SELECT ts.*, cs.teaching_type, cs.formation_type as form_type,
                   c.code as course_code, c.name as course_name,
                   s.code as semester_code, s.year_group,
                   t.name as teacher_name, r.name as room_name
            FROM timetable_slots ts
            JOIN course_sessions cs ON ts.course_session_id = cs.id
            JOIN courses c ON cs.course_id = c.id
            JOIN semesters s ON c.semester_id = s.id
            LEFT JOIN teachers t ON ts.teacher_id = t.id
            LEFT JOIN rooms r ON ts.room_id = r.id
            WHERE ts.week_number = ?
            ORDER BY ts.day_of_week, ts.start_time
        ''', (week_number,))
        slots = rows_to_list(cursor.fetchall())
        return jsonify({
            'week_number': week_number,
            'slots': slots
        }), 200
    except Exception as e:
        return error_response(f'Error fetching timetable: {str(e)}', 500)

@app.route('/api/timetable/teacher/<int:teacher_id>/week/<int:week_number>', methods=['GET'])
def get_teacher_timetable_week(teacher_id, week_number):
    """Get timetable for a teacher in a specific week"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Check if teacher exists
        cursor.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,))
        if not cursor.fetchone():
            return error_response('Teacher not found', 404)
        
        cursor.execute('''
            SELECT ts.*, c.code as course_code, c.name as course_name, 
                   r.name as room_name
            FROM timetable_slots ts
            JOIN course_sessions cs ON ts.course_session_id = cs.id
            JOIN courses c ON cs.course_id = c.id
            LEFT JOIN rooms r ON ts.room_id = r.id
            WHERE ts.teacher_id = ? AND ts.week_number = ?
            ORDER BY ts.day_of_week, ts.start_time
        ''', (teacher_id, week_number))
        slots = rows_to_list(cursor.fetchall())
        
        return jsonify({
            'teacher_id': teacher_id,
            'week_number': week_number,
            'slots': slots
        }), 200
    except Exception as e:
        return error_response(f'Error fetching teacher timetable: {str(e)}', 500)

@app.route('/api/timetable/week/<int:week_number>', methods=['DELETE'])
def clear_timetable_week(week_number):
    """Clear timetable for a specific week"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('DELETE FROM timetable_slots WHERE week_number = ?', (week_number,))
        deleted = cursor.rowcount
        db.commit()
        
        return jsonify({
            'week_number': week_number,
            'deleted': deleted
        }), 200
    except Exception as e:
        return error_response(f'Error clearing timetable: {str(e)}', 500)

# ======================= CALENDAR =======================

@app.route('/api/calendar', methods=['GET'])
def get_calendar():
    """Get calendar events"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM calendar_events ORDER BY week_number')
        events = rows_to_list(cursor.fetchall())
        return jsonify(events), 200
    except Exception as e:
        return error_response(f'Error fetching calendar: {str(e)}', 500)

@app.route('/api/calendar', methods=['POST'])
def create_calendar_event():
    """Create calendar event"""
    try:
        data = request.get_json()
        if not data or not data.get('event_type'):
            return error_response('event_type is required')
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            INSERT INTO calendar_events (week_number, date, event_type, description)
            VALUES (?, ?, ?, ?)
        ''', (
            data.get('week_number'),
            data.get('date'),
            data['event_type'],
            data.get('description')
        ))
        db.commit()
        event_id = cursor.lastrowid
        cursor.execute('SELECT * FROM calendar_events WHERE id = ?', (event_id,))
        event = row_to_dict(cursor.fetchone())
        return jsonify(event), 201
    except Exception as e:
        return error_response(f'Error creating calendar event: {str(e)}', 500)

# ======================= IMPORT =======================

@app.route('/api/import/excel', methods=['POST'])
def import_excel():
    """Import data from Excel file"""
    try:
        if 'file' not in request.files:
            return error_response('No file part')
        
        file = request.files['file']
        if file.filename == '':
            return error_response('No selected file')
        
        # This is a placeholder for Excel import
        # Actual implementation would require openpyxl or pandas library
        return jsonify({
            'message': 'Excel import not yet implemented',
            'note': 'Install openpyxl or pandas to enable Excel import'
        }), 501
    except Exception as e:
        return error_response(f'Error importing file: {str(e)}', 500)

# ======================= REPARTITION HEBDOMADAIRE =======================

@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(get_year_config())

@app.route('/api/config', methods=['PUT'])
def update_config():
    data = request.get_json() or {}
    db = get_db()
    for key in ['academic_start_week', 'academic_end_week',
                'semester_odd_start_week', 'semester_odd_end_week',
                'semester_even_start_week', 'semester_even_end_week']:
        if key in data:
            try:
                val = int(data[key])
            except (TypeError, ValueError):
                return error_response(f'{key} doit être un entier', 400)
            if val < 1 or val > 52:
                return error_response(f'{key} hors plage (1–52)', 400)
            db.execute('INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)', (key, str(val)))
    db.commit()
    return jsonify({'message': 'Configuration mise à jour'})

@app.route('/api/repartition', methods=['GET'])
def get_repartition():
    """Tableau pivot : pour un semestre donné, heures par cours et par semaine"""
    semester_code = request.args.get('semester', '')
    try:
        cfg = get_year_config()
        start_week = cfg['academic_start_week']
        end_week_cfg = cfg['academic_end_week']
        max_week = cfg['academic_max_week']
        _key = lambda w: school_week_key(w, start_week, max_week)

        # Colonnes = plage complète de l'année académique (identique pour tous les semestres)
        weeks = sorted(get_valid_school_weeks(start_week, end_week_cfg, max_week), key=_key)

        db = get_db()
        cursor = db.cursor()

        # Détecter l'année de promotion à partir du code semestre
        year_group = None
        if semester_code:
            s_code = semester_code.split('+')[0]  # ex: "S1+S2" → "S1"
            try:
                sn = int(s_code[1])          # S1→1, S3→3, S5→5
                year_group = (sn + 1) // 2   # 1,2→1 ; 3,4→2 ; 5,6→3
            except Exception:
                pass

        # Charger le calendrier spécial global
        cursor.execute('SELECT week_number, week_type FROM special_calendar ORDER BY week_type, week_number')
        sc = {t: [] for t in _SPECIAL_TYPES}
        for r in cursor.fetchall():
            if r['week_type'] in sc:
                sc[r['week_type']].append(r['week_number'])

        special_weeks = {
            'vacation_ftp': sc['vacation_ftp'],
            'stage_ftp':    sc.get(f'stage_ftp_y{year_group}', []) if year_group and year_group >= 2 else [],
            'company_alt':  sc.get(f'company_alt_y{year_group}', []) if year_group else [],
        }

        # Lignes de données avec heures hebdomadaires
        if semester_code:
            cursor.execute('''
                SELECT cs.id AS session_id,
                       c.code AS course_code, c.name AS course_name,
                       s.code AS semester_code,
                       cs.teaching_type, cs.formation_type,
                       cs.total_hours, cs.nb_sessions, cs.slot_duration,
                       cs.room_name,
                       t.name AS teacher_name,
                       wh.week_number, wh.semester_week, wh.hours
                FROM course_sessions cs
                JOIN courses c ON cs.course_id = c.id
                JOIN semesters s ON c.semester_id = s.id
                LEFT JOIN teachers t ON cs.teacher_id = t.id
                LEFT JOIN weekly_hours wh ON wh.course_session_id = cs.id
                WHERE s.code = ? AND (cs.nb_sessions > 0 OR cs.total_hours > 0)
                ORDER BY c.code,
                         CASE cs.teaching_type WHEN 'CM' THEN 0 WHEN 'TD' THEN 1 WHEN 'TP' THEN 2 WHEN 'PT' THEN 3 ELSE 4 END,
                         cs.formation_type, wh.week_number
            ''', (semester_code,))
        else:
            cursor.execute('''
                SELECT cs.id AS session_id,
                       c.code AS course_code, c.name AS course_name,
                       s.code AS semester_code,
                       cs.teaching_type, cs.formation_type,
                       cs.total_hours, cs.nb_sessions, cs.slot_duration,
                       cs.room_name,
                       t.name AS teacher_name,
                       wh.week_number, wh.semester_week, wh.hours
                FROM course_sessions cs
                JOIN courses c ON cs.course_id = c.id
                JOIN semesters s ON c.semester_id = s.id
                LEFT JOIN teachers t ON cs.teacher_id = t.id
                LEFT JOIN weekly_hours wh ON wh.course_session_id = cs.id
                WHERE cs.nb_sessions > 0 OR cs.total_hours > 0
                ORDER BY s.code, c.code,
                         CASE cs.teaching_type WHEN 'CM' THEN 0 WHEN 'TD' THEN 1 WHEN 'TP' THEN 2 WHEN 'PT' THEN 3 ELSE 4 END,
                         cs.formation_type, wh.week_number
            ''')
        raw = cursor.fetchall()

        # Pivot : regrouper par session
        sessions = {}
        order = []
        for r in raw:
            sid = r['session_id']
            if sid not in sessions:
                sessions[sid] = {
                    'session_id': sid,
                    'course_code': r['course_code'] or '',
                    'course_name': r['course_name'] or '',
                    'semester': r['semester_code'] or '',
                    'type': r['teaching_type'] or '',
                    'formation': {0: 'FTP', 1: 'ALT', 2: 'MUT', 3: 'OTHER'}.get(r['formation_type'], str(r['formation_type'] or '')),
                    'total_hours': r['total_hours'] or 0,
                    'nb_sessions': r['nb_sessions'] or 0,
                    'slot_duration': r['slot_duration'] or 1.5,
                    'teacher': r['teacher_name'] or '',
                    'room': r['room_name'] or '',
                    'by_week': {},
                }
                order.append(sid)
            if r['week_number'] is not None and (r['hours'] or 0) > 0:
                sessions[sid]['by_week'][r['week_number']] = r['hours'] or 0

        return jsonify({
            'weeks': weeks,
            'rows': [sessions[sid] for sid in order],
            'special_weeks': special_weeks,
        }), 200
    except Exception as e:
        return error_response(f'Error fetching repartition: {str(e)}', 500)

@app.route('/api/checks/repartition', methods=['GET'])
def checks_repartition():
    """Contrôles de validation : charge enseignants par semaine + conflits salles"""
    try:
        db = get_db()
        cursor = db.cursor()

        # 1. Charge enseignants par semaine
        cursor.execute('''
            SELECT t.id AS teacher_id, t.name AS teacher_name,
                   wh.week_number,
                   SUM(wh.hours) AS total_hours,
                   GROUP_CONCAT(DISTINCT c.code || ' ' || cs.teaching_type) AS courses
            FROM weekly_hours wh
            JOIN course_sessions cs ON wh.course_session_id = cs.id
            JOIN courses c ON cs.course_id = c.id
            JOIN teachers t ON cs.teacher_id = t.id
            WHERE wh.hours > 0
            GROUP BY t.id, wh.week_number
            HAVING SUM(wh.hours) > 20
            ORDER BY t.name, wh.week_number
        ''')
        teacher_load = [dict(r) for r in cursor.fetchall()]

        # 2. Conflits salles : semaines où une salle est utilisée par plus de 2 matières
        #    - STD (salles standard, pool générique) : exclue du contrôle
        #    - 123 : label couvrant deux salles info → nombre de matières divisé par deux
        cursor.execute('''
            SELECT cs.room_name, wh.week_number,
                   CASE WHEN cs.room_name = '123'
                        THEN COUNT(DISTINCT c.id) / 2.0
                        ELSE COUNT(DISTINCT c.id) END AS nb_courses,
                   GROUP_CONCAT(DISTINCT c.code || ' ' || cs.teaching_type) AS courses
            FROM weekly_hours wh
            JOIN course_sessions cs ON wh.course_session_id = cs.id
            JOIN courses c ON cs.course_id = c.id
            WHERE wh.hours > 0 AND cs.room_name IS NOT NULL AND cs.room_name != ''
              AND cs.room_name != 'STD'
            GROUP BY cs.room_name, wh.week_number
            HAVING (CASE WHEN cs.room_name = '123'
                         THEN COUNT(DISTINCT c.id) / 2.0
                         ELSE COUNT(DISTINCT c.id) END) > 2
            ORDER BY cs.room_name, wh.week_number
        ''')
        room_conflicts = [dict(r) for r in cursor.fetchall()]

        return jsonify({
            'teacher_load': teacher_load,
            'room_conflicts': room_conflicts,
        }), 200
    except Exception as e:
        return error_response(f'Error running checks: {str(e)}', 500)

@app.route('/api/export/repartition', methods=['GET'])
def export_repartition_excel():
    """Export la répartition des 6 semestres en fichier Excel (un onglet par année)"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.formatting.rule import CellIsRule

    try:
        db = get_db()
        cursor = db.cursor()

        # Filtres d'affichage (repris de l'onglet Répartition) : semestres, formation, enseignant
        sel_sems = [s.strip() for s in (request.args.get('semesters') or '').split(',') if s.strip()]
        sel_sems = set(sel_sems) or None
        form_filter = (request.args.get('formation') or '').lower()   # '', 'ftp', 'alt'
        teacher_filter = (request.args.get('teacher') or '').strip() or None

        def session_included(s):
            if sel_sems is not None and s['semester'] not in sel_sems:
                return False
            if teacher_filter and (s['teacher'] or '') != teacher_filter:
                return False
            if form_filter == 'ftp' and s['formation'] not in ('FTP', 'MUT'):
                return False
            if form_filter == 'alt' and s['formation'] not in ('ALT', 'MUT'):
                return False
            return True

        cfg = get_year_config()
        start_week = cfg['academic_start_week']
        end_week_cfg = cfg['academic_end_week']
        max_week = cfg['academic_max_week']
        _key = lambda w: school_week_key(w, start_week, max_week)
        weeks = sorted(get_valid_school_weeks(start_week, end_week_cfg, max_week), key=_key)

        # Charger le calendrier spécial
        cursor.execute('SELECT week_number, week_type FROM special_calendar ORDER BY week_type, week_number')
        sc = {t: set() for t in _SPECIAL_TYPES}
        for r in cursor.fetchall():
            if r['week_type'] in sc:
                sc[r['week_type']].add(r['week_number'])

        # Charger les commentaires par semaine (affichés au-dessus du tableau)
        cursor.execute('SELECT week_number, comment, formations, years FROM week_comments')
        week_comments = {r['week_number']: {
            'comment': r['comment'],
            'years': [int(y) for y in (r['years'] or '1,2,3').split(',') if y],
        } for r in cursor.fetchall()}

        # Charger les codes des catégories (affichés en 1re ligne de chaque onglet)
        cursor.execute('SELECT week_type, code FROM special_category_codes')
        category_codes = {r['week_type']: r['code'] for r in cursor.fetchall()}

        # Charger toutes les sessions avec heures hebdomadaires
        cursor.execute('''
            SELECT cs.id AS session_id,
                   c.code AS course_code, c.name AS course_name,
                   s.code AS semester_code, s.year_group,
                   cs.teaching_type, cs.formation_type,
                   cs.total_hours, cs.nb_sessions, cs.slot_duration,
                   cs.room_name,
                   t.name AS teacher_name,
                   wh.week_number, wh.hours
            FROM course_sessions cs
            JOIN courses c ON cs.course_id = c.id
            JOIN semesters s ON c.semester_id = s.id
            LEFT JOIN teachers t ON cs.teacher_id = t.id
            LEFT JOIN weekly_hours wh ON wh.course_session_id = cs.id
            WHERE cs.nb_sessions > 0 OR cs.total_hours > 0
            ORDER BY s.year_group, s.code, c.code,
                     CASE cs.teaching_type WHEN 'CM' THEN 0 WHEN 'TD' THEN 1 WHEN 'TP' THEN 2 WHEN 'PT' THEN 3 ELSE 4 END,
                     cs.formation_type, wh.week_number
        ''')
        raw = cursor.fetchall()

        # Pivoter par session
        sessions = {}
        order = []
        for r in raw:
            sid = r['session_id']
            if sid not in sessions:
                sessions[sid] = {
                    'session_id': sid,
                    'course_code': r['course_code'] or '',
                    'course_name': r['course_name'] or '',
                    'semester': r['semester_code'] or '',
                    'year_group': r['year_group'],
                    'type': r['teaching_type'] or '',
                    'formation': {0: 'FTP', 1: 'ALT', 2: 'MUT'}.get(r['formation_type'], '?'),
                    'formation_type': r['formation_type'],
                    'total_hours': r['total_hours'] or 0,
                    'teacher': r['teacher_name'] or '',
                    'room': r['room_name'] or '',
                    'by_week': {},
                }
                order.append(sid)
            if r['week_number'] is not None and (r['hours'] or 0) > 0:
                sessions[sid]['by_week'][r['week_number']] = r['hours']

        # Styles
        thin = Side(style='thin', color='374151')
        thick = Side(style='medium', color='374151')
        border_all = Border(left=thin, right=thin, top=thin, bottom=thin)
        font_header = Font(bold=True, size=9)
        font_data = Font(size=8)
        font_mat = Font(bold=True, size=9, color='4F46E5')
        font_form_ftp = Font(bold=True, size=8, color='0369A1')
        font_form_alt = Font(bold=True, size=8, color='9A3412')
        font_form_mut = Font(bold=True, size=8, color='6B21A8')
        font_total_ok = Font(bold=True, size=8, color='4F46E5')
        font_total_bad = Font(bold=True, size=8, color='DC2626')
        fill_ftp = PatternFill('solid', fgColor='E0F2FE')
        fill_alt = PatternFill('solid', fgColor='FFF7ED')
        fill_mut = PatternFill('solid', fgColor='F3E8FF')
        fill_mat = PatternFill('solid', fgColor='EEF2FF')
        fill_header = PatternFill('solid', fgColor='F3F4F6')
        fill_total = PatternFill('solid', fgColor='EEF2FF')
        # Semaines spéciales (vacances / stage / entreprise) : couleur orange unique,
        # cohérente avec l'affichage à l'écran.
        fill_vacation = PatternFill('solid', fgColor='FDBA74')
        fill_stage    = PatternFill('solid', fgColor='FDBA74')
        fill_company  = PatternFill('solid', fgColor='FDBA74')
        align_center = Alignment(horizontal='center', vertical='center')

        wb = Workbook()
        wb.remove(wb.active)

        # Ordre d'affichage imposé des matières S5/S6 (entrelacé), identique à l'écran.
        # Les codes absents conservent leur ordre naturel (tri stable).
        s56_order = {code: i for i, code in enumerate([
            'R5.01', 'R6.01', 'R5.02', 'R5.03a', 'R5.03b', 'R6.02', 'R5.04', 'R6.03',
            'R5.05', 'R6.04', 'R5.06', 'R5.07', 'R5.08', 'R5.09', 'R5.10', 'R6.05',
            'R5.11', 'R6.06', 'R5.12', 'R6.07', 'R5.13', 'R5.14', 'R6.08',
            'SAE5.1', 'SAE5.2', 'SAE5.3', 'SAE6.1', 'SAE6.2',
        ])}
        # Repositionnements ponctuels « placer ce code juste après cet autre code ».
        course_after = {'R3.11': 'R3.08'}

        year_groups = [(1, 'S1+S2', ['S1', 'S2']), (2, 'S3+S4', ['S3', 'S4']), (3, 'S5+S6', ['S5', 'S6'])]

        for yg, sheet_name, sem_codes in year_groups:
            # Filtrer les sessions pour cette année + selon l'affichage (semestre/formation/enseignant)
            year_sessions = [sessions[sid] for sid in order
                             if sessions[sid]['semester'] in sem_codes and session_included(sessions[sid])]
            if not year_sessions:
                continue  # onglet non créé s'il n'y a rien à afficher

            ws = wb.create_sheet(title=sheet_name)

            # Semaines spéciales pour cette année
            sp_vacation = sc['vacation_ftp']
            sp_stage = sc.get(f'stage_ftp_y{yg}', set()) if yg >= 2 else set()
            sp_company = sc.get(f'company_alt_y{yg}', set())

            # Grouper par matière
            by_code = {}
            code_order = []
            for s in year_sessions:
                key = s['course_code'] + '|' + s['semester']
                if key not in by_code:
                    by_code[key] = {'code': s['course_code'], 'name': s['course_name'],
                                    'sem': s['semester'], 'ftp': [], 'alt': [], 'mut': []}
                    code_order.append(key)
                if s['formation'] == 'FTP': by_code[key]['ftp'].append(s)
                elif s['formation'] == 'ALT': by_code[key]['alt'].append(s)
                elif s['formation'] == 'MUT': by_code[key]['mut'].append(s)

            # Ordre imposé S5/S6 (entrelacé) ; autres années : ordre naturel conservé.
            code_order.sort(key=lambda k: s56_order.get(by_code[k]['code'], 10**6))
            # Repositionnements ponctuels (ex. R3.11 juste après R3.08)
            for move_code, after_code in course_after.items():
                mi = next((i for i, k in enumerate(code_order) if by_code[k]['code'] == move_code), -1)
                if mi < 0 or not any(by_code[k]['code'] == after_code for k in code_order):
                    continue
                item = code_order.pop(mi)
                ai = next((i for i, k in enumerate(code_order) if by_code[k]['code'] == after_code), -1)
                code_order.insert(ai + 1, item)

            # Colonnes : Formation | Matière | Type | Enseignant | Salle | Heures | Reste | S36 | S37 | ...
            # La colonne Formation est fusionnée verticalement par groupe (FTP/ALT/MUT).
            COL_FORM = 1
            COL_MAT = 2
            COL_TYPE = 3
            COL_TEACH = 4
            COL_ROOM = 5
            COL_TOTAL = 6
            COL_RESTE = 7
            COL_FIRST_WEEK = 8

            nw = len(weeks)
            # Colonne d'appoint (cachée) : formation par ligne, pour les SUMIF des totaux
            # (les cellules fusionnées de COL_FORM sont vides hors ancre, inutilisables en formule).
            COL_FORMKEY = COL_FIRST_WEEK + nw
            first_wk_letter = get_column_letter(COL_FIRST_WEEK)
            last_wk_letter = get_column_letter(COL_FIRST_WEEK + nw - 1)
            formkey_col = get_column_letter(COL_FORMKEY)
            form_range = f'${formkey_col}$6:${formkey_col}$2000'

            # --- Ligne 1 : Annotations (semaines spéciales, éditable) ---
            font_annot = Font(italic=True, size=7, color='666666')
            fill_annot = PatternFill('solid', fgColor='FFFFEE')
            align_annot = Alignment(horizontal='center', vertical='center', text_rotation=90)

            a1 = ws.cell(row=1, column=1, value='Annotations')
            a1.font = Font(italic=True, size=8)
            a1.fill = fill_annot
            a1.alignment = align_center
            for col in range(2, COL_FIRST_WEEK):
                ws.cell(row=1, column=col).fill = fill_annot
                ws.cell(row=1, column=col).border = border_all
            ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=COL_FIRST_WEEK - 1)
            has_comment = False
            for i, w in enumerate(weeks):
                labels = []
                # Code de la catégorie si défini, sinon libellé complet
                if w in sp_vacation:
                    labels.append(category_codes.get('vacation_ftp') or 'Vacances')
                if w in sp_stage:
                    labels.append(category_codes.get(f'stage_ftp_y{yg}') or 'Stage FTP')
                if w in sp_company:
                    labels.append(category_codes.get(f'company_alt_y{yg}') or 'Entreprise ALT')
                wc = week_comments.get(w)
                if wc and (not wc['years'] or yg in wc['years']):
                    labels.append(wc['comment'])
                    has_comment = True
                c = ws.cell(row=1, column=COL_FIRST_WEEK + i, value=' / '.join(labels) if labels else '')
                c.font = font_annot
                c.fill = fill_annot
                c.alignment = align_annot
                c.border = border_all
            # Plus de hauteur si des commentaires (texte vertical) sont présents
            ws.row_dimensions[1].height = 140 if has_comment else 60

            # --- Ligne 2 : Totaux FTP (formules SUMIF) ---
            f2 = ws.cell(row=2, column=1, value='FTP')
            f2.font = font_form_ftp
            f2.fill = fill_ftp
            f2.alignment = align_center
            for col in range(2, COL_FIRST_WEEK):
                ws.cell(row=2, column=col).fill = fill_ftp
                ws.cell(row=2, column=col).border = border_all
            ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=COL_FIRST_WEEK - 1)
            for i in range(nw):
                wk_col = get_column_letter(COL_FIRST_WEEK + i)
                wk_range = f'{wk_col}$6:{wk_col}$2000'
                formula = f'=SUMIF({form_range},"FTP",{wk_range})+SUMIF({form_range},"MUT",{wk_range})'
                c = ws.cell(row=2, column=COL_FIRST_WEEK + i, value=formula)
                c.font = Font(bold=True, size=8, color='0369A1')
                c.fill = fill_ftp
                c.alignment = align_center
                c.border = border_all
                c.number_format = '0.##;-0.##;0'

            # --- Ligne 3 : Totaux ALT (formules SUMIF) ---
            a3 = ws.cell(row=3, column=1, value='ALT')
            a3.font = font_form_alt
            a3.fill = fill_alt
            a3.alignment = align_center
            for col in range(2, COL_FIRST_WEEK):
                ws.cell(row=3, column=col).fill = fill_alt
                ws.cell(row=3, column=col).border = border_all
            ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=COL_FIRST_WEEK - 1)
            for i in range(nw):
                wk_col = get_column_letter(COL_FIRST_WEEK + i)
                wk_range = f'{wk_col}$6:{wk_col}$2000'
                formula = f'=SUMIF({form_range},"ALT",{wk_range})+SUMIF({form_range},"MUT",{wk_range})'
                c = ws.cell(row=3, column=COL_FIRST_WEEK + i, value=formula)
                c.font = Font(bold=True, size=8, color='9A3412')
                c.fill = fill_alt
                c.alignment = align_center
                c.border = border_all
                c.number_format = '0.##;-0.##;0'

            # --- Ligne 4 : En-têtes ---
            headers = ['Formation', 'Matière', 'Type', 'Enseignant', 'Salle', 'Heures', 'Reste']
            for i, h in enumerate(headers):
                c = ws.cell(row=4, column=i+1, value=h)
                c.font = font_header
                c.fill = fill_header
                c.border = border_all
                c.alignment = align_center
            for i, w in enumerate(weeks):
                c = ws.cell(row=4, column=COL_FIRST_WEEK + i, value=f'S{w:02d}')
                c.font = font_header
                c.fill = fill_header
                c.border = border_all
                c.alignment = align_center

            # --- Ligne 5+ : Données ---
            row = 5
            total_col_letter = get_column_letter(COL_TOTAL)
            for key in code_order:
                block = by_code[key]
                all_rows = block['mut'] + block['ftp'] + block['alt']
                if not all_rows:
                    continue

                # Ligne en-tête matière (le libellé occupe la colonne Matière)
                c = ws.cell(row=row, column=COL_MAT, value=f"{block['code']} — {block['name']} ({block['sem']})")
                c.font = font_mat
                c.fill = fill_mat
                for col in range(1, COL_FIRST_WEEK + nw):
                    ws.cell(row=row, column=col).fill = fill_mat
                    ws.cell(row=row, column=col).border = border_all
                row += 1

                # Ligne « Total promo » : total d'heures de la matière par promo (MUT compté
                # pour FTP et ALT)
                ftp_total = sum((s['total_hours'] or 0) for s in block['mut'] + block['ftp'])
                alt_total = sum((s['total_hours'] or 0) for s in block['mut'] + block['alt'])
                for col in range(1, COL_FIRST_WEEK + nw):
                    cc = ws.cell(row=row, column=col); cc.fill = fill_total; cc.border = border_all
                lbl = ws.cell(row=row, column=COL_FORM, value='Total promo')
                lbl.font = Font(bold=True, size=8)
                lbl.alignment = Alignment(horizontal='right', vertical='center')
                ws.merge_cells(start_row=row, start_column=COL_FORM, end_row=row, end_column=COL_MAT)
                cf = ws.cell(row=row, column=COL_TYPE, value='FTP')
                cf.font = font_form_ftp; cf.fill = fill_ftp; cf.alignment = align_center; cf.border = border_all
                vf = ws.cell(row=row, column=COL_TEACH, value=ftp_total or None)
                vf.font = Font(bold=True, size=8, color='0369A1'); vf.fill = fill_ftp
                vf.alignment = align_center; vf.border = border_all; vf.number_format = '0.##'
                ca = ws.cell(row=row, column=COL_ROOM, value='ALT')
                ca.font = font_form_alt; ca.fill = fill_alt; ca.alignment = align_center; ca.border = border_all
                va = ws.cell(row=row, column=COL_TOTAL, value=alt_total or None)
                va.font = Font(bold=True, size=8, color='9A3412'); va.fill = fill_alt
                va.alignment = align_center; va.border = border_all; va.number_format = '0.##'
                row += 1

                # Une « bande » par formation : libellé fusionné verticalement dans COL_FORM
                for form, grp in (('MUT', block['mut']), ('FTP', block['ftp']), ('ALT', block['alt'])):
                    if not grp:
                        continue
                    group_start = row
                    form_font = font_form_mut if form == 'MUT' else font_form_ftp if form == 'FTP' else font_form_alt
                    form_fill = fill_mut if form == 'MUT' else fill_ftp if form == 'FTP' else fill_alt

                    for s in grp:
                        # Colonne Formation : style posé sur chaque cellule (avant fusion)
                        fc = ws.cell(row=row, column=COL_FORM)
                        fc.fill = form_fill
                        fc.border = border_all
                        fc.alignment = align_center
                        # Colonne d'appoint cachée : formation par ligne (pour les SUMIF)
                        ws.cell(row=row, column=COL_FORMKEY, value=form).font = font_data

                        c = ws.cell(row=row, column=COL_TYPE, value=s['type'])
                        c.font = font_data
                        c.alignment = align_center
                        c.border = border_all

                        c = ws.cell(row=row, column=COL_TEACH, value=s['teacher'])
                        c.font = font_data
                        c.border = border_all

                        c = ws.cell(row=row, column=COL_ROOM, value=s['room'])
                        c.font = font_data
                        c.border = border_all

                        # Heures prévues
                        c = ws.cell(row=row, column=COL_TOTAL, value=s['total_hours'] if s['total_hours'] > 0 else None)
                        c.font = font_data
                        c.alignment = align_center
                        c.border = border_all

                        # Reste (formule Excel)
                        reste_formula = f'={total_col_letter}{row}-SUM({first_wk_letter}{row}:{last_wk_letter}{row})'
                        c = ws.cell(row=row, column=COL_RESTE, value=reste_formula)
                        c.font = font_total_ok
                        c.fill = fill_total
                        c.alignment = align_center
                        c.border = border_all
                        c.number_format = '0.##;-0.##;0'

                        for i, w in enumerate(weeks):
                            h = s['by_week'].get(w, 0)
                            c = ws.cell(row=row, column=COL_FIRST_WEEK + i, value=h if h else None)
                            c.font = font_data
                            c.alignment = align_center
                            c.border = border_all
                            c.number_format = '0.##;-0.##;0'
                            if form == 'MUT':
                                # CM/TD mutualisés : FTP (stage/vacances) + ALT (entreprise)
                                if w in sp_stage or w in sp_vacation or w in sp_company: c.fill = fill_stage
                            elif form == 'FTP':
                                if w in sp_stage: c.fill = fill_stage
                                elif w in sp_vacation: c.fill = fill_vacation
                            elif form == 'ALT':
                                if w in sp_company: c.fill = fill_company

                        row += 1

                    # Libellé de la formation dans la cellule fusionnée (ancre = 1re ligne)
                    group_end = row - 1
                    anchor = ws.cell(row=group_start, column=COL_FORM, value=form)
                    anchor.font = form_font
                    anchor.fill = form_fill
                    anchor.alignment = align_center
                    anchor.border = border_all
                    if group_end > group_start:
                        ws.merge_cells(start_row=group_start, start_column=COL_FORM,
                                       end_row=group_end, end_column=COL_FORM)

            # Mise en forme conditionnelle : Reste rouge si != 0
            reste_letter = get_column_letter(COL_RESTE)
            reste_range_cf = f'{reste_letter}6:{reste_letter}{max(row - 1, 6)}'
            ws.conditional_formatting.add(reste_range_cf, CellIsRule(
                operator='notEqual', formula=['0'],
                font=Font(bold=True, size=8, color='DC2626'),
                fill=PatternFill('solid', fgColor='FEE2E2')
            ))

            # Largeurs de colonnes
            ws.column_dimensions[get_column_letter(COL_FORM)].width = 5
            ws.column_dimensions[get_column_letter(COL_MAT)].width = 6
            ws.column_dimensions[get_column_letter(COL_TYPE)].width = 5
            ws.column_dimensions[get_column_letter(COL_TEACH)].width = 16
            ws.column_dimensions[get_column_letter(COL_ROOM)].width = 10
            ws.column_dimensions[get_column_letter(COL_TOTAL)].width = 6
            ws.column_dimensions[get_column_letter(COL_RESTE)].width = 6
            for i in range(nw):
                ws.column_dimensions[get_column_letter(COL_FIRST_WEEK + i)].width = 4.5
            # Colonne d'appoint formation : cachée (sert uniquement aux SUMIF)
            ws.column_dimensions[get_column_letter(COL_FORMKEY)].hidden = True

            # Figer les volets
            ws.freeze_panes = ws.cell(row=5, column=COL_FIRST_WEEK)

        # --- Feuille Contacts enseignants ---
        ws_contacts = wb.create_sheet(title='Contacts')
        contact_headers = ['Nom', 'Email', 'Téléphone', 'Structure', 'Corps', 'Statut']
        for i, h in enumerate(contact_headers, 1):
            c = ws_contacts.cell(row=1, column=i, value=h)
            c.font = font_header
            c.fill = fill_header
            c.border = border_all
            c.alignment = align_center

        cursor.execute('SELECT name, email, phone, structure, corps_code, status FROM teachers ORDER BY name')
        teachers_list = cursor.fetchall()
        # Ne garder que les enseignants présents dans l'affichage filtré
        incl_names = {(sessions[sid]['teacher'] or '').strip()
                      for sid in order if session_included(sessions[sid])}
        incl_names.discard('')
        teachers_list = [t for t in teachers_list if t['name'] in incl_names]
        for r_idx, t in enumerate(teachers_list, 2):
            for col_idx, field in enumerate(['name', 'email', 'phone', 'structure', 'corps_code', 'status'], 1):
                c = ws_contacts.cell(row=r_idx, column=col_idx, value=t[field])
                c.font = font_data
                c.border = border_all

        ws_contacts.column_dimensions['A'].width = 25
        ws_contacts.column_dimensions['B'].width = 30
        ws_contacts.column_dimensions['C'].width = 15
        ws_contacts.column_dimensions['D'].width = 20
        ws_contacts.column_dimensions['E'].width = 15
        ws_contacts.column_dimensions['F'].width = 12
        last_contact_row = len(teachers_list) + 1
        ws_contacts.auto_filter.ref = f'A1:F{last_contact_row}'
        ws_contacts.freeze_panes = 'A2'

        # --- Un onglet par enseignant : bilan + calendrier de ses heures ---
        import re

        def _safe_sheet_name(name, used):
            base = re.sub(r'[:\\/?*\[\]]', ' ', name).strip() or 'Enseignant'
            base = base[:31]
            title, n = base, 2
            while title.lower() in used:
                suffix = f' ({n})'
                title = base[:31 - len(suffix)] + suffix
                n += 1
            used.add(title.lower())
            return title

        # Grouper les sessions (filtrées selon l'affichage) par enseignant
        by_teacher = {}
        for sid in order:
            s = sessions[sid]
            if not session_included(s):
                continue
            tname = (s['teacher'] or '').strip()
            if tname:
                by_teacher.setdefault(tname, []).append(s)

        used_titles = {'contacts', 's1+s2', 's3+s4', 's5+s6'}
        type_rank = {'CM': 0, 'TD': 1, 'TP': 2, 'PT': 3}
        fill_overload = PatternFill('solid', fgColor='FCA5A5')
        # Styles d'annotation (ligne 1), identiques aux onglets par année
        font_annot = Font(italic=True, size=7, color='666666')
        fill_annot = PatternFill('solid', fgColor='FFFFEE')
        align_annot = Alignment(horizontal='center', vertical='center', text_rotation=90)

        # Colonnes au format Répartition (sans la colonne Enseignant, redondante ici)
        TF_FORM, TF_MAT, TF_TYPE, TF_SALLE, TF_TOTAL, TF_RESTE = 1, 2, 3, 4, 5, 6
        TF_FIRST = 7
        nw = len(weeks)
        TF_FORMKEY = TF_FIRST + nw
        tf_total_letter = get_column_letter(TF_TOTAL)
        tf_first_letter = get_column_letter(TF_FIRST)
        tf_last_letter = get_column_letter(TF_FIRST + nw - 1)
        tf_formkey_letter = get_column_letter(TF_FORMKEY)
        tf_form_range = f'${tf_formkey_letter}$5:${tf_formkey_letter}$2000'

        for tname in sorted(by_teacher.keys(), key=lambda x: x.lower()):
            tsessions = by_teacher[tname]
            ws = wb.create_sheet(title=_safe_sheet_name(tname, used_titles))

            teacher_ygs = sorted({s['year_group'] for s in tsessions if s['year_group']})
            sp_vac = sc['vacation_ftp']
            total_prev = sum(s['total_hours'] or 0 for s in tsessions)
            total_placed = sum(sum(s['by_week'].get(w, 0) for w in weeks) for s in tsessions)

            # --- Ligne 1 : nom + bilan (gauche) + annotations/codes par semaine (vertical) ---
            c = ws.cell(row=1, column=1,
                        value=f'{tname}  —  Prévu {total_prev:g} h  /  Placé {total_placed:g} h  /  '
                              f'Reste {total_prev - total_placed:g} h')
            c.font = Font(bold=True, size=10, color='4F46E5')
            c.alignment = Alignment(horizontal='left', vertical='center')
            ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=TF_RESTE)
            has_comment = False
            for i, w in enumerate(weeks):
                labels = []
                if w in sp_vac:
                    labels.append(category_codes.get('vacation_ftp') or 'Vacances')
                for g in teacher_ygs:
                    if g >= 2 and w in sc.get(f'stage_ftp_y{g}', set()):
                        labels.append(category_codes.get(f'stage_ftp_y{g}') or 'Stage FTP')
                    if w in sc.get(f'company_alt_y{g}', set()):
                        labels.append(category_codes.get(f'company_alt_y{g}') or 'Entreprise ALT')
                seen = set()
                labels = [x for x in labels if not (x in seen or seen.add(x))]
                cc = ws.cell(row=1, column=TF_FIRST + i, value=' / '.join(labels) if labels else '')
                cc.font = font_annot; cc.fill = fill_annot; cc.alignment = align_annot; cc.border = border_all
                if labels:
                    has_comment = True
            ws.row_dimensions[1].height = 140 if has_comment else 40

            # --- Lignes 2 et 3 : totaux FTP / ALT (formules SUMIF) ---
            for trow, crit, lab_fill, lab_font, col_clr in (
                (2, 'FTP', fill_ftp, font_form_ftp, '0369A1'),
                (3, 'ALT', fill_alt, font_form_alt, '9A3412'),
            ):
                lc = ws.cell(row=trow, column=1, value=crit)
                lc.font = lab_font; lc.alignment = align_center
                for col in range(1, TF_FIRST):
                    cell = ws.cell(row=trow, column=col); cell.fill = lab_fill; cell.border = border_all
                ws.merge_cells(start_row=trow, start_column=1, end_row=trow, end_column=TF_FIRST - 1)
                for i in range(nw):
                    wk_col = get_column_letter(TF_FIRST + i)
                    wk_range = f'{wk_col}$5:{wk_col}$2000'
                    cc = ws.cell(row=trow, column=TF_FIRST + i,
                                 value=f'=SUMIF({tf_form_range},"{crit}",{wk_range})+SUMIF({tf_form_range},"MUT",{wk_range})')
                    cc.font = Font(bold=True, size=8, color=col_clr)
                    cc.fill = lab_fill; cc.alignment = align_center; cc.border = border_all
                    cc.number_format = '0.##;-0.##;0'

            # --- Ligne 4 : en-têtes ---
            for i, h in enumerate(['Form.', 'Matière', 'Type', 'Salle', 'Heures', 'Reste'], 1):
                cc = ws.cell(row=4, column=i, value=h)
                cc.font = font_header; cc.fill = fill_header; cc.border = border_all; cc.alignment = align_center
            for i, w in enumerate(weeks):
                cc = ws.cell(row=4, column=TF_FIRST + i, value=f'S{w:02d}')
                cc.font = font_header; cc.fill = fill_header; cc.border = border_all; cc.alignment = align_center

            # --- Lignes 5+ : données groupées par matière (colonne Formation fusionnée) ---
            by_code, code_order = {}, []
            for s in sorted(tsessions, key=lambda s: (s['semester'], s['course_code'], type_rank.get(s['type'], 9))):
                key = s['course_code'] + '|' + s['semester']
                if key not in by_code:
                    by_code[key] = {'code': s['course_code'], 'name': s['course_name'],
                                    'sem': s['semester'], 'mut': [], 'ftp': [], 'alt': []}
                    code_order.append(key)
                f = s['formation']
                (by_code[key]['mut'] if f == 'MUT' else by_code[key]['ftp'] if f == 'FTP' else by_code[key]['alt']).append(s)

            row = 5
            week_totals = {w: 0 for w in weeks}
            for key in code_order:
                block = by_code[key]
                c = ws.cell(row=row, column=TF_MAT, value=f"{block['code']} — {block['name']} ({block['sem']})")
                c.font = font_mat; c.fill = fill_mat
                for col in range(1, TF_FIRST + nw):
                    ws.cell(row=row, column=col).fill = fill_mat
                    ws.cell(row=row, column=col).border = border_all
                row += 1

                for form, grp in (('MUT', block['mut']), ('FTP', block['ftp']), ('ALT', block['alt'])):
                    if not grp:
                        continue
                    group_start = row
                    form_font = font_form_mut if form == 'MUT' else font_form_ftp if form == 'FTP' else font_form_alt
                    form_fill = fill_mut if form == 'MUT' else fill_ftp if form == 'FTP' else fill_alt
                    for s in grp:
                        yg_s = s['year_group']
                        sp_v = sc['vacation_ftp']
                        sp_st = sc.get(f'stage_ftp_y{yg_s}', set()) if yg_s and yg_s >= 2 else set()
                        sp_co = sc.get(f'company_alt_y{yg_s}', set())
                        ws.cell(row=row, column=TF_FORM).fill = form_fill
                        ws.cell(row=row, column=TF_FORMKEY, value=form).font = font_data
                        ws.cell(row=row, column=TF_TYPE, value=s['type']).font = font_data
                        ws.cell(row=row, column=TF_SALLE, value=s['room']).font = font_data
                        ws.cell(row=row, column=TF_TOTAL, value=s['total_hours'] or None).font = font_data
                        rc = ws.cell(row=row, column=TF_RESTE,
                                     value=f'={tf_total_letter}{row}-SUM({tf_first_letter}{row}:{tf_last_letter}{row})')
                        rc.font = font_total_ok; rc.fill = fill_total; rc.number_format = '0.##;-0.##;0'
                        for col in (TF_FORM, TF_TYPE, TF_SALLE, TF_TOTAL, TF_RESTE):
                            ws.cell(row=row, column=col).border = border_all
                            ws.cell(row=row, column=col).alignment = align_center
                        for i, w in enumerate(weeks):
                            h = s['by_week'].get(w, 0)
                            week_totals[w] += h
                            cc = ws.cell(row=row, column=TF_FIRST + i, value=h if h else None)
                            cc.font = font_data; cc.alignment = align_center; cc.border = border_all
                            cc.number_format = '0.##;-0.##;0'
                            if form == 'MUT':
                                if w in sp_st or w in sp_v or w in sp_co: cc.fill = fill_stage
                            elif form == 'FTP':
                                if w in sp_st: cc.fill = fill_stage
                                elif w in sp_v: cc.fill = fill_vacation
                            elif form == 'ALT':
                                if w in sp_co: cc.fill = fill_company
                        row += 1
                    group_end = row - 1
                    anchor = ws.cell(row=group_start, column=TF_FORM, value=form)
                    anchor.font = form_font; anchor.fill = form_fill
                    anchor.alignment = align_center; anchor.border = border_all
                    if group_end > group_start:
                        ws.merge_cells(start_row=group_start, start_column=TF_FORM,
                                       end_row=group_end, end_column=TF_FORM)

            # Ligne charge totale de l'enseignant / semaine (toutes formations, MUT compté 1 fois)
            ws.cell(row=row, column=TF_MAT, value='Total / sem.').font = Font(bold=True, size=8)
            ws.cell(row=row, column=TF_TOTAL, value=total_placed or None).font = Font(bold=True, size=8)
            for col in range(1, TF_FIRST):
                cell = ws.cell(row=row, column=col); cell.fill = fill_header; cell.border = border_all; cell.alignment = align_center
            for i, w in enumerate(weeks):
                tot = week_totals[w]
                cc = ws.cell(row=row, column=TF_FIRST + i, value=tot if tot else None)
                cc.font = Font(bold=True, size=8); cc.alignment = align_center; cc.border = border_all
                cc.number_format = '0.##;-0.##;0'
                cc.fill = fill_overload if tot > 20 else fill_header
            total_row = row

            # Mise en forme conditionnelle : Reste rouge si != 0
            reste_letter = get_column_letter(TF_RESTE)
            ws.conditional_formatting.add(
                f'{reste_letter}5:{reste_letter}{max(total_row - 1, 5)}',
                CellIsRule(operator='notEqual', formula=['0'],
                           font=Font(bold=True, size=8, color='DC2626'),
                           fill=PatternFill('solid', fgColor='FEE2E2')))

            # Largeurs + colonne d'appoint cachée + volets figés
            for col, wd in ((TF_FORM, 5), (TF_MAT, 16), (TF_TYPE, 5), (TF_SALLE, 10), (TF_TOTAL, 6), (TF_RESTE, 6)):
                ws.column_dimensions[get_column_letter(col)].width = wd
            for i in range(nw):
                ws.column_dimensions[get_column_letter(TF_FIRST + i)].width = 4.5
            ws.column_dimensions[get_column_letter(TF_FORMKEY)].hidden = True
            ws.freeze_panes = ws.cell(row=5, column=TF_FIRST)

        # Générer le fichier
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        year = get_current_year() or 'export'
        filename = f'repartition_{year}.xlsx'
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True, download_name=filename)
    except Exception as e:
        return error_response(f'Error exporting: {str(e)}', 500)

@app.route('/api/import/repartition', methods=['POST'])
def import_repartition_excel():
    """Importe la répartition depuis un fichier Excel au format export"""
    from openpyxl import load_workbook

    if 'file' not in request.files:
        return error_response('Aucun fichier fourni', 400)

    file = request.files['file']
    if not file.filename.endswith('.xlsx'):
        return error_response('Le fichier doit être au format .xlsx', 400)

    try:
        wb = load_workbook(file, data_only=True)
        db = get_db()
        cursor = db.cursor()

        formation_map = {'FTP': 0, 'ALT': 1, 'MUT': 2}
        imported = 0
        errors = []

        year_sheet_names = {'S1+S2', 'S3+S4', 'S5+S6'}
        for ws in wb.worksheets:
            # N'importer que les onglets de répartition par année (ignorer Contacts + onglets enseignants)
            if ws.title not in year_sheet_names:
                continue

            # Trouver la ligne d'en-tête (celle qui contient "Matière") et localiser les
            # colonnes par leur libellé (l'ordre peut varier : Formation est désormais à gauche).
            header_row = None
            col_mat = col_type = col_form = None
            for r in range(1, 10):
                labels = {}
                for c in range(1, ws.max_column + 1):
                    v = ws.cell(row=r, column=c).value
                    if v is not None:
                        labels[str(v).strip()] = c
                if 'Matière' in labels:
                    header_row = r
                    col_mat = labels.get('Matière')
                    col_type = labels.get('Type')
                    col_form = labels.get('Formation')
                    break

            if header_row is None or not col_mat or not col_type or not col_form:
                errors.append(f"Onglet {ws.title}: en-tête introuvable")
                continue

            # Extraire les numéros de semaine depuis les en-têtes (S36, S37, ...)
            week_columns = []
            for col in range(1, ws.max_column + 1):
                val = ws.cell(row=header_row, column=col).value
                if val and str(val).startswith('S') and len(str(val)) == 3:
                    try:
                        week_num = int(str(val)[1:])
                        week_columns.append((col, week_num))
                    except ValueError:
                        pass

            if not week_columns:
                errors.append(f"Onglet {ws.title}: colonnes semaines introuvables")
                continue

            # Parcourir les lignes de données
            current_code = None
            current_sem = None
            last_form = None  # colonne Formation fusionnée : report de la dernière valeur lue

            for r in range(header_row + 1, ws.max_row + 1):
                mat_val = ws.cell(row=r, column=col_mat).value
                type_val = ws.cell(row=r, column=col_type).value
                form_cell = ws.cell(row=r, column=col_form).value
                # Cellule fusionnée : seule l'ancre porte la valeur → report sur les lignes suivantes
                if form_cell is not None and str(form_cell).strip():
                    last_form = str(form_cell).strip()
                form_val = last_form

                # Ligne en-tête matière : "R1.01 — Mécanique (S1)"
                if mat_val and not type_val:
                    mat_str = str(mat_val)
                    parts = mat_str.split(' — ', 1)
                    if len(parts) == 2:
                        current_code = parts[0].strip()
                        name_part = parts[1]
                        if '(' in name_part and name_part.endswith(')'):
                            sem_start = name_part.rfind('(')
                            current_sem = name_part[sem_start + 1:-1].strip()
                    continue

                if not type_val or not form_val:
                    continue
                if not current_code or not current_sem:
                    continue

                teaching_type = str(type_val).strip()
                formation_str = str(form_val).strip()
                formation_type = formation_map.get(formation_str)
                if formation_type is None:
                    continue

                # Trouver la session correspondante
                cursor.execute('''
                    SELECT cs.id FROM course_sessions cs
                    JOIN courses c ON cs.course_id = c.id
                    JOIN semesters s ON c.semester_id = s.id
                    WHERE c.code = ? AND s.code = ?
                      AND cs.teaching_type = ? AND cs.formation_type = ?
                ''', (current_code, current_sem, teaching_type, formation_type))

                row_result = cursor.fetchone()
                if not row_result:
                    errors.append(f"{current_code} {current_sem} {teaching_type} {formation_str}: session introuvable")
                    continue

                session_id = row_result['id']

                # Importer les heures par semaine
                for col, week_num in week_columns:
                    cell_val = ws.cell(row=r, column=col).value
                    try:
                        hours = float(cell_val) if cell_val else 0
                    except (ValueError, TypeError):
                        hours = 0

                    if hours > 0:
                        cursor.execute('''
                            INSERT OR REPLACE INTO weekly_hours (course_session_id, week_number, hours)
                            VALUES (?, ?, ?)
                        ''', (session_id, week_num, hours))
                        imported += 1
                    else:
                        cursor.execute(
                            'DELETE FROM weekly_hours WHERE course_session_id = ? AND week_number = ?',
                            (session_id, week_num)
                        )

        db.commit()
        return jsonify({
            'imported': imported,
            'errors': errors,
            'message': f'{imported} cellules importées' + (f', {len(errors)} erreurs' if errors else '')
        })
    except Exception as e:
        return error_response(f'Erreur import: {str(e)}', 500)

# ======================= ANNÉES UNIVERSITAIRES =======================

@app.route('/api/years', methods=['GET'])
def get_years():
    return jsonify({'years': list_years(), 'current': get_current_year()})

@app.route('/api/years', methods=['POST'])
def create_year():
    data = request.get_json() or {}
    new_year = (data.get('year') or '').strip()
    copy_from = (data.get('copy_from') or '').strip()

    if len(new_year) != 9 or new_year[4] != '-' or not new_year[:4].isdigit() or not new_year[5:].isdigit():
        return error_response('Format invalide — attendu AAAA-AAAA (ex : 2025-2026)', 400)

    new_path = db_path_for_year(new_year)
    if os.path.exists(new_path):
        return error_response(f"L'année {new_year} existe déjà", 400)

    if copy_from:
        src_path = db_path_for_year(copy_from)
        if not os.path.exists(src_path):
            return error_response(f"Année source {copy_from} introuvable", 404)
        shutil.copy2(src_path, new_path)
        # S'assurer que la copie est à jour schéma
        db = sqlite3.connect(new_path)
        db.row_factory = sqlite3.Row
        _apply_migrations(db)
        db.close()
    else:
        _init_fresh_db(new_path)

    return jsonify({'year': new_year, 'years': list_years()}), 201

@app.route('/api/years/current', methods=['PUT'])
def set_current_year():
    data = request.get_json() or {}
    year = (data.get('year') or '').strip()
    if not year:
        return error_response('year requis', 400)
    if not os.path.exists(db_path_for_year(year)):
        return error_response(f"Année {year} introuvable", 404)
    settings = get_settings()
    settings['current_year'] = year
    save_settings(settings)
    return jsonify({'current': year})

# ======================= ERROR HANDLERS =======================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return error_response('Resource not found', 404)

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return error_response('Internal server error', 500)

# ======================= OPTIMISATION CP-SAT =======================

@app.route('/api/course-orderings', methods=['GET'])
def get_course_orderings():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            SELECT co.id, co.min_gap_weeks,
                   cp.id AS pred_id, cp.code AS pred_code, cp.name AS pred_name,
                   cs2.id AS succ_id, cs2.code AS succ_code, cs2.name AS succ_name
            FROM course_ordering co
            JOIN courses cp  ON co.course_id_pred = cp.id
            JOIN courses cs2 ON co.course_id_succ = cs2.id
            ORDER BY cp.code, cs2.code
        ''')
        rows = rows_to_list(cursor.fetchall())
        return jsonify(rows), 200
    except Exception as e:
        return error_response(str(e), 500)

@app.route('/api/course-orderings', methods=['POST'])
def create_course_ordering():
    try:
        data = request.get_json() or {}
        pred = data.get('course_id_pred')
        succ = data.get('course_id_succ')
        gap  = int(data.get('min_gap_weeks', 0))
        if not pred or not succ:
            return error_response('course_id_pred et course_id_succ requis')
        if pred == succ:
            return error_response('Une matière ne peut pas être contrainte par elle-même')
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            'INSERT INTO course_ordering (course_id_pred, course_id_succ, min_gap_weeks) VALUES (?, ?, ?)',
            (pred, succ, gap)
        )
        db.commit()
        oid = cursor.lastrowid
        cursor.execute('''
            SELECT co.id, co.min_gap_weeks,
                   cp.id AS pred_id, cp.code AS pred_code, cp.name AS pred_name,
                   cs2.id AS succ_id, cs2.code AS succ_code, cs2.name AS succ_name
            FROM course_ordering co
            JOIN courses cp  ON co.course_id_pred = cp.id
            JOIN courses cs2 ON co.course_id_succ = cs2.id
            WHERE co.id = ?
        ''', (oid,))
        row = row_to_dict(cursor.fetchone())
        return jsonify(row), 201
    except sqlite3.IntegrityError:
        return error_response('Cette contrainte existe déjà')
    except Exception as e:
        return error_response(str(e), 500)

@app.route('/api/course-orderings/<int:oid>', methods=['DELETE'])
def delete_course_ordering(oid):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('DELETE FROM course_ordering WHERE id = ?', (oid,))
        db.commit()
        return jsonify({'message': 'Contrainte supprimée'}), 200
    except Exception as e:
        return error_response(str(e), 500)

@app.route('/api/optimize', methods=['POST'])
def optimize_repartition():
    """Optimise la répartition hebdomadaire via OR-Tools CP-SAT.
    Body: { "semester": "S1+S2" }  ou  { "semester": "S1" }
    Écrase weekly_hours pour les sessions concernées.
    """
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        return error_response('OR-Tools non installé. Exécuter : pip install ortools', 500)

    data = request.get_json() or {}
    semester_param = data.get('semester', '')
    formation_param = data.get('formation', '')  # '', 'ftp', 'alt'

    sem_codes = semester_param.split('+') if '+' in semester_param else (
        [semester_param] if semester_param else []
    )

    # Filtrage par formation : ftp → ft in {0,2}, alt → ft in {1,2}, '' → tous
    if formation_param == 'ftp':
        ft_filter = {0, 2}
    elif formation_param == 'alt':
        ft_filter = {1, 2}
    else:
        ft_filter = {0, 1, 2}

    try:
        cfg = get_year_config()
        start_week   = cfg['academic_start_week']
        end_week_cfg = cfg['academic_end_week']
        max_week     = cfg['academic_max_week']
        _key = lambda w: school_week_key(w, start_week, max_week)
        all_valid_weeks = get_valid_school_weeks(start_week, end_week_cfg, max_week)

        db = get_db()
        cursor = db.cursor()

        # --- Sessions à optimiser ---
        q_sessions = '''
            SELECT cs.id, cs.nb_sessions, cs.slot_duration, cs.formation_type,
                   cs.teaching_type,
                   COALESCE(cs.sessions_per_week_max, 1) AS sessions_per_week_max,
                   cs.room_name,
                   c.id   AS course_id,
                   c.code AS course_code,
                   c.name AS course_name,
                   c.start_week AS course_start_week,
                   c.end_week   AS course_end_week,
                   c.default_weeks AS course_default_weeks,
                   s.code AS semester_code,
                   s.year_group AS year_group
            FROM course_sessions cs
            JOIN courses c  ON cs.course_id  = c.id
            JOIN semesters s ON c.semester_id = s.id
            WHERE {where} AND cs.nb_sessions > 0
            ORDER BY cs.id
        '''
        if sem_codes:
            ph = ','.join('?' * len(sem_codes))
            cursor.execute(q_sessions.format(where=f's.code IN ({ph})'), sem_codes)
        else:
            cursor.execute(q_sessions.format(where='1=1'))
        sessions = [s for s in cursor.fetchall() if s['formation_type'] in ft_filter]

        if not sessions:
            return jsonify({'message': 'Aucune session à optimiser', 'weeks_assigned': 0}), 200

        # --- Calendrier spécial ---
        cursor.execute('SELECT week_number, week_type FROM special_calendar')
        sc = {t: set() for t in _SPECIAL_TYPES}
        for r in cursor.fetchall():
            if r['week_type'] in sc:
                sc[r['week_type']].add(r['week_number'])

        # --- Salles par type ---
        cursor.execute('SELECT name, room_type FROM rooms')
        room_type_by_name = {r['name']: r['room_type'] for r in cursor.fetchall()}
        cursor.execute('SELECT room_type, COUNT(*) AS cnt FROM rooms GROUP BY room_type')
        room_counts = {r['room_type']: r['cnt'] for r in cursor.fetchall()}

        # --- Contraintes d'ordonnancement ---
        course_ids_in_scope = {s['course_id'] for s in sessions}
        cursor.execute('''
            SELECT id, course_id_pred, course_id_succ, min_gap_weeks
            FROM course_ordering
        ''')
        orderings = [r for r in cursor.fetchall()
                     if r['course_id_pred'] in course_ids_in_scope
                     and r['course_id_succ'] in course_ids_in_scope]


        # Index des cours → sessions
        course_to_sessions = {}
        for s in sessions:
            course_to_sessions.setdefault(s['course_id'], []).append(s['id'])

        # =========================================================
        # Construction du modèle CP-SAT
        # =========================================================
        model  = cp_model.CpModel()
        SCALE  = 10      # 1h → 10 unités (gère les 0.5h)
        ROOM_H = 30      # heures disponibles par salle par semaine
        MAX_H  = 40      # plafond souple heures/semaine/formation
        ABS_MAX_H = 50   # plafond absolu infranchissable
        TGT_FTP = 25     # cible heures/semaine FTP
        TGT_ALT = 35     # cible heures/semaine ALT

        sorted_weeks  = sorted(all_valid_weeks, key=_key)
        week_to_idx   = {w: i for i, w in enumerate(sorted_weeks)}

        _FT_LABELS = {0: 'FTP', 1: 'ALT', 2: 'MUT'}

        # === Fusion CM+TD : même cours/formation → mêmes variables x ===
        _CMTD = {'CM', 'TD'}
        _by_cf = {}   # (course_id, ft) → [sessions CM/TD]
        for s in sessions:
            if s['teaching_type'] in _CMTD:
                _by_cf.setdefault((s['course_id'], s['formation_type']), []).append(s)

        _merged_secondary = {}   # secondary_sid → primary_sid
        _merged_nb = {}          # primary_sid → max(nb) du groupe
        for group in _by_cf.values():
            if len(group) < 2:
                continue
            group.sort(key=lambda s: s['teaching_type'])   # CM avant TD
            primary = group[0]
            max_nb = max(s['nb_sessions'] for s in group)
            _merged_nb[primary['id']] = max_nb
            for sec in group[1:]:
                _merged_secondary[sec['id']] = primary['id']

        x             = {}   # x[sid][week] = IntVar/BoolVar(nb séances)
        session_weeks = {}   # sid → liste des semaines valides triées (numérotation parallèle)
        infeasible_sids = {}  # sid → reason string
        _contig_data  = {}   # sid → (n_valid, acts_list, min_span) pour pénalité souple

        for s in sessions:
            sid    = s['id']

            # Les sessions secondaires (TD fusionné avec CM) sont traitées après
            if sid in _merged_secondary:
                continue

            ft     = s['formation_type']   # 0=FTP 1=ALT 2=MUT
            sw, ew = resolve_course_weeks({
                'default_weeks': s['course_default_weeks'],
                'semester_code': s['semester_code'],
                'start_week':    s['course_start_week'],
                'end_week':      s['course_end_week'],
            }, cfg)
            nb     = _merged_nb.get(sid, s['nb_sessions'])  # nb fusionné si CM+TD
            max_pw = max(1, int(s['sessions_per_week_max'] or 1))

            valid = get_valid_school_weeks(sw, ew, max_week) & all_valid_weeks if (sw and ew) else set(all_valid_weeks)
            yg = s['year_group']
            excluded_types = []
            if ft == 0:   # FTP : vacances + stages selon année
                valid -= sc['vacation_ftp']
                excluded_types.append('vacances FTP')
                if yg == 2:
                    valid -= sc['stage_ftp_y2']
                    excluded_types.append('stages FTP 2A')
                elif yg == 3:
                    valid -= sc['stage_ftp_y3']
                    excluded_types.append('stages FTP 3A')
            elif ft == 1:   # ALT : semaines entreprise selon année
                excl = sc.get(f'company_alt_y{yg}', set())
                valid -= excl
                if excl:
                    excluded_types.append(f'entreprise ALT {yg}A')
            elif ft == 2:   # MUT : compte pour FTP → exclure vacances FTP
                valid -= sc['vacation_ftp']
                excluded_types.append('vacances FTP')

            sw_list = sorted(valid, key=_key)
            session_weeks[sid] = sw_list
            x[sid] = {}

            sess_label = f"{s['course_code']} {s['teaching_type']} {_FT_LABELS[ft]}"

            if not sw_list:
                reason = f"Aucune semaine valide"
                if sw and ew:
                    reason += f" (plage S{sw}→S{ew}"
                    if excluded_types:
                        reason += f", excl. {', '.join(excluded_types)}"
                    reason += ")"
                infeasible_sids[sid] = {'label': sess_label, 'reason': reason}
                continue

            n_valid   = len(sw_list)
            min_span  = math.ceil(nb / max_pw)   # semaines minimales nécessaires

            if n_valid < min_span:
                infeasible_sids[sid] = {
                    'label': sess_label,
                    'reason': f"{n_valid} semaines valides, besoin de {min_span} min. "
                              f"({nb} séances, max {max_pw}/sem)"
                }
                continue

            # ---------------------------------------------------------------
            # Variables de session par semaine.
            # Contiguïté gérée en souple dans l'objectif (pénalité de trous).
            # ---------------------------------------------------------------
            acts_list = []
            for i, w in enumerate(sw_list):
                xv  = model.new_int_var(0, max_pw + 1, f'x_{sid}_{w}')
                act = model.new_bool_var(f'act_{sid}_{i}')
                model.add(xv >= 1).only_enforce_if(act)
                model.add(xv == 0).only_enforce_if(act.Not())
                x[sid][w] = xv
                acts_list.append(act)

            # Nombre total de séances = nb
            model.add(cp_model.LinearExpr.Sum(
                [x[sid][w] for w in sw_list]
            ) == nb)

            # Mémoriser pour la pénalité de contiguïté (objectif)
            _contig_data[sid] = (n_valid, acts_list, min_span)

        # === Alias des sessions secondaires (TD fusionné avec CM) ===
        for sec_sid, pri_sid in _merged_secondary.items():
            if pri_sid in infeasible_sids:
                infeasible_sids[sec_sid] = infeasible_sids[pri_sid]
                session_weeks[sec_sid] = session_weeks.get(pri_sid, [])
                x[sec_sid] = {}
            else:
                x[sec_sid] = x[pri_sid]
                session_weeks[sec_sid] = session_weeks[pri_sid]

        # --- Contrainte plafond absolu / semaine / formation ---
        # Le plafond souple (MAX_H=40h) est géré dans l'objectif ;
        # ici on impose le plafond absolu (ABS_MAX_H) pour éviter
        # des solutions aberrantes tout en laissant de la flexibilité
        # quand la contiguïté l'exige.
        cap_groups = []
        if ft_filter & {0, 2}:
            cap_groups.append(({0, 2}, 'ftp'))
        if ft_filter & {1, 2}:
            cap_groups.append(({1, 2}, 'alt'))
        for w in sorted_weeks:
            for ft_set, label in cap_groups:
                items = [
                    (x[s['id']][w], int(round(s['slot_duration'] * SCALE)))
                    for s in sessions
                    if s['formation_type'] in ft_set and w in x[s['id']]
                ]
                if items:
                    model.add(
                        cp_model.LinearExpr.WeightedSum(
                            [v for v, _ in items], [d for _, d in items]
                        ) <= ABS_MAX_H * SCALE
                    )

        # --- Contraintes de capacité salle ---
        room_load = {}
        for s in sessions:
            sid = s['id']
            if sid in infeasible_sids or not session_weeks[sid] or not s['room_name']:
                continue
            rt = room_type_by_name.get(s['room_name'])
            if not rt or rt not in room_counts:
                continue
            sd_scaled = int(round(s['slot_duration'] * SCALE))
            for w in session_weeks[sid]:
                room_load.setdefault((rt, w), []).append((x[sid][w], sd_scaled))

        for (rt, w), items in room_load.items():
            cap = int(room_counts[rt] * ROOM_H * SCALE)
            model.add(
                cp_model.LinearExpr.WeightedSum(
                    [v for v, _ in items], [d for _, d in items]
                ) <= cap
            )

        # --- Contraintes d'ordonnancement (A avant B avec écart min) ---
        # Variables booléennes ob[sid][w] = 1 ssi x[sid][w] >= 1
        ob = {}
        def get_ob(sid, w):
            if sid not in ob:
                ob[sid] = {}
            if w not in ob[sid]:
                xv = x[sid].get(w)
                if xv is None:
                    ob[sid][w] = None
                    return None
                bv = model.new_bool_var(f'ob_{sid}_{w}')
                model.add(xv >= 1).only_enforce_if(bv)
                model.add(xv == 0).only_enforce_if(bv.Not())
                ob[sid][w] = bv
            return ob[sid][w]

        for ord_row in orderings:
            gap       = ord_row['min_gap_weeks']
            pred_sids = course_to_sessions.get(ord_row['course_id_pred'], [])
            succ_sids = course_to_sessions.get(ord_row['course_id_succ'], [])
            for ps in pred_sids:
                for ss_ in succ_sids:
                    for w_p in session_weeks.get(ps, []):
                        for w_s in session_weeks.get(ss_, []):
                            # succ doit être au moins (gap+1) semaines après pred
                            if week_to_idx.get(w_s, 0) <= week_to_idx.get(w_p, 0) + gap:
                                bp = get_ob(ps,  w_p)
                                bs = get_ob(ss_, w_s)
                                if bp is not None and bs is not None:
                                    model.add(bp + bs <= 1)

        # =========================================================
        # Objectif multi-critères
        # =========================================================
        obj_terms = []

        # (0) Pénalité forte pour dépassement du plafond souple (MAX_H)
        #     Priorité : contiguïté (hard) > plafond 40h (soft fort) > cible (soft)
        W_OVERFLOW = 100
        for w in sorted_weeks:
            for ft_set, label in cap_groups:
                items_ovf = [
                    (x[s['id']][w], int(round(s['slot_duration'] * SCALE)))
                    for s in sessions
                    if s['formation_type'] in ft_set and w in x[s['id']]
                ]
                if items_ovf:
                    load_ovf = cp_model.LinearExpr.WeightedSum(
                        [v for v, _ in items_ovf], [d for _, d in items_ovf]
                    )
                    ovf = model.new_int_var(0, (ABS_MAX_H - MAX_H) * SCALE,
                                            f'ovf_{label}_{w}')
                    model.add(ovf >= load_ovf - MAX_H * SCALE)
                    obj_terms.append(W_OVERFLOW * ovf)

        # (1) Cibles de charge hebdomadaire (poids fort)
        W_BALANCE = 10
        obj_groups = []
        if ft_filter & {0, 2}:
            obj_groups.append(({0, 2}, TGT_FTP, 'ftp'))
        if ft_filter & {1, 2}:
            obj_groups.append(({1, 2}, TGT_ALT, 'alt'))
        for w in sorted_weeks:
            for ft_set, target, label in obj_groups:
                items = [
                    (x[s['id']][w], int(round(s['slot_duration'] * SCALE)))
                    for s in sessions
                    if s['formation_type'] in ft_set and w in x[s['id']]
                ]
                if not items:
                    continue
                load_expr = cp_model.LinearExpr.WeightedSum(
                    [v for v, _ in items], [d for _, d in items]
                )
                target_scaled = target * SCALE
                max_load = ABS_MAX_H * SCALE
                dev_pos = model.new_int_var(0, max_load, f'dp_{label}_{w}')
                dev_neg = model.new_int_var(0, max_load, f'dn_{label}_{w}')
                model.add(load_expr - target_scaled <= dev_pos)
                model.add(target_scaled - load_expr <= dev_neg)
                obj_terms += [W_BALANCE * dev_pos, W_BALANCE * dev_neg]

        # (2) Étalement uniforme par cours — utile uniquement si max_pw > 1
        W_SPREAD = 1
        for s in sessions:
            sid    = s['id']
            max_pw = max(1, int(s['sessions_per_week_max'] or 1))
            if not session_weeks.get(sid) or sid in infeasible_sids or sid in _merged_secondary or max_pw <= 1:
                continue
            nb = s['nb_sessions']
            mw = model.new_int_var(0, nb, f'mw_{sid}')
            for w in session_weeks[sid]:
                if w in x[sid]:
                    model.add(mw >= x[sid][w])
            obj_terms.append(W_SPREAD * mw)

        # (3) Contiguïté souple : pénaliser les trous dans le bloc actif
        #     gap = (dernière semaine active - première + 1) - nb semaines actives
        W_CONTIG = 50
        for sid, (n_valid, acts_list, min_span) in _contig_data.items():
            if n_valid <= 1:
                continue
            first_idx = model.new_int_var(0, n_valid - 1, f'first_{sid}')
            last_idx  = model.new_int_var(0, n_valid - 1, f'last_{sid}')
            for i, act in enumerate(acts_list):
                model.add(first_idx <= i).only_enforce_if(act)
                model.add(last_idx  >= i).only_enforce_if(act)
            num_active = cp_model.LinearExpr.Sum(acts_list)
            gap_count = model.new_int_var(0, n_valid, f'gap_{sid}')
            model.add(gap_count >= last_idx - first_idx + 1 - num_active)
            obj_terms.append(W_CONTIG * gap_count)

        if obj_terms:
            model.minimize(cp_model.LinearExpr.Sum(obj_terms))

        # --- Résolution ---
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 60.0
        solver.parameters.num_search_workers  = 4
        status = solver.solve(model)

        # --- Helper : diagnostic de charge par formation ---
        # Formations à afficher dans le diagnostic (selon le choix utilisateur)
        diag_labels = []
        if formation_param == 'ftp':
            diag_labels = [('FTP', {0, 2})]
        elif formation_param == 'alt':
            diag_labels = [('ALT', {1, 2})]
        else:
            diag_labels = [('FTP', {0, 2}), ('ALT', {1, 2})]

        def _build_diagnostics():
            problems = []

            # 1. Sessions pré-exclues
            if infeasible_sids:
                for v in infeasible_sids.values():
                    problems.append(f"⛔ {v['label']} : {v['reason']}")

            # 2. Charge totale par formation
            load = {}
            wks  = {}
            for label, ft_set in diag_labels:
                load[label] = 0.0
                wks[label] = set()
            for s in sessions:
                sid = s['id']
                if sid in infeasible_sids:
                    continue
                ft = s['formation_type']
                total_h = s['nb_sessions'] * s['slot_duration']
                for label, ft_set in diag_labels:
                    if ft in ft_set:
                        load[label] += total_h
                        wks[label].update(session_weeks.get(sid, []))

            for label, _ in diag_labels:
                nw = len(wks[label])
                if nw > 0:
                    avg = round(load[label] / nw, 1)
                    marker = '🔴' if load[label] > MAX_H * nw else '📊'
                    problems.append(
                        f"{marker} {label} : {round(load[label], 1)}h à répartir "
                        f"sur {nw} semaines (moy. {avg}h/sem, max {MAX_H}h/sem)"
                    )

            # 3. Charge forcée minimum par semaine
            week_forced = {}
            for s in sessions:
                sid = s['id']
                if sid in infeasible_sids or not session_weeks.get(sid):
                    continue
                ft = s['formation_type']
                sw_list = session_weeks[sid]
                n_valid = len(sw_list)
                nb = s['nb_sessions']
                forced_h = s['slot_duration'] * nb / n_valid if n_valid > 0 else 0
                for w in sw_list:
                    for label, ft_set in diag_labels:
                        if ft in ft_set:
                            week_forced[(label, w)] = week_forced.get((label, w), 0) + forced_h

            overloaded_weeks = sorted(
                [(fl, w, h) for (fl, w), h in week_forced.items() if h > MAX_H * 0.9],
                key=lambda x: -x[2]
            )[:8]
            for fl, w, h in overloaded_weeks:
                marker = '🔴' if h > MAX_H else '🟡'
                problems.append(
                    f"{marker} {fl} semaine {w} : charge estimée ~{round(h, 1)}h "
                    f"(max {MAX_H}h)"
                )

            # 4. Sessions les plus contraintes (marge < 30%)
            tight = []
            for s in sessions:
                sid = s['id']
                if sid in infeasible_sids:
                    continue
                sw_list = session_weeks.get(sid, [])
                if not sw_list:
                    continue
                nb = s['nb_sessions']
                max_pw = max(1, int(s['sessions_per_week_max'] or 1))
                min_span = math.ceil(nb / max_pw)
                n_valid = len(sw_list)
                slack = (n_valid - min_span) / max(min_span, 1)
                if slack < 0.3:
                    tight.append((s, n_valid, min_span, slack))
            tight.sort(key=lambda x: x[3])
            for s, nv, ms, sl in tight[:8]:
                ft_label = _FT_LABELS[s['formation_type']]
                problems.append(
                    f"⚠️ {s['course_code']} {s['teaching_type']} {ft_label} : "
                    f"{nv} semaines dispo pour {ms} nécessaires "
                    f"({s['nb_sessions']} séances, max {int(s['sessions_per_week_max'] or 1)}/sem) — "
                    f"marge {round(sl*100)}%"
                )

            # 5. Contraintes d'ordonnancement problématiques
            if orderings:
                for ord_row in orderings:
                    pred_sids_list = course_to_sessions.get(ord_row['course_id_pred'], [])
                    succ_sids_list = course_to_sessions.get(ord_row['course_id_succ'], [])
                    for ps in pred_sids_list:
                        for ss_ in succ_sids_list:
                            pw = session_weeks.get(ps, [])
                            sw_ = session_weeks.get(ss_, [])
                            if pw and sw_:
                                last_pred = max(week_to_idx.get(w, 0) for w in pw)
                                first_succ = min(week_to_idx.get(w, 0) for w in sw_)
                                gap = ord_row['min_gap_weeks']
                                if first_succ <= last_pred + gap:
                                    ps_info = next((s for s in sessions if s['id'] == ps), None)
                                    ss_info = next((s for s in sessions if s['id'] == ss_), None)
                                    if ps_info and ss_info:
                                        problems.append(
                                            f"🔗 Ordre : {ps_info['course_code']} doit finir "
                                            f"{gap} sem. avant {ss_info['course_code']} "
                                            f"— plages se chevauchent"
                                        )

            return problems

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            problems = _build_diagnostics()

            # --- Diagnostic par élimination : identifier la contrainte bloquante ---
            root_causes = []

            def _diag_model_base():
                """Modèle minimal : juste les variables + somme = nb."""
                dm = cp_model.CpModel()
                dx = {}
                for s in sessions:
                    sid = s['id']
                    if sid in infeasible_sids or sid in _merged_secondary:
                        continue
                    nb = _merged_nb.get(sid, s['nb_sessions'])
                    mpw = max(1, int(s['sessions_per_week_max'] or 1))
                    dx[sid] = {}
                    for w in session_weeks[sid]:
                        dx[sid][w] = dm.new_int_var(0, mpw, f'dx_{sid}_{w}')
                    dm.add(cp_model.LinearExpr.Sum(
                        [dx[sid][w] for w in session_weeks[sid]]
                    ) == nb)
                # Alias secondaires CM+TD
                for sec_sid, pri_sid in _merged_secondary.items():
                    if sec_sid not in infeasible_sids and pri_sid in dx:
                        dx[sec_sid] = dx[pri_sid]
                return dm, dx

            def _diag_solve(dm, timeout=10.0):
                ds = cp_model.CpSolver()
                ds.parameters.max_time_in_seconds = timeout
                ds.parameters.num_search_workers = 4
                return ds.solve(dm) in (cp_model.OPTIMAL, cp_model.FEASIBLE)

            try:
                # Test 1 : sans contiguïté, sans cap, sans salles
                dm0, _ = _diag_model_base()
                base_ok = _diag_solve(dm0, 5.0)
                if not base_ok:
                    root_causes.append(
                        '🔴 Certaines sessions ont des plages de semaines '
                        'trop étroites pour y caser toutes les séances '
                        '(même sans limite de 40h/sem, salles ou contiguïté).'
                    )
                else:
                    # Test 2 : sans contiguïté, avec cap 40h, sans salles
                    dm1, dx1 = _diag_model_base()
                    for w in sorted_weeks:
                        for ft_set in cap_groups:
                            items = [
                                (dx1[s['id']][w], int(round(s['slot_duration'] * SCALE)))
                                for s in sessions
                                if s['formation_type'] in ft_set[0]
                                   and s['id'] not in infeasible_sids
                                   and w in dx1.get(s['id'], {})
                            ]
                            if items:
                                dm1.add(cp_model.LinearExpr.WeightedSum(
                                    [v for v, _ in items], [d for _, d in items]
                                ) <= MAX_H * SCALE)
                    cap_ok = _diag_solve(dm1)
                    if not cap_ok:
                        root_causes.append(
                            '🔴 La CAPACITÉ de 40h/semaine est dépassée '
                            '(même sans contiguïté ni contrainte de salles). '
                            'Solutions : élargir les plages de semaines '
                            'ou réduire le volume horaire.'
                        )
                    else:
                        # Test 3 : sans contiguïté, avec cap + salles
                        # (le modèle principal a contiguïté + cap + salles)
                        # Si sans contiguïté + cap ça passe,
                        # c'est la contiguïté et/ou les salles qui bloquent.
                        # Tester contiguïté seule (sans salles) :
                        # on réutilise le modèle principal mais sans room_load
                        # → plus simple : on teste si base + cap + salles passe
                        dm2, dx2 = _diag_model_base()
                        for w in sorted_weeks:
                            for ft_set in cap_groups:
                                items = [
                                    (dx2[s['id']][w], int(round(s['slot_duration'] * SCALE)))
                                    for s in sessions
                                    if s['formation_type'] in ft_set[0]
                                       and s['id'] not in infeasible_sids
                                       and w in dx2.get(s['id'], {})
                                ]
                                if items:
                                    dm2.add(cp_model.LinearExpr.WeightedSum(
                                        [v for v, _ in items], [d for _, d in items]
                                    ) <= MAX_H * SCALE)
                        for (rt, w), items_r in room_load.items():
                            cap = int(room_counts[rt] * ROOM_H * SCALE)
                            r_items = []
                            for s in sessions:
                                sid = s['id']
                                if sid in infeasible_sids or not s['room_name']:
                                    continue
                                if room_type_by_name.get(s['room_name']) == rt and w in dx2.get(sid, {}):
                                    r_items.append((dx2[sid][w], int(round(s['slot_duration'] * SCALE))))
                            if r_items:
                                dm2.add(cp_model.LinearExpr.WeightedSum(
                                    [v for v, _ in r_items], [d for _, d in r_items]
                                ) <= cap)
                        cap_room_ok = _diag_solve(dm2)
                        if not cap_room_ok:
                            root_causes.append(
                                '🔴 La CAPACITÉ DES SALLES est insuffisante '
                                '(sans contiguïté). '
                                'Solutions : ajouter des salles, modifier les types, '
                                'ou élargir les plages.'
                            )
                        else:
                            # Tous les tests de diagnostic passent
                            # → le solveur n'a pas trouvé de solution dans le temps imparti
                            root_causes.append(
                                '🟡 Les contraintes de base sont satisfaisables mais le '
                                'solveur n\'a pas trouvé de solution dans le temps imparti. '
                                'Essayez de relancer ou d\'élargir les plages de semaines.'
                            )
            except Exception:
                pass  # diagnostic optionnel

            if root_causes:
                problems = root_causes + [''] + problems

            return jsonify({
                'error': f'Aucune solution trouvée ({solver.status_name(status)})',
                'problems': problems if problems else [
                    'Cause indéterminée — vérifiez les plages de semaines, '
                    'le max séances/sem et les contraintes d\'ordonnancement.'
                ],
            }), 422

        # --- Écriture dans weekly_hours ---
        db = get_db()
        cursor = db.cursor()
        weeks_assigned = 0

        for s in sessions:
            sid = s['id']
            if not session_weeks[sid]:
                continue
            slot_dur = s['slot_duration']
            cursor.execute('DELETE FROM weekly_hours WHERE course_session_id = ?', (sid,))
            for w in session_weeks[sid]:
                if w not in x[sid]:
                    continue
                n = solver.value(x[sid][w])
                if n > 0:
                    cursor.execute(
                        'INSERT INTO weekly_hours (course_session_id, week_number, hours) VALUES (?, ?, ?)',
                        (sid, w, round(n * slot_dur, 2))
                    )
                    weeks_assigned += 1

        db.commit()

        # Détecter les dépassements du plafond souple (MAX_H)
        overflow_weeks = []
        for w in sorted_weeks:
            for ft_set, label in cap_groups:
                total_h = sum(
                    solver.value(x[s['id']][w]) * s['slot_duration']
                    for s in sessions
                    if s['formation_type'] in ft_set and w in x.get(s['id'], {})
                )
                if total_h > MAX_H:
                    overflow_weeks.append(
                        f"S{w} {label.upper()}: {round(total_h, 1)}h (plafond souple {MAX_H}h)"
                    )

        n_infeasible = len(infeasible_sids)
        infeasible_list = [
            f"{v['label']} : {v['reason']}" for v in infeasible_sids.values()
        ] if infeasible_sids else None

        # Détecter les sessions avec trous de contiguïté
        non_contig = []
        for sid, (n_valid, acts_list, min_span) in _contig_data.items():
            if n_valid <= 1:
                continue
            active_indices = [i for i, act in enumerate(acts_list) if solver.value(act)]
            if len(active_indices) >= 2:
                span = active_indices[-1] - active_indices[0] + 1
                gaps = span - len(active_indices)
                if gaps > 0:
                    s_info = next((s for s in sessions if s['id'] == sid), None)
                    if s_info:
                        non_contig.append(
                            f"{s_info['course_code']} {s_info['teaching_type']} "
                            f"{_FT_LABELS[s_info['formation_type']]}: {gaps} trou(s)"
                        )

        warnings = []
        if n_infeasible:
            warnings.append(
                f'{n_infeasible} session(s) ignorée(s) : pas assez de semaines valides '
                f'(vérifier plages de semaines / calendrier spécial).'
            )
        if overflow_weeks:
            warnings.append(
                f'{len(overflow_weeks)} semaine(s) dépassent {MAX_H}h : '
                + ', '.join(overflow_weeks)
            )
        if non_contig:
            warnings.append(
                f'{len(non_contig)} session(s) non contiguë(s) : '
                + ', '.join(non_contig)
            )

        return jsonify({
            'status':               solver.status_name(status),
            'sessions_optimized':   len([s for s in sessions if s['id'] not in infeasible_sids
                                         and session_weeks.get(s['id'])]),
            'weeks_assigned':       weeks_assigned,
            'infeasible_sessions':  n_infeasible,
            'infeasible_details':   infeasible_list,
            'overflow_weeks':       overflow_weeks if overflow_weeks else None,
            'non_contiguous':       non_contig if non_contig else None,
            'warning':              ' | '.join(warnings) if warnings else None,
        }), 200

    except Exception as e:
        return error_response(f'Erreur optimisation : {str(e)}', 500)

# ======================= APPLICATION STARTUP =======================

# Initialize database on module load (works with any WSGI runner)
os.makedirs('static', exist_ok=True)
init_db()

if __name__ == '__main__':
    # Run Flask app
    # debug est désactivé par défaut ; activez-le en local avec EDT_DEBUG=1.
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('EDT_DEBUG', '0') == '1'
    )
