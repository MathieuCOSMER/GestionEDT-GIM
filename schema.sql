-- Teachers table
CREATE TABLE IF NOT EXISTS teachers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    email TEXT,
    phone TEXT,
    structure TEXT,
    corps_code TEXT,
    max_hours_day REAL DEFAULT 6,
    priority INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Teacher availability (dispos)
CREATE TABLE IF NOT EXISTS teacher_availability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    available INTEGER DEFAULT 1,
    priority INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE CASCADE
);

-- Rooms
CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    capacity INTEGER,
    room_type TEXT DEFAULT 'standard',
    location TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Semesters
CREATE TABLE IF NOT EXISTS semesters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    year_group INTEGER NOT NULL,
    name TEXT,
    start_week INTEGER,
    end_week INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Courses (Ressources and SAE)
CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    semester_id INTEGER NOT NULL,
    course_type TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE CASCADE
);

-- Course sessions
CREATE TABLE IF NOT EXISTS course_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    teacher_id INTEGER,
    formation_type INTEGER NOT NULL,
    teaching_type TEXT NOT NULL,
    nb_sessions INTEGER NOT NULL DEFAULT 0,
    total_hours REAL DEFAULT 0,
    slot_duration REAL DEFAULT 1.5,
    room_name TEXT,
    promo TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (teacher_id) REFERENCES teachers(id)
);

-- Weekly distribution
CREATE TABLE IF NOT EXISTS weekly_hours (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_session_id INTEGER NOT NULL,
    week_number INTEGER NOT NULL,
    semester_week INTEGER,
    hours REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (course_session_id) REFERENCES course_sessions(id) ON DELETE CASCADE,
    UNIQUE(course_session_id, week_number)
);

-- Course sequencing constraints
CREATE TABLE IF NOT EXISTS course_sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    predecessor_session_id INTEGER NOT NULL,
    successor_session_id INTEGER NOT NULL,
    min_gap_weeks INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (predecessor_session_id) REFERENCES course_sessions(id),
    FOREIGN KEY (successor_session_id) REFERENCES course_sessions(id)
);

-- Generated timetable slots
CREATE TABLE IF NOT EXISTS timetable_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_session_id INTEGER NOT NULL,
    week_number INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    room_id INTEGER,
    teacher_id INTEGER,
    formation_type INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (course_session_id) REFERENCES course_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (room_id) REFERENCES rooms(id),
    FOREIGN KEY (teacher_id) REFERENCES teachers(id)
);

-- Academic calendar
CREATE TABLE IF NOT EXISTS calendar_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_number INTEGER,
    date TEXT,
    event_type TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Semester special weeks (vacances FTP, semaines entreprise ALT)
CREATE TABLE IF NOT EXISTS semester_special_weeks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    semester_id INTEGER NOT NULL,
    week_number INTEGER NOT NULL,
    week_type TEXT NOT NULL CHECK(week_type IN ('vacation_ftp', 'company_alt')),
    FOREIGN KEY (semester_id) REFERENCES semesters(id) ON DELETE CASCADE,
    UNIQUE(semester_id, week_number, week_type)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_teacher_availability_teacher ON teacher_availability(teacher_id);
CREATE INDEX IF NOT EXISTS idx_courses_semester ON courses(semester_id);
CREATE INDEX IF NOT EXISTS idx_course_sessions_course ON course_sessions(course_id);
CREATE INDEX IF NOT EXISTS idx_course_sessions_teacher ON course_sessions(teacher_id);
CREATE INDEX IF NOT EXISTS idx_weekly_hours_session ON weekly_hours(course_session_id);
CREATE INDEX IF NOT EXISTS idx_timetable_slots_session ON timetable_slots(course_session_id);
CREATE INDEX IF NOT EXISTS idx_timetable_slots_week ON timetable_slots(week_number);
CREATE INDEX IF NOT EXISTS idx_timetable_slots_teacher ON timetable_slots(teacher_id);
