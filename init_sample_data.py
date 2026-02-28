"""
Sample data initialization script for IUT EDT Management System
Run after app initialization to populate with test data
"""

import sqlite3
import json

DATABASE = '/sessions/optimistic-zen-bardeen/mnt/GestionEDT/edt.db'

def init_sample_data():
    """Initialize sample data"""
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    try:
        # Insert sample teachers
        teachers = [
            ('Dr. Jean Dupont', 'jean.dupont@iut.fr', '01.98.76.54.32', 'Computer Science', 'PR', 6, 1),
            ('Mme Marie Martin', 'marie.martin@iut.fr', '01.98.76.54.33', 'Mathematics', 'MCF', 6, 1),
            ('M. Pierre Bernard', 'pierre.bernard@iut.fr', '01.98.76.54.34', 'Electronics', 'ATER', 4, 2),
            ('Dr. Sophie Lefebvre', 'sophie.lefebvre@iut.fr', '01.98.76.54.35', 'Networks', 'PR', 6, 1),
            ('M. Marc Leclerc', 'marc.leclerc@iut.fr', '01.98.76.54.36', 'Management', 'MCF', 5, 2),
        ]
        
        for teacher in teachers:
            cursor.execute('''
                INSERT INTO teachers (name, email, phone, structure, corps_code, max_hours_day, priority)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', teacher)
        
        print("✓ Inserted 5 teachers")
        
        # Insert sample rooms
        rooms = [
            ('A101', 30, 'standard', 'Building A - Floor 1'),
            ('A102', 30, 'standard', 'Building A - Floor 1'),
            ('B201', 40, 'info_fixe', 'Building B - Computer Lab'),
            ('B202', 25, 'info_mobile', 'Building B - Mobile Lab'),
            ('C301', 100, 'standard', 'Building C - Amphitheater'),
            ('PT101', 20, 'tp', 'Building A - Project Room'),
        ]
        
        for room in rooms:
            cursor.execute('''
                INSERT INTO rooms (name, capacity, room_type, location)
                VALUES (?, ?, ?, ?)
            ''', room)
        
        print("✓ Inserted 6 rooms")
        
        # Insert semesters
        semesters = [
            ('S1', 1, 'Year 1 - Semester 1', 1, 15),
            ('S2', 1, 'Year 1 - Semester 2', 16, 30),
            ('S3', 2, 'Year 2 - Semester 3', 1, 15),
            ('S4', 2, 'Year 2 - Semester 4', 16, 30),
            ('S5', 3, 'Year 3 - Semester 5', 1, 15),
            ('S6', 3, 'Year 3 - Semester 6', 16, 30),
        ]
        
        for sem in semesters:
            cursor.execute('''
                INSERT INTO semesters (code, year_group, name, start_week, end_week)
                VALUES (?, ?, ?, ?, ?)
            ''', sem)
        
        print("✓ Inserted 6 semesters")
        
        # Insert courses
        courses = [
            ('R1.01', 'Introduction to Programming', 1, 'ressource'),
            ('R1.02', 'Mathematics 1', 1, 'ressource'),
            ('R1.03', 'Introduction to Electronics', 1, 'ressource'),
            ('SAE1.1', 'First Mini-Project', 1, 'sae'),
            ('R2.01', 'Advanced Programming', 2, 'ressource'),
            ('R2.02', 'Databases', 2, 'ressource'),
            ('SAE2.1', 'Team Project', 2, 'sae'),
        ]
        
        for course in courses:
            cursor.execute('''
                INSERT INTO courses (code, name, semester_id, course_type)
                VALUES (?, ?, ?, ?)
            ''', course)
        
        print("✓ Inserted 7 courses")
        
        # Insert course sessions
        sessions = [
            (1, 1, 0, 'CM', 10, 15, 1.5, 'C301', 'FTP'),
            (1, 1, 0, 'TD', 10, 10, 1.5, 'A101', 'FTP'),
            (1, 1, 0, 'TP 12', 10, 20, 2, 'B201', 'FTP'),
            (2, 2, 0, 'CM', 10, 15, 1.5, 'C301', 'FTP'),
            (2, 2, 0, 'TD', 10, 10, 1.5, 'A102', 'FTP'),
            (3, 3, 0, 'CM', 8, 12, 1.5, 'C301', 'FTP'),
            (3, 3, 0, 'TP 12', 8, 16, 2, 'B202', 'FTP'),
            (4, 1, 0, 'PT', 10, 20, 2, 'PT101', 'FTP'),
        ]
        
        for session in sessions:
            cursor.execute('''
                INSERT INTO course_sessions (course_id, teacher_id, formation_type, teaching_type,
                                            nb_sessions, total_hours, slot_duration, room_name, promo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', session)
        
        print("✓ Inserted 8 course sessions")
        
        # Insert teacher availability
        availabilities = [
            (1, 0, '08:00', '18:00', 1, 1),  # Monday all day
            (1, 1, '08:00', '12:00', 1, 1),  # Tuesday morning
            (1, 2, '14:00', '18:00', 1, 2),  # Wednesday afternoon (prefer)
            (2, 0, '08:00', '18:00', 1, 1),  # Monday all day
            (2, 3, '08:00', '12:00', 1, 1),  # Thursday morning
            (3, 1, '08:00', '18:00', 1, 1),  # Tuesday all day
            (4, 2, '08:00', '18:00', 1, 1),  # Wednesday all day
            (5, 4, '08:00', '12:00', 1, 2),  # Friday morning
        ]
        
        for avail in availabilities:
            cursor.execute('''
                INSERT INTO teacher_availability (teacher_id, day_of_week, start_time, end_time, available, priority)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', avail)
        
        print("✓ Inserted 8 availability slots")
        
        # Insert weekly hours
        for session_id in range(1, 9):
            for week in range(1, 16):
                cursor.execute('''
                    INSERT INTO weekly_hours (course_session_id, week_number, semester_week, hours)
                    VALUES (?, ?, ?, ?)
                ''', (session_id, week, week, 1.5))
        
        print("✓ Inserted 120 weekly hour entries")
        
        # Insert calendar events
        events = [
            (3, '2024-01-15', 'vacation', 'Winter Break'),
            (8, '2024-02-12', 'holiday', 'Presidents Day'),
            (21, '2024-04-08', 'vacation', 'Easter Break'),
            (30, '2024-06-01', 'semester_end', 'End of Semester'),
        ]
        
        for event in events:
            cursor.execute('''
                INSERT INTO calendar_events (week_number, date, event_type, description)
                VALUES (?, ?, ?, ?)
            ''', event)
        
        print("✓ Inserted 4 calendar events")
        
        conn.commit()
        print("\n✓ Sample data initialization complete!")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    print("Initializing sample data...")
    init_sample_data()
