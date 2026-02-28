# Deployment Guide - IUT EDT Management System

## Quick Start

### 1. Navigate to project directory
```bash
cd /sessions/optimistic-zen-bardeen/mnt/GestionEDT
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Initialize the application
```bash
python app.py
```

The server will start on `http://localhost:5000`

### 4. (Optional) Load sample data
In a new terminal:
```bash
cd /sessions/optimistic-zen-bardeen/mnt/GestionEDT
python init_sample_data.py
```

### 5. (Optional) Test the API
In a new terminal:
```bash
cd /sessions/optimistic-zen-bardeen/mnt/GestionEDT
pip install requests
python test_api.py
```

## Project Structure

```
/sessions/optimistic-zen-bardeen/mnt/GestionEDT/
│
├── app.py                      # Main Flask application (44 KB)
│   ├── Teachers CRUD (6 routes)
│   ├── Rooms CRUD (6 routes)
│   ├── Semesters CRUD (6 routes)
│   ├── Courses CRUD (6 routes)
│   ├── Course Sessions CRUD (7 routes)
│   ├── Weekly Hours (3 routes)
│   ├── Service Calculation (2 routes)
│   ├── Timetable Generation (4 routes)
│   ├── Calendar (2 routes)
│   └── Total: 42 API endpoints
│
├── schema.sql                  # Database schema (5 KB)
│   ├── 10 data tables
│   ├── 9 indexes
│   └── Foreign key constraints
│
├── requirements.txt            # Python dependencies
│   ├── Flask 3.0.0
│   ├── Flask-CORS 4.0.0
│   └── Werkzeug 3.0.0
│
├── README.md                   # API documentation (8 KB)
├── DEPLOYMENT.md              # This file
│
├── init_sample_data.py         # Sample data loader
├── test_api.py                 # API test suite
│
├── static/                     # Frontend files
│   └── index.html              # Homepage
│
└── edt.db                      # SQLite database (auto-created)
```

## API Routes Overview

### Total: 42 Endpoints

#### Teachers (6 routes)
- GET/POST /api/teachers
- GET/PUT/DELETE /api/teachers/<id>
- GET/POST /api/teachers/<id>/availability

#### Rooms (6 routes)
- GET/POST /api/rooms
- GET/PUT/DELETE /api/rooms/<id>

#### Semesters (6 routes)
- GET/POST /api/semesters
- GET/PUT/DELETE /api/semesters/<id>

#### Courses (6 routes)
- GET/POST /api/courses
- GET/PUT/DELETE /api/courses/<id>

#### Course Sessions (7 routes)
- GET/POST /api/course-sessions
- GET/PUT/DELETE /api/course-sessions/<id>
- GET /api/course-sessions/by-course/<id>

#### Weekly Hours (3 routes)
- GET/POST /api/weekly-hours/<id>
- PUT /api/weekly-hours/batch

#### Service Calculation (2 routes)
- GET /api/service/teacher/<id>
- GET /api/service/all

#### Timetable (4 routes)
- POST /api/generate-timetable
- GET /api/timetable/week/<n>
- GET /api/timetable/teacher/<id>/week/<n>
- DELETE /api/timetable/week/<n>

#### Calendar (2 routes)
- GET/POST /api/calendar

## Database Schema

### 10 Tables

1. **teachers** (6 columns)
   - Faculty members with availability constraints

2. **teacher_availability** (6 columns)
   - Time slots when teachers are available

3. **rooms** (5 columns)
   - Classrooms and facilities

4. **semesters** (6 columns)
   - Academic periods (S1-S6)

5. **courses** (6 columns)
   - Course definitions (Ressources and SAE)

6. **course_sessions** (10 columns)
   - Individual teaching sessions

7. **weekly_hours** (6 columns)
   - Weekly hour distribution

8. **course_sequences** (4 columns)
   - Ordering constraints between sessions

9. **timetable_slots** (10 columns)
   - Generated schedule slots

10. **calendar_events** (5 columns)
    - Academic calendar (vacations, holidays)

## Configuration

### Environment Variables
No environment variables required. All settings are in `app.py`:

```python
DATABASE = '/sessions/optimistic-zen-bardeen/mnt/GestionEDT/edt.db'
SCHEMA_PATH = '/sessions/optimistic-zen-bardeen/mnt/GestionEDT/schema.sql'
```

### Server Settings
```python
app.run(
    host='0.0.0.0',      # Listen on all interfaces
    port=5000,            # Default port
    debug=True            # Enable debug mode
)
```

### CORS Configuration
```python
CORS(app)  # Enable for all origins
```

## Database Details

### Type: SQLite

**Advantages:**
- No external dependencies
- Single file database
- Good for small to medium applications
- Easy backup and portability

**File Location:**
```
/sessions/optimistic-zen-bardeen/mnt/GestionEDT/edt.db
```

**Auto-initialization:**
- Database is created automatically on first run
- Schema is loaded from `schema.sql`
- No manual database setup required

## Key Features

### 1. Teacher Management
- Teacher profiles with contact info
- Availability scheduling (time slots)
- Priority levels and constraints
- Max hours per day limits

### 2. Course Organization
- Support for 3-year program
- 6 semesters (S1-S6)
- Ressources and SAE courses
- Multiple teaching types (CM, TD, TP, PT)

### 3. Timetable Generation
- Automatic slot creation
- Weekly hour distribution
- Multi-formation support (FTP, ALT, MUT)
- Conflict detection ready

### 4. Service Calculation
- HETD (Équivalent Temps Plein) calculation
- Different coefficients per teaching type:
  - CM: 1.5x
  - TD: 1.0x
  - TP: 0.667x
  - PT: 1.0x

### 5. Academic Calendar
- Holiday management
- Vacation periods
- Semester tracking
- Event scheduling

## Testing

### Manual Testing
Test individual endpoints:
```bash
curl http://localhost:5000/api/teachers
curl -X POST http://localhost:5000/api/teachers \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Teacher"}'
```

### Automated Testing
Run the full test suite:
```bash
python test_api.py
```

This will test all 42 endpoints and verify:
- Create operations (201 status)
- Read operations (200 status)
- Update operations (200 status)
- Delete operations (200 status)
- Error handling (404/400 status)

## Performance Optimizations

### Indexes Created
- teacher_availability: teacher_id
- courses: semester_id
- course_sessions: course_id, teacher_id
- weekly_hours: course_session_id
- timetable_slots: course_session_id, week_number, teacher_id

### Query Optimizations
- JOIN operations for related data
- Efficient filtering with WHERE clauses
- Batch operations for bulk updates

## Error Handling

All endpoints return JSON error responses:

```json
{
  "error": "Error description"
}
```

HTTP Status Codes:
- 200: Success (GET, PUT, DELETE)
- 201: Created (POST)
- 400: Bad Request
- 404: Not Found
- 500: Internal Server Error
- 501: Not Implemented

## Backup and Recovery

### Backup Database
```bash
cp /sessions/optimistic-zen-bardeen/mnt/GestionEDT/edt.db \
   /sessions/optimistic-zen-bardeen/mnt/GestionEDT/edt.db.backup
```

### Restore Database
```bash
cp /sessions/optimistic-zen-bardeen/mnt/GestionEDT/edt.db.backup \
   /sessions/optimistic-zen-bardeen/mnt/GestionEDT/edt.db
```

### Reset Database
```bash
rm /sessions/optimistic-zen-bardeen/mnt/GestionEDT/edt.db
python app.py  # Recreates from schema
```

## Troubleshooting

### Port Already in Use
If port 5000 is already in use:
```python
# Edit app.py, change:
app.run(port=5001)  # Use different port
```

### Import Errors
```bash
# Ensure all dependencies are installed:
pip install -r requirements.txt --upgrade
```

### Database Locked
- Close all connections
- Delete `.db-wal` and `.db-shm` files if they exist
- Restart the application

### CORS Issues
- CORS is enabled for all origins by default
- To restrict, modify in app.py:
```python
CORS(app, origins=['http://localhost:3000'])
```

## Production Deployment

### For Production Use:

1. **Disable Debug Mode**
```python
app.run(debug=False)
```

2. **Use Production Server**
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

3. **Database Optimization**
- Add WAL mode for SQLite
- Implement connection pooling
- Regular backups

4. **Security**
- Add authentication
- Validate all inputs
- Use HTTPS
- Rate limiting

5. **Monitoring**
- Log all API requests
- Monitor database size
- Track performance metrics

## Support and Maintenance

### Regular Maintenance Tasks

1. **Weekly**
   - Backup database
   - Check error logs

2. **Monthly**
   - Review API usage statistics
   - Optimize slow queries
   - Update dependencies

3. **Quarterly**
   - Full database optimization
   - Performance analysis
   - Security audit

## Additional Resources

- See `README.md` for API documentation
- See `app.py` for source code comments
- See `schema.sql` for database structure
- Run `test_api.py` for endpoint testing

## Summary

The IUT EDT Management System is a fully functional Flask backend with:
- 42 API endpoints
- 10 data tables
- Comprehensive HETD calculations
- Timetable generation capabilities
- Academic calendar management
- Full CRUD operations
- Error handling
- Sample data loader
- Test suite

Ready for development and deployment!
