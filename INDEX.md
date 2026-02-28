# IUT EDT Management System - Complete Index

## Project Directory

```
/sessions/optimistic-zen-bardeen/mnt/GestionEDT/
```

## Files Overview

### Core Application Files

| File | Size | Purpose | Status |
|------|------|---------|--------|
| **app.py** | 44 KB | Main Flask application with 42 API endpoints | ✓ Complete |
| **schema.sql** | 5 KB | SQLite database schema with 10 tables and 9 indexes | ✓ Complete |
| **config.py** | 3 KB | Centralized configuration and constants | ✓ Complete |
| **requirements.txt** | 47 B | Python package dependencies | ✓ Complete |

### Documentation Files

| File | Size | Purpose |
|------|------|---------|
| **README.md** | 8 KB | Comprehensive API reference documentation |
| **DEPLOYMENT.md** | 7 KB | Setup, configuration, and deployment guide |
| **SUMMARY.md** | 6 KB | Overview and complete feature list |
| **QUICK_REFERENCE.md** | 4 KB | Quick command and API examples |
| **INDEX.md** | This file | Complete file listing and descriptions |

### Utility Scripts

| File | Purpose | Executable |
|------|---------|-----------|
| **init_sample_data.py** | Load sample data (5 teachers, 6 rooms, 7 courses, etc.) | python |
| **test_api.py** | Comprehensive API test suite (tests all 42 endpoints) | python |
| **start.sh** | Interactive quick-start script with menu | bash |

### Frontend Files

| File | Purpose |
|------|---------|
| **static/index.html** | Landing page with feature overview |
| **static/** | Directory for CSS, JS, images |

### Generated Files

| File | Purpose | Created |
|------|---------|---------|
| **edt.db** | SQLite database | On first run |

## Quick Start

### 1. Install
```bash
cd /sessions/optimistic-zen-bardeen/mnt/GestionEDT
pip install -r requirements.txt
```

### 2. Run
```bash
python app.py
# Open browser: http://localhost:5000
```

### 3. Load Sample Data (Optional)
```bash
python init_sample_data.py
```

### 4. Test API (Optional)
```bash
python test_api.py
```

## File Descriptions

### app.py - Main Application (44 KB)

**Contains 42 API Endpoints:**

Teachers (7):
- GET/POST /api/teachers
- GET/PUT/DELETE /api/teachers/<id>
- GET/POST /api/teachers/<id>/availability

Rooms (6):
- GET/POST /api/rooms
- GET/PUT/DELETE /api/rooms/<id>

Semesters (6):
- GET/POST /api/semesters
- GET/PUT/DELETE /api/semesters/<id>

Courses (6):
- GET/POST /api/courses
- GET/PUT/DELETE /api/courses/<id>

Course Sessions (7):
- GET/POST /api/course-sessions
- GET/PUT/DELETE /api/course-sessions/<id>
- GET /api/course-sessions/by-course/<id>

Weekly Hours (3):
- GET/POST /api/weekly-hours/<id>
- PUT /api/weekly-hours/batch

Service (2):
- GET /api/service/teacher/<id>
- GET /api/service/all

Timetable (4):
- POST /api/generate-timetable
- GET /api/timetable/week/<n>
- GET /api/timetable/teacher/<id>/week/<n>
- DELETE /api/timetable/week/<n>

Calendar (2):
- GET/POST /api/calendar

Static (2):
- GET /
- GET /<path>

**Features:**
- CORS enabled for frontend integration
- SQLite database connection
- Comprehensive error handling
- JSON request/response
- Input validation
- HETD calculation system
- Timestamp auditing

### schema.sql - Database Schema (5 KB)

**10 Tables:**
1. teachers - Faculty members
2. teacher_availability - Time slots
3. rooms - Facilities
4. semesters - Academic periods
5. courses - Course definitions
6. course_sessions - Teaching sessions
7. weekly_hours - Hour distribution
8. course_sequences - Ordering constraints
9. timetable_slots - Generated schedule
10. calendar_events - Academic calendar

**9 Indexes:**
- Optimized queries for common lookups
- Foreign key constraints
- Unique constraints
- Cascade deletes

### config.py - Configuration (3 KB)

**Contains:**
- Database paths
- Server settings
- HETD coefficients (CM: 1.5, TD: 1.0, TP: 0.667, PT: 1.0)
- Formation type mappings (FTP, ALT, MUT, OTHER)
- Teaching type definitions
- Day/week constants
- Priority levels
- Validation rules

### requirements.txt

**Dependencies:**
```
Flask==3.0.0
Flask-CORS==4.0.0
Werkzeug==3.0.0
```

### README.md - API Documentation (8 KB)

**Sections:**
1. Features overview
2. Installation instructions
3. Database information
4. Complete API reference (all 42 endpoints documented)
5. HETD calculation formulas
6. Formation types and course types
7. Error handling guide
8. File structure
9. Configuration options

### DEPLOYMENT.md - Setup Guide (7 KB)

**Sections:**
1. Quick start (5 steps)
2. Project structure overview
3. API routes overview (42 endpoints)
4. Database schema details
5. Configuration guide
6. Testing procedures
7. Performance optimizations
8. Backup and recovery
9. Troubleshooting
10. Production deployment notes

### SUMMARY.md - System Overview (6 KB)

**Sections:**
1. Project overview
2. File descriptions
3. Complete endpoint list (42)
4. Database structure (10 tables)
5. Key features (7 major categories)
6. Quick start guide
7. Configuration
8. Error handling
9. Testing options
10. System requirements

### QUICK_REFERENCE.md - Quick Commands (4 KB)

**Sections:**
1. Starting the application
2. API examples with curl
3. Data structure examples
4. Key constants and mappings
5. Common tasks
6. HTTP status codes
7. Common HTTP methods
8. Response formats
9. File locations and database info
10. API endpoint summary
11. Common queries
12. Tips & tricks

### init_sample_data.py - Sample Data Loader

**Loads:**
- 5 sample teachers (Jean Dupont, Marie Martin, etc.)
- 6 sample rooms (A101, B201, etc.)
- 6 sample semesters (S1-S6)
- 7 sample courses (R1.01, SAE1.1, etc.)
- 8 sample course sessions (CM, TD, TP, PT)
- 8 availability slots
- 120 weekly hour entries
- 4 calendar events

**Usage:**
```bash
python init_sample_data.py
```

### test_api.py - Test Suite

**Tests:**
- All 42 endpoints
- CRUD operations
- Relationships and foreign keys
- Error handling
- Data validation
- Colored output
- Request/response examples

**Usage:**
```bash
pip install requests  # First time only
python test_api.py
```

### start.sh - Interactive Script

**Menu Options:**
1. Start Flask server
2. Initialize sample data
3. Run API tests
4. Reset database
5. Show configuration
6. Exit

**Usage:**
```bash
./start.sh
```

### static/index.html - Landing Page

**Features:**
- Responsive design
- Feature overview cards
- API endpoint listing
- Test functionality
- Beautiful styling
- Professional layout

**Access:**
```
http://localhost:5000/
```

## Database Location

```
/sessions/optimistic-zen-bardeen/mnt/GestionEDT/edt.db
```

- Auto-created on first run
- Auto-initialized from schema.sql
- SQLite format
- No setup required

## Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Backend | Flask | 3.0.0 |
| CORS | Flask-CORS | 4.0.0 |
| Database | SQLite | Built-in |
| Server | Werkzeug | 3.0.0 |
| Language | Python | 3.7+ |

## API Statistics

| Metric | Count |
|--------|-------|
| Total Endpoints | 42 |
| HTTP Methods | 4 (GET, POST, PUT, DELETE) |
| Database Tables | 10 |
| Database Indexes | 9 |
| Relationships | 8 (foreign keys) |
| Request Types | JSON |
| Response Types | JSON |

## Data Model Statistics

| Category | Count |
|----------|-------|
| Formation Types | 4 (FTP, ALT, MUT, OTHER) |
| Teaching Types | 5 (CM, TD, TP 12, TP 8, PT) |
| Course Types | 2 (ressource, sae) |
| Room Types | Multiple |
| Semesters | 6 (S1-S6) |
| Years | 3 (Year 1, 2, 3) |
| Days per Week | 5 (Mon-Fri) |
| Priority Levels | 3 (Preferred, Possible, Avoid) |

## Feature Checklist

- ✓ Teacher management (CRUD)
- ✓ Teacher availability scheduling
- ✓ Room management (CRUD)
- ✓ Semester management (CRUD)
- ✓ Course management (CRUD)
- ✓ Course session management (CRUD)
- ✓ Weekly hour distribution
- ✓ HETD calculation system
- ✓ Timetable generation
- ✓ Service hour tracking
- ✓ Calendar management
- ✓ Error handling
- ✓ Input validation
- ✓ Sample data loader
- ✓ Test suite
- ✓ Documentation (4 guides)
- ✓ Configuration management
- ✓ CORS enabled
- ✓ Timestamp auditing
- ✓ Database indexing

## Documentation Files by Purpose

### Getting Started
1. DEPLOYMENT.md - Initial setup
2. QUICK_REFERENCE.md - First commands to try

### Learning the API
1. README.md - Complete API documentation
2. test_api.py - Working examples

### Understanding the System
1. SUMMARY.md - System overview
2. app.py - Source code with comments
3. schema.sql - Database structure

### Configuration
1. config.py - All settings
2. DEPLOYMENT.md - Configuration section

### Troubleshooting
1. DEPLOYMENT.md - Troubleshooting section
2. test_api.py - Test if everything works

## Support Resources

### Code Documentation
- app.py: Inline comments explaining each endpoint
- schema.sql: Comments on table purposes
- config.py: Configuration explanations
- Functions have docstrings

### Examples
- init_sample_data.py: Complete data examples
- test_api.py: All API endpoint examples
- QUICK_REFERENCE.md: curl command examples
- README.md: Request/response examples

### Guides
- DEPLOYMENT.md: Step-by-step setup
- README.md: Complete API reference
- QUICK_REFERENCE.md: Common tasks
- SUMMARY.md: System overview

## File Sizes Summary

| Category | Size | Files |
|----------|------|-------|
| Application | 44 KB | app.py |
| Schema | 5 KB | schema.sql |
| Configuration | 3 KB | config.py |
| Documentation | 25 KB | 4 guides |
| Utilities | 12 KB | 3 scripts |
| Frontend | 6 KB | index.html |
| Database | ~50 KB | edt.db (created) |
| **Total** | **~145 KB** | **11 files** |

## Getting Help

1. **API Questions** → README.md
2. **Setup Issues** → DEPLOYMENT.md
3. **Command Examples** → QUICK_REFERENCE.md
4. **System Overview** → SUMMARY.md
5. **Configuration** → config.py
6. **Source Code** → app.py

## Quick Links to Key Sections

### Installation
- See: DEPLOYMENT.md → Quick Start section
- Files: requirements.txt, app.py

### API Documentation
- See: README.md → API Reference section
- Files: app.py (implementation), test_api.py (examples)

### Database
- See: README.md → Database section
- Files: schema.sql (structure), config.py (settings)

### Configuration
- See: DEPLOYMENT.md → Configuration section
- Files: config.py (all settings)

### Troubleshooting
- See: DEPLOYMENT.md → Troubleshooting section
- Files: test_api.py (verify functionality)

## Next Steps

1. **Read**: DEPLOYMENT.md (5 min)
2. **Install**: pip install -r requirements.txt (1 min)
3. **Run**: python app.py (instant)
4. **Test**: python test_api.py (2 min)
5. **Explore**: Visit http://localhost:5000

---

**Complete Flask Backend for IUT EDT Management System - Ready to Deploy!**

Created: 2026-02-28
Location: /sessions/optimistic-zen-bardeen/mnt/GestionEDT/
Status: Fully Functional
