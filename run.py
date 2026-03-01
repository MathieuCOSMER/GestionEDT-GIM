#!/usr/bin/env python3
"""Launch script for IUT GIM EDT Management System."""

import os
import sys
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'edt.db')
SCHEMA_PATH = os.path.join(BASE_DIR, 'schema.sql')

def check_dependencies():
    try:
        import flask
        import flask_cors
        print("  Flask OK")
    except ImportError:
        print("  Installing Flask...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install',
                               'flask', 'flask-cors', '--break-system-packages', '-q'])

def init_db():
    import sqlite3
    if not os.path.exists(DB_PATH):
        print(f"  Creating database at {DB_PATH}...")
        conn = sqlite3.connect(DB_PATH)
        with open(SCHEMA_PATH, 'r') as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()
        print("  Database created. Run import_excel.py to load data.")
    else:
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM teachers").fetchone()[0]
        conn.close()
        print(f"  Database OK ({count} teachers)")

def main():
    print("=" * 50)
    print("  IUT GIM Toulon - Gestion EDT")
    print("=" * 50)

    print("\n[1] Checking dependencies...")
    check_dependencies()

    print("[2] Checking database...")
    init_db()

    print("[3] Starting server...")
    print(f"    http://localhost:5000")
    print("    Press Ctrl+C to stop\n")

    # Set DB path in env for app.py
    os.environ['EDT_DB_PATH'] = DB_PATH

    sys.path.insert(0, BASE_DIR)
    from app import app
    app.run(host='0.0.0.0', port=5000, debug=True)

if __name__ == '__main__':
    main()
