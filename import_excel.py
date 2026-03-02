#!/usr/bin/env python3
"""Import Excel data into SQLite for IUT GIM EDT management."""

import sqlite3
import pandas as pd
import sys
import os
import tempfile
import shutil

EXCEL_FILE = "/sessions/optimistic-zen-bardeen/mnt/uploads/placement cours semaine BUT 25-26 V3.xlsx"
DB_FILE = "/sessions/optimistic-zen-bardeen/edt.db"
SCHEMA_FILE = "/sessions/optimistic-zen-bardeen/mnt/GestionEDT/schema.sql"

SEMESTER_MAPPING = {
    "S1+S2": [("S1", 1), ("S2", 1)],
    "S3+S4": [("S3", 2), ("S4", 2)],
    "S5+S6": [("S5", 3), ("S6", 3)],
}

def norm(name):
    if pd.isna(name) or name is None:
        return None
    s = str(name).strip().replace('\n', '').replace('\r', '').upper()
    return s if s and s != '?' and s != 'NAN' else None

def main():
    print("=" * 60)
    print("IUT GIM EDT - Import Excel")
    print("=" * 60)

    # Remove old DB
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    with open(SCHEMA_FILE, 'r') as f:
        conn.executescript(f.read())
    conn.commit()

    sheets = {}
    for s in ["S1+S2", "S3+S4", "S5+S6", "Contact Vacataire"]:
        sheets[s] = pd.read_excel(EXCEL_FILE, sheet_name=s, header=None)
        print(f"  Loaded '{s}' ({sheets[s].shape})")

    # === TEACHERS ===
    # First collect all teacher names from course sheets (by last name only)
    teacher_names = set()
    for sn in ["S1+S2", "S3+S4", "S5+S6"]:
        df = sheets[sn]
        for idx in range(5, len(df)):
            t = norm(df.iloc[idx, 2])
            if t and t not in ('ENTREPRISE', 'MATHIEU'):
                # Clean up names like "KAROSKI (GEII)" -> keep as-is
                teacher_names.add(t)

    # Import from Contact Vacataire (with email/phone)
    contact_map = {}  # last_name_upper -> full record
    df_contact = sheets["Contact Vacataire"]
    for idx in range(2, len(df_contact)):
        row = df_contact.iloc[idx]
        last_name = row.iloc[2] if pd.notna(row.iloc[2]) else None
        if not last_name:
            continue
        last_upper = str(last_name).strip().upper()
        first_name = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else ""
        contact_map[last_upper] = {
            'structure': str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else None,
            'first_name': first_name,
            'email': str(row.iloc[6]).strip() if pd.notna(row.iloc[6]) else None,
            'phone': str(row.iloc[7]).strip() if pd.notna(row.iloc[7]) else None,
            'corps': str(row.iloc[5]).strip() if pd.notna(row.iloc[5]) else None,
        }

    # Merge: all teacher_names + contact info where available
    teacher_ids = {}
    for name in sorted(teacher_names):
        # Try to match with contact sheet (by last name)
        base_name = name.split('(')[0].strip()  # KAROSKI (GEII) -> KAROSKI
        contact = contact_map.get(base_name, contact_map.get(name, {}))
        cur.execute(
            "INSERT OR IGNORE INTO teachers (name, email, phone, structure, corps_code) VALUES (?,?,?,?,?)",
            (name, contact.get('email'), contact.get('phone'),
             contact.get('structure'), contact.get('corps'))
        )
        teacher_ids[name] = cur.lastrowid if cur.lastrowid else cur.execute(
            "SELECT id FROM teachers WHERE name=?", (name,)).fetchone()[0]

    # Also add teachers from contact sheet not in course data
    for last_upper, info in contact_map.items():
        if last_upper not in teacher_ids:
            display = f"{last_upper} {info['first_name']}".strip() if info['first_name'] else last_upper
            cur.execute(
                "INSERT OR IGNORE INTO teachers (name, email, phone, structure, corps_code) VALUES (?,?,?,?,?)",
                (last_upper, info.get('email'), info.get('phone'),
                 info.get('structure'), info.get('corps'))
            )
            if cur.lastrowid:
                teacher_ids[last_upper] = cur.lastrowid

    conn.commit()
    print(f"\n  Teachers: {len(teacher_ids)}")

    # === SEMESTERS ===
    sem_ids = {}
    for code, yg in [("S1",1),("S2",1),("S3",2),("S4",2),("S5",3),("S6",3)]:
        cur.execute("INSERT INTO semesters (code, year_group, name) VALUES (?,?,?)",
                    (code, yg, f"Semestre {code[1]}"))
        sem_ids[code] = cur.lastrowid
    conn.commit()
    print(f"  Semesters: {len(sem_ids)}")

    # === ROOMS ===
    room_ids = {}
    def get_room(name):
        n = str(name).strip() if pd.notna(name) else 'STD'
        if n in room_ids:
            return room_ids[n]
        rtype = 'standard'
        if n in ('123', '124'):
            rtype = 'info_fixe'
        elif n == 'INFO_MOBILE':
            rtype = 'info_mobile'
        cur.execute("INSERT OR IGNORE INTO rooms (name, room_type) VALUES (?,?)", (n, rtype))
        rid = cur.lastrowid or cur.execute("SELECT id FROM rooms WHERE name=?", (n,)).fetchone()[0]
        room_ids[n] = rid
        return rid

    # Pre-create known rooms
    for rn in ['STD', '123', '124', '126', '127', '129', '228', '19']:
        get_room(rn)
    conn.commit()
    print(f"  Rooms: {len(room_ids)}")

    # === COURSES & SESSIONS & WEEKLY HOURS ===
    total_courses = 0
    total_sessions = 0
    total_weekly = 0

    for sheet_name in ["S1+S2", "S3+S4", "S5+S6"]:
        df = sheets[sheet_name]
        semesters = SEMESTER_MAPPING[sheet_name]

        # Get week mapping from rows 1-2
        week_map = []  # list of (col_index, but_week, cal_week)
        for col in range(10, df.shape[1]):
            but_w = df.iloc[1, col]
            cal_w = df.iloc[2, col]
            if pd.notna(but_w) and pd.notna(cal_w):
                try:
                    week_map.append((col, int(float(but_w)), int(float(cal_w))))
                except (ValueError, TypeError):
                    pass

        # Find semester separator row
        sep_idx = None
        for idx in range(5, len(df)):
            val = df.iloc[idx, 0]
            if pd.notna(val) and 'Semestre' in str(val) and str(val).strip() != semesters[0][0]:
                sep_idx = idx
                break

        # Process each semester in this sheet
        for sem_i, (sem_code, sem_yg) in enumerate(semesters):
            if sem_i == 0:
                row_start, row_end = 5, sep_idx if sep_idx else len(df)
            else:
                if not sep_idx:
                    continue
                row_start, row_end = sep_idx + 1, len(df)

            current_course_id = None
            current_course_code = None
            current_teacher = None

            for idx in range(row_start, row_end):
                row = df.iloc[idx]

                # New course?
                code = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else None
                if code and (code.startswith('R') or code.startswith('SAE')):
                    cname = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else code
                    ctype = 'SAE' if code.startswith('SAE') else 'RESSOURCE'
                    cur.execute(
                        "INSERT INTO courses (code, name, semester_id, course_type) VALUES (?,?,?,?)",
                        (code, cname, sem_ids[sem_code], ctype))
                    current_course_id = cur.lastrowid
                    current_course_code = code
                    total_courses += 1

                # New teacher within course?
                t = norm(row.iloc[2])
                if t:
                    current_teacher = t

                # Session line (has nb_sessions in col 3)
                if current_course_id and pd.notna(row.iloc[3]):
                    try:
                        nb = int(float(row.iloc[3]))
                    except (ValueError, TypeError):
                        continue

                    formation = int(float(row.iloc[4])) if pd.notna(row.iloc[4]) else 0
                    ttype = str(row.iloc[5]).strip() if pd.notna(row.iloc[5]) else 'CM'
                    total_h = float(row.iloc[6]) if pd.notna(row.iloc[6]) else 0
                    room_name = str(row.iloc[8]).strip() if pd.notna(row.iloc[8]) else 'STD'
                    promo = str(row.iloc[9]).strip() if pd.notna(row.iloc[9]) else None
                    if promo and promo.lower() == 'nan':
                        promo = None

                    # Determine slot duration from teaching type
                    if 'CM' in ttype:
                        dur = 1.5
                    elif 'TD' in ttype:
                        dur = 1.5
                    elif 'TP' in ttype:
                        dur = 2.0 if nb > 0 else 1.5
                    elif 'PT' in ttype:
                        dur = 2.0
                    else:
                        dur = 1.5

                    tid = teacher_ids.get(current_teacher)
                    get_room(room_name)

                    cur.execute("""INSERT INTO course_sessions
                        (course_id, teacher_id, formation_type, teaching_type,
                         nb_sessions, total_hours, slot_duration, room_name, promo)
                        VALUES (?,?,?,?,?,?,?,?,?)""",
                        (current_course_id, tid, formation, ttype, nb, total_h, dur, room_name, promo))
                    session_id = cur.lastrowid
                    total_sessions += 1

                    # Weekly hours
                    for col_i, but_w, cal_w in week_map:
                        if col_i < df.shape[1]:
                            h = row.iloc[col_i]
                            if pd.notna(h):
                                try:
                                    hval = float(h)
                                    if hval > 0:
                                        cur.execute(
                                            "INSERT OR IGNORE INTO weekly_hours (course_session_id, week_number, semester_week, hours) VALUES (?,?,?,?)",
                                            (session_id, cal_w, but_w, hval))
                                        total_weekly += 1
                                except (ValueError, TypeError):
                                    pass

        conn.commit()
        print(f"  {sheet_name}: {total_courses} courses, {total_sessions} sessions")

    # === SET start_week / end_week ON COURSES ===
    # Derive from the min/max calendar weeks of actual weekly_hours for each course
    cur.execute("""
        UPDATE courses SET
            start_week = (
                SELECT MIN(wh.week_number)
                FROM weekly_hours wh
                JOIN course_sessions cs ON wh.course_session_id = cs.id
                WHERE cs.course_id = courses.id
            ),
            end_week = (
                SELECT MAX(wh.week_number)
                FROM weekly_hours wh
                JOIN course_sessions cs ON wh.course_session_id = cs.id
                WHERE cs.course_id = courses.id
            )
    """)
    conn.commit()
    print(f"  Course start/end weeks updated")

    # === CALENDAR EVENTS ===
    # Extract from row 0 of S1+S2
    df = sheets["S1+S2"]
    events = [
        (36, 'semester_start', 'Rentrée S1 - lundi 01/09'),
        (42, 'vacation', 'Vacances Toussaint début'),
        (44, 'vacation', 'Vacances Toussaint fin'),
        (52, 'vacation', 'Vacances Noël début'),
        (1, 'vacation', 'Vacances Noël fin'),
    ]
    for wk, etype, desc in events:
        cur.execute("INSERT INTO calendar_events (week_number, event_type, description) VALUES (?,?,?)",
                    (wk, etype, desc))
    conn.commit()

    # === SUMMARY ===
    counts = {}
    for table in ['teachers', 'semesters', 'courses', 'course_sessions', 'rooms', 'weekly_hours', 'calendar_events']:
        counts[table] = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    print("\n" + "=" * 60)
    print("IMPORT COMPLETE")
    print("=" * 60)
    for t, c in counts.items():
        print(f"  {t:20s}: {c}")
    print(f"\n  Database: {DB_FILE}")
    print("=" * 60)

    conn.close()

if __name__ == "__main__":
    main()
