# EDTGestion Excel Import Script

## Summary

The `import_excel.py` script has been successfully created and tested. It imports data from the Excel file at:
```
/sessions/optimistic-zen-bardeen/mnt/uploads/placement cours semaine BUT 25-26 V3.xlsx
```

Into the SQLite database at:
```
/sessions/optimistic-zen-bardeen/mnt/GestionEDT/edt.db
```

## Script Location

**File:** `/sessions/optimistic-zen-bardeen/mnt/GestionEDT/import_excel.py`

**Size:** ~8.8 KB

**Permissions:** Executable (chmod +x)

## Features

### Data Imported

The script successfully imports:

1. **Teachers** (38 records)
   - From: "Contact Vacataire" sheet
   - Fields: name, email, phone, structure, corps_code

2. **Semesters** (6 records)
   - S1-S6 with appropriate year groups (1-3)
   - Auto-created during import

3. **Courses** (147 records)
   - Type: RESSOURCE (starting with "R") or SAE (starting with "SAE")
   - From: S1+S2, S3+S4, S5+S6 sheets
   - Fields: code, name, semester_id, course_type

4. **Course Sessions** (739 records)
   - Teacher assignments per course
   - Formation types (FTP=0, ALT=1, MUT=2)
   - Teaching types (CM, TD, TP, etc.)
   - Room assignments
   - Sessions count and total hours

5. **Rooms** (11 records)
   - STD, 123, 129, 228, 19, 127, 124, 126
   - Auto-created during import

6. **Weekly Hours** (2438 records)
   - Hours per week for each course session
   - Calendar week numbers
   - BUT week numbers (semester weeks)

### Excel File Structure

The script handles the complex Excel structure:

**Sheets S1+S2, S3+S4, S5+S6:**
- Row 0: Header and semester name
- Row 1: BUT week numbers
- Row 2: Calendar week numbers
- Row 3-4: Total hours per week (FTP and ALT)
- Row 5+: Course data
- Columns 0-9: Course metadata
- Columns 10+: Weekly hours distribution

**Columns in course data:**
- Col 0: Course code (R1.01, SAE1.1, etc.)
- Col 1: Course name
- Col 2: Teacher name
- Col 3: Number of sessions
- Col 4: Formation type (0=FTP, 1=ALT, 2=MUT)
- Col 5: Teaching type (CM, TD, TP, etc.)
- Col 6: Total hours
- Col 7: Diff
- Col 8: Room name
- Col 9: Promo label
- Cols 10+: Hours per week (mapped to calendar weeks)

**Contact Vacataire sheet:**
- Row 0: Empty
- Row 1: Headers
- Row 2+: Teacher contact data
  - Col 0: Structure/Entreprise
  - Col 2: Last name
  - Col 3: First name
  - Col 5: Corps code
  - Col 6: Email
  - Col 7: Phone

## Usage

### Run the script:
```bash
python3 /sessions/optimistic-zen-bardeen/mnt/GestionEDT/import_excel.py
```

### Expected output:
```
================================================================================
EDTGestion Excel Import Script
================================================================================

[1/8] Creating in-memory database...
[2/8] Loading Excel data...
[3/8] Importing teachers...
[4/8] Creating semesters...
[5/8] Importing courses and sessions...
[6/8] Computing summary...
[7/8] Copying database to final location...
[8/8] Final Summary
================================================================================

Data imported successfully to: /sessions/optimistic-zen-bardeen/mnt/GestionEDT/edt.db

  Teachers:         38
  Semesters:        6
  Courses:          147
  Course Sessions:  739
  Rooms:            11
  Weekly Hours:     2438

================================================================================

Import completed successfully!
```

## Technical Details

### Implementation Approach

The script uses a **two-stage process** to handle file system I/O issues:

1. **In-Memory Database Creation**
   - Creates a temporary SQLite database in memory
   - Loads and executes the schema from schema.sql
   - Processes all Excel data
   - Commits all transactions

2. **File Transfer**
   - Uses subprocess `cp` command for reliable file copying
   - Transfers the completed database to the target location

### Data Processing

- **Name Normalization:** All teacher names are normalized (uppercase, whitespace stripped)
- **Duplicate Handling:** Uses UNIQUE constraints and IntegrityError handling
- **Week Mapping:** Maps BUT weeks to calendar weeks from Excel headers
- **Multi-Semester Support:** Correctly splits courses before/after "Semestre 2" marker
- **Lazy Teacher Creation:** Teachers created on-demand during course import or from Contact Vacataire

### Database Schema

Uses 11 tables from `schema.sql`:
- teachers
- teacher_availability
- rooms
- semesters
- courses
- course_sessions
- weekly_hours
- course_sequences
- timetable_slots
- calendar_events
- sqlite_sequence (auto-created)

All tables have proper foreign keys and indexes for performance.

## Files Created

- **import_excel.py** (8.8 KB) - The main import script
- **IMPORT_SUMMARY.md** (this file) - Documentation

## Version

- Script Version: 1.0
- Python 3.6+
- Dependencies: pandas, sqlite3 (built-in)

## Notes

- The script is idempotent: running it multiple times will overwrite existing data
- No dependencies beyond pandas and standard library
- Creates temporary directory during execution, cleaned up automatically
- All operations are wrapped in error handling for robustness

