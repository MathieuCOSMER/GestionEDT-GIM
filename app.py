"""
Flask backend application for IUT Gestion Emploi Du Temps (EDT)
Manages timetables for IUT GIM Toulon
"""

from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import sqlite3
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
import io

# Initialize Flask app
app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# Database configuration
DATABASE = '/sessions/optimistic-zen-bardeen/edt.db'
SCHEMA_PATH = '/sessions/optimistic-zen-bardeen/mnt/GestionEDT/schema.sql'

# Helper function to get database connection
def get_db():
    """Get database connection"""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

# Helper function to initialize database
def init_db():
    """Initialize database from schema"""
    if not os.path.exists(DATABASE):
        db = get_db()
        with open(SCHEMA_PATH, 'r') as f:
            db.executescript(f.read())
        db.commit()
        db.close()

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

# ======================= STATIC FILES =======================

@app.route('/')
def serve_root():
    """Serve index.html at root"""
    if os.path.exists('static/index.html'):
        return send_file('static/index.html')
    return jsonify({'message': 'Welcome to IUT EDT Management System'}), 200

@app.route('/<path:path>')
def serve_static(path):
    """Serve static files"""
    return send_from_directory('static', path)

# ======================= TEACHERS CRUD =======================

@app.route('/api/teachers', methods=['GET'])
def get_teachers():
    """Get all teachers"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM teachers ORDER BY name')
        teachers = rows_to_list(cursor.fetchall())
        db.close()
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
            INSERT INTO teachers (name, email, phone, structure, corps_code, max_hours_day, priority)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['name'],
            data.get('email'),
            data.get('phone'),
            data.get('structure'),
            data.get('corps_code'),
            data.get('max_hours_day', 6),
            data.get('priority', 1)
        ))
        db.commit()
        teacher_id = cursor.lastrowid
        cursor.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,))
        teacher = row_to_dict(cursor.fetchone())
        db.close()
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
        db.close()
        
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
            db.close()
            return error_response('Teacher not found', 404)
        
        # Update fields
        update_fields = []
        values = []
        for field in ['name', 'email', 'phone', 'structure', 'corps_code', 'max_hours_day', 'priority']:
            if field in data:
                update_fields.append(f'{field} = ?')
                values.append(data[field])
        
        if not update_fields:
            db.close()
            return error_response('No fields to update')
        
        values.append(teacher_id)
        query = f'UPDATE teachers SET {", ".join(update_fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?'
        cursor.execute(query, values)
        db.commit()
        
        cursor.execute('SELECT * FROM teachers WHERE id = ?', (teacher_id,))
        teacher = row_to_dict(cursor.fetchone())
        db.close()
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
            db.close()
            return error_response('Teacher not found', 404)
        
        cursor.execute('DELETE FROM teachers WHERE id = ?', (teacher_id,))
        db.commit()
        db.close()
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
            db.close()
            return error_response('Teacher not found', 404)
        
        cursor.execute('SELECT * FROM teacher_availability WHERE teacher_id = ? ORDER BY day_of_week, start_time', (teacher_id,))
        availability = rows_to_list(cursor.fetchall())
        db.close()
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
            db.close()
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
        db.close()
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
        db.close()
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
        db.close()
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
        db.close()
        
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
            db.close()
            return error_response('Room not found', 404)
        
        # Update fields
        update_fields = []
        values = []
        for field in ['name', 'capacity', 'room_type', 'location']:
            if field in data:
                update_fields.append(f'{field} = ?')
                values.append(data[field])
        
        if not update_fields:
            db.close()
            return error_response('No fields to update')
        
        values.append(room_id)
        query = f'UPDATE rooms SET {", ".join(update_fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?'
        cursor.execute(query, values)
        db.commit()
        
        cursor.execute('SELECT * FROM rooms WHERE id = ?', (room_id,))
        room = row_to_dict(cursor.fetchone())
        db.close()
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
            db.close()
            return error_response('Room not found', 404)
        
        cursor.execute('DELETE FROM rooms WHERE id = ?', (room_id,))
        db.commit()
        db.close()
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
        db.close()
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
            INSERT INTO semesters (code, year_group, name)
            VALUES (?, ?, ?)
        ''', (
            data['code'],
            data['year_group'],
            data.get('name')
        ))
        db.commit()
        semester_id = cursor.lastrowid
        cursor.execute('SELECT * FROM semesters WHERE id = ?', (semester_id,))
        semester = row_to_dict(cursor.fetchone())
        db.close()
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
        db.close()
        
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
            db.close()
            return error_response('Semester not found', 404)
        
        # Update fields
        update_fields = []
        values = []
        for field in ['code', 'year_group', 'name']:
            if field in data:
                update_fields.append(f'{field} = ?')
                values.append(data[field])
        
        if not update_fields:
            db.close()
            return error_response('No fields to update')
        
        values.append(semester_id)
        query = f'UPDATE semesters SET {", ".join(update_fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?'
        cursor.execute(query, values)
        db.commit()
        
        cursor.execute('SELECT * FROM semesters WHERE id = ?', (semester_id,))
        semester = row_to_dict(cursor.fetchone())
        db.close()
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
            db.close()
            return error_response('Semester not found', 404)
        
        cursor.execute('DELETE FROM semesters WHERE id = ?', (semester_id,))
        db.commit()
        db.close()
        return jsonify({'message': 'Semester deleted'}), 200
    except Exception as e:
        return error_response(f'Error deleting semester: {str(e)}', 500)

# ======================= COURSES CRUD =======================

@app.route('/api/courses', methods=['GET'])
def get_courses():
    """Get all courses"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            SELECT c.*, s.code as semester_code 
            FROM courses c 
            JOIN semesters s ON c.semester_id = s.id 
            ORDER BY c.code
        ''')
        courses = rows_to_list(cursor.fetchall())
        db.close()
        return jsonify(courses), 200
    except Exception as e:
        return error_response(f'Error fetching courses: {str(e)}', 500)

@app.route('/api/courses', methods=['POST'])
def create_course():
    """Create a new course"""
    try:
        data = request.get_json()
        if not data or not data.get('code') or not data.get('name') or not data.get('semester_id') or not data.get('course_type'):
            return error_response('Course code, name, semester_id, and course_type are required')
        
        db = get_db()
        cursor = db.cursor()
        
        # Check if semester exists
        cursor.execute('SELECT * FROM semesters WHERE id = ?', (data['semester_id'],))
        if not cursor.fetchone():
            db.close()
            return error_response('Semester not found', 404)
        
        cursor.execute('''
            INSERT INTO courses (code, name, semester_id, course_type, start_week, end_week)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            data['code'],
            data['name'],
            data['semester_id'],
            data['course_type'],
            data.get('start_week'),
            data.get('end_week')
        ))
        db.commit()
        course_id = cursor.lastrowid
        cursor.execute('''
            SELECT c.*, s.code as semester_code 
            FROM courses c 
            JOIN semesters s ON c.semester_id = s.id 
            WHERE c.id = ?
        ''', (course_id,))
        course = row_to_dict(cursor.fetchone())
        db.close()
        return jsonify(course), 201
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
        db.close()
        
        if not course:
            return error_response('Course not found', 404)
        
        return jsonify(row_to_dict(course)), 200
    except Exception as e:
        return error_response(f'Error fetching course: {str(e)}', 500)

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
            db.close()
            return error_response('Course not found', 404)
        
        # Update fields
        update_fields = []
        values = []
        for field in ['code', 'name', 'semester_id', 'course_type', 'start_week', 'end_week']:
            if field in data:
                update_fields.append(f'{field} = ?')
                values.append(data[field])
        
        if not update_fields:
            db.close()
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
        db.close()
        return jsonify(course), 200
    except Exception as e:
        return error_response(f'Error updating course: {str(e)}', 500)

@app.route('/api/courses/<int:course_id>', methods=['DELETE'])
def delete_course(course_id):
    """Delete a course"""
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Check if course exists
        cursor.execute('SELECT * FROM courses WHERE id = ?', (course_id,))
        if not cursor.fetchone():
            db.close()
            return error_response('Course not found', 404)
        
        cursor.execute('DELETE FROM courses WHERE id = ?', (course_id,))
        db.commit()
        db.close()
        return jsonify({'message': 'Course deleted'}), 200
    except Exception as e:
        return error_response(f'Error deleting course: {str(e)}', 500)

# ======================= COURSE SESSIONS CRUD =======================

@app.route('/api/course-sessions', methods=['GET'])
def get_course_sessions():
    """Get all course sessions"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            SELECT cs.*, c.code as course_code, c.name as course_name,
                   c.semester_id, s.code as semester_code,
                   t.name as teacher_name
            FROM course_sessions cs
            JOIN courses c ON cs.course_id = c.id
            JOIN semesters s ON c.semester_id = s.id
            LEFT JOIN teachers t ON cs.teacher_id = t.id
            ORDER BY s.code, c.code, cs.formation_type, cs.teaching_type
        ''')
        sessions = rows_to_list(cursor.fetchall())
        db.close()
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
            db.close()
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
        db.close()
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
        db.close()
        
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
            db.close()
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
            db.close()
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
        db.close()
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
            db.close()
            return error_response('Course session not found', 404)
        
        cursor.execute('DELETE FROM course_sessions WHERE id = ?', (session_id,))
        db.commit()
        db.close()
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
            db.close()
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
        db.close()
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
            db.close()
            return error_response('Course session not found', 404)
        
        cursor.execute('''
            SELECT * FROM weekly_hours 
            WHERE course_session_id = ? 
            ORDER BY week_number
        ''', (session_id,))
        hours = rows_to_list(cursor.fetchall())
        db.close()
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
            db.close()
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
        db.close()
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
        db.close()
        return jsonify({'updated': updated_count}), 200
    except Exception as e:
        return error_response(f'Error updating weekly hours: {str(e)}', 500)

# ======================= SERVICE CALCULATION =======================

def calculate_hetd(teaching_type, total_hours):
    """Calculate HETD based on teaching type"""
    coefficients = {
        'CM': 1.5,
        'TD': 1.0,
        'TP 12': 2/3,
        'TP 8': 2/3,
        'PT': 1.0
    }
    coefficient = coefficients.get(teaching_type, 1.0)
    return total_hours * coefficient

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
            db.close()
            return error_response('Teacher not found', 404)
        
        cursor.execute('''
            SELECT cs.id, c.code as course_code, cs.teaching_type, cs.total_hours
            FROM course_sessions cs
            JOIN courses c ON cs.course_id = c.id
            WHERE cs.teacher_id = ?
        ''', (teacher_id,))
        sessions = cursor.fetchall()
        db.close()
        
        service_details = []
        total_hetd = 0
        
        for session in sessions:
            hetd = calculate_hetd(session['teaching_type'], session['total_hours'])
            total_hetd += hetd
            service_details.append({
                'course_code': session['course_code'],
                'teaching_type': session['teaching_type'],
                'total_hours': session['total_hours'],
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
    """Get all teachers' service hours with breakdown by type"""
    try:
        db = get_db()
        cursor = db.cursor()

        cursor.execute('''
            SELECT t.id, t.name,
                   COALESCE(SUM(CASE WHEN cs.teaching_type = 'CM' THEN cs.total_hours ELSE 0 END), 0) as cm_hours,
                   COALESCE(SUM(CASE WHEN cs.teaching_type = 'TD' THEN cs.total_hours ELSE 0 END), 0) as td_hours,
                   COALESCE(SUM(CASE WHEN cs.teaching_type LIKE 'TP%' THEN cs.total_hours ELSE 0 END), 0) as tp_hours,
                   COALESCE(SUM(CASE WHEN cs.teaching_type = 'PT' THEN cs.total_hours ELSE 0 END), 0) as pt_hours
            FROM teachers t
            LEFT JOIN course_sessions cs ON cs.teacher_id = t.id
            GROUP BY t.id, t.name
            ORDER BY t.name
        ''')
        rows = cursor.fetchall()
        db.close()

        services = []
        for row in rows:
            cm_h = row['cm_hours']
            td_h = row['td_hours']
            tp_h = row['tp_hours']
            pt_h = row['pt_hours']
            hetd = cm_h * 1.5 + td_h * 1.0 + tp_h * (2.0/3.0) + pt_h * 1.0
            total_h = cm_h + td_h + tp_h + pt_h

            if total_h > 0:
                services.append({
                    'teacher_id': row['id'],
                    'teacher_name': row['name'],
                    'cm_hours': round(cm_h, 1),
                    'td_hours': round(td_h, 1),
                    'tp_hours': round(tp_h, 1),
                    'pt_hours': round(pt_h, 1),
                    'total_hours': round(total_h, 1),
                    'total_hetd': round(hetd, 2)
                })

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
            db.close()
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
                cursor.execute(
                    'SELECT hours FROM weekly_hours WHERE course_session_id = ? AND week_number = ?',
                    (sess['id'], week))
                row = cursor.fetchone()
                if row and row['hours'] > 0:
                    sess_copy = dict(sess)
                    sess_copy['week_hours'] = row['hours']
                    week_sessions.append(sess_copy)

            # Sort: CM first (harder to place), then TD, then TP, then PT
            type_order = {'CM': 0, 'TD': 1, 'TP 12': 2, 'TP 8': 2, 'TP12': 2, 'TP': 2, 'PT': 3}
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
        db.close()

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
        db.close()
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
        db.close()
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
            db.close()
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
        db.close()
        
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
        db.close()
        
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
        db.close()
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
        db.close()
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

# ======================= ERROR HANDLERS =======================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return error_response('Resource not found', 404)

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return error_response('Internal server error', 500)

# ======================= APPLICATION STARTUP =======================

if __name__ == '__main__':
    # Create static directory if it doesn't exist
    os.makedirs('static', exist_ok=True)
    
    # Initialize database
    init_db()
    
    # Run Flask app
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )
