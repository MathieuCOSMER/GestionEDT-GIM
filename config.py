"""
Configuration file for IUT EDT Management System
"""

import os

# Database configuration
DATABASE_PATH = '/sessions/optimistic-zen-bardeen/mnt/GestionEDT/edt.db'
SCHEMA_PATH = '/sessions/optimistic-zen-bardeen/mnt/GestionEDT/schema.sql'

# Server configuration
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 5000
DEBUG_MODE = True

# CORS configuration
CORS_ORIGINS = ['*']  # Allow all origins. For production, specify domains.

# Database configuration
SQLITE_CONFIG = {
    'check_same_thread': False,
    'timeout': 5,
}

# Formation types mapping
FORMATION_TYPES = {
    0: 'FTP',      # Full-time
    1: 'ALT',      # Work-study
    2: 'MUT',      # Mutualized
    3: 'OTHER'     # Other
}

# Teaching types mapping
TEACHING_TYPES = {
    'CM': 'Lecture (Cours Magistral)',
    'TD': 'Tutorial (Travaux Dirigés)',
    'TP 12': 'Lab - 12 students',
    'TP 8': 'Lab - 8 students',
    'PT': 'Project (Projet Tutoré)'
}

# HETD (Service Hours) coefficients
HETD_COEFFICIENTS = {
    'CM': 1.5,      # CM: 1.5x
    'TD': 1.0,      # TD: 1.0x
    'TP 12': 2/3,   # TP: 2/3
    'TP 8': 2/3,    # TP: 2/3
    'PT': 1.0       # PT: 1.0x
}

# Days of week mapping
DAYS_OF_WEEK = {
    0: 'Monday',
    1: 'Tuesday',
    2: 'Wednesday',
    3: 'Thursday',
    4: 'Friday'
}

# Room types
ROOM_TYPES = ['standard', 'info_fixe', 'info_mobile', 'laboratory', 'amphitheater']

# Course types
COURSE_TYPES = ['ressource', 'sae']

# Semester codes and mappings
SEMESTERS = {
    'S1': {'year': 1, 'name': 'First Year - Semester 1'},
    'S2': {'year': 1, 'name': 'First Year - Semester 2'},
    'S3': {'year': 2, 'name': 'Second Year - Semester 3'},
    'S4': {'year': 2, 'name': 'Second Year - Semester 4'},
    'S5': {'year': 3, 'name': 'Third Year - Semester 5'},
    'S6': {'year': 3, 'name': 'Third Year - Semester 6'}
}

# Year groups
YEAR_GROUPS = {
    1: 'First Year (S1, S2)',
    2: 'Second Year (S3, S4)',
    3: 'Third Year (S5, S6)'
}

# Priority levels
PRIORITY_LEVELS = {
    1: 'Preferred',
    2: 'Possible',
    3: 'Avoid'
}

# API Rate Limiting (if needed in future)
RATE_LIMIT_ENABLED = False
RATE_LIMIT_REQUESTS = 1000
RATE_LIMIT_WINDOW = 3600  # seconds

# Logging configuration
LOGGING_LEVEL = 'INFO'
LOGGING_FILE = '/sessions/optimistic-zen-bardeen/mnt/GestionEDT/edt.log'

# Timetable generation settings
TIMETABLE_SETTINGS = {
    'default_slot_duration': 1.5,  # hours
    'earliest_start_time': '08:00',
    'latest_end_time': '18:00',
    'lunch_break_start': '12:00',
    'lunch_break_end': '14:00',
}

# Calendar settings
CALENDAR_SETTINGS = {
    'academic_year_start_month': 9,  # September
    'academic_year_start_day': 1,
    'total_weeks_per_year': 52,
    'weeks_per_semester': 15,
}

# Validation rules
VALIDATION_RULES = {
    'teacher_name_min_length': 2,
    'teacher_name_max_length': 100,
    'room_name_min_length': 1,
    'room_name_max_length': 50,
    'course_code_max_length': 20,
    'course_name_max_length': 200,
    'max_hours_per_day_default': 6,
    'max_hours_per_week': 40,
}

# Feature flags
FEATURES = {
    'enable_excel_import': False,  # Requires openpyxl or pandas
    'enable_conflicts_detection': True,
    'enable_analytics': True,
    'enable_notifications': False,
}

def get_config():
    """Get current configuration as dictionary"""
    return {
        'database': DATABASE_PATH,
        'schema': SCHEMA_PATH,
        'server_host': SERVER_HOST,
        'server_port': SERVER_PORT,
        'debug': DEBUG_MODE,
        'hetd_coefficients': HETD_COEFFICIENTS,
        'formation_types': FORMATION_TYPES,
        'teaching_types': TEACHING_TYPES,
    }

if __name__ == '__main__':
    import json
    print(json.dumps(get_config(), indent=2))
