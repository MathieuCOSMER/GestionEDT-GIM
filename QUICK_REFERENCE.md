# IUT EDT Management System - Quick Reference Guide

## Starting the Application

```bash
cd /sessions/optimistic-zen-bardeen/mnt/GestionEDT
pip install -r requirements.txt
python app.py
```

Server runs on: `http://localhost:5000`

## API Quick Reference

### Create a Teacher
```bash
curl -X POST http://localhost:5000/api/teachers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Dr. John Doe",
    "email": "john@iut.fr",
    "structure": "Computer Science",
    "max_hours_day": 6
  }'
```

### Get All Teachers
```bash
curl http://localhost:5000/api/teachers
```

### Create a Room
```bash
curl -X POST http://localhost:5000/api/rooms \
  -H "Content-Type: application/json" \
  -d '{
    "name": "A101",
    "capacity": 30,
    "room_type": "standard"
  }'
```

### Create a Semester
```bash
curl -X POST http://localhost:5000/api/semesters \
  -H "Content-Type: application/json" \
  -d '{
    "code": "S1",
    "year_group": 1,
    "name": "First Year - Semester 1",
    "start_week": 1,
    "end_week": 15
  }'
```

### Create a Course
```bash
curl -X POST http://localhost:5000/api/courses \
  -H "Content-Type: application/json" \
  -d '{
    "code": "R1.01",
    "name": "Programming",
    "semester_id": 1,
    "course_type": "ressource"
  }'
```

### Create a Course Session
```bash
curl -X POST http://localhost:5000/api/course-sessions \
  -H "Content-Type: application/json" \
  -d '{
    "course_id": 1,
    "teacher_id": 1,
    "formation_type": 0,
    "teaching_type": "CM",
    "total_hours": 15
  }'
```

### Add Weekly Hours
```bash
curl -X POST http://localhost:5000/api/weekly-hours/1 \
  -H "Content-Type: application/json" \
  -d '{
    "week_number": 1,
    "semester_week": 1,
    "hours": 3
  }'
```

### Generate Timetable
```bash
curl -X POST http://localhost:5000/api/generate-timetable \
  -H "Content-Type: application/json" \
  -d '{
    "weeks": [1, 2, 3, 4, 5]
  }'
```

### Get Teacher HETD
```bash
curl http://localhost:5000/api/service/teacher/1
```

### Get Timetable for Week
```bash
curl http://localhost:5000/api/timetable/week/1
```

## Data Structure Examples

### Teacher Object
```json
{
  "id": 1,
  "name": "Dr. Jean Dupont",
  "email": "jean.dupont@iut.fr",
  "phone": "01.98.76.54.32",
  "structure": "Computer Science",
  "corps_code": "PR",
  "max_hours_day": 6,
  "priority": 1
}
```

### Room Object
```json
{
  "id": 1,
  "name": "A101",
  "capacity": 30,
  "room_type": "standard",
  "location": "Building A"
}
```

### Course Object
```json
{
  "id": 1,
  "code": "R1.01",
  "name": "Programming",
  "semester_id": 1,
  "course_type": "ressource"
}
```

### Course Session Object
```json
{
  "id": 1,
  "course_id": 1,
  "teacher_id": 1,
  "formation_type": 0,
  "teaching_type": "CM",
  "nb_sessions": 10,
  "total_hours": 15,
  "slot_duration": 1.5,
  "room_name": "A101",
  "promo": "FTP"
}
```

## Key Constants

### Formation Types
- 0: FTP (Full-time)
- 1: ALT (Work-study/Alternance)
- 2: MUT (Mutualized)
- 3: OTHER

### Teaching Types
- CM: Lecture (Cours Magistral)
- TD: Tutorial (Travaux Dirigés)
- TP 12: Lab - 12 students
- TP 8: Lab - 8 students
- PT: Project (Projet Tutoré)

### HETD Coefficients
- CM: 1.5x
- TD: 1.0x
- TP: 0.667x (2/3)
- PT: 1.0x

### Days of Week
- 0: Monday
- 1: Tuesday
- 2: Wednesday
- 3: Thursday
- 4: Friday

### Course Types
- ressource: Standard course
- sae: Mini-project

### Priority Levels
- 1: Preferred
- 2: Possible
- 3: Avoid

## Semesters (S1-S6)
```
Year 1: S1, S2
Year 2: S3, S4
Year 3: S5, S6
```

## Common Tasks

### Load Sample Data
```bash
python init_sample_data.py
```

### Run Tests
```bash
python test_api.py
```

### Reset Database
```bash
rm edt.db
python app.py  # Recreates database
```

### View Configuration
```bash
python -c "from config import get_config; import json; print(json.dumps(get_config(), indent=2))"
```

## HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | OK (GET, PUT, DELETE successful) |
| 201 | Created (POST successful) |
| 400 | Bad Request (invalid data) |
| 404 | Not Found (resource doesn't exist) |
| 500 | Server Error |
| 501 | Not Implemented |

## Common HTTP Methods

| Method | Purpose |
|--------|---------|
| GET | Retrieve data |
| POST | Create new data |
| PUT | Update existing data |
| DELETE | Remove data |

## Response Format

### Success
```json
{
  "id": 1,
  "name": "Example",
  ...
}
```

### Error
```json
{
  "error": "Description of what went wrong"
}
```

## File Locations

| File | Purpose |
|------|---------|
| app.py | Main application (42 endpoints) |
| schema.sql | Database schema |
| config.py | Configuration |
| requirements.txt | Python dependencies |
| edt.db | SQLite database |
| static/index.html | Frontend |
| README.md | Full documentation |
| DEPLOYMENT.md | Setup guide |

## Environment Setup

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Python Version Required
```
Python 3.7 or higher
```

### Required Packages
- Flask 3.0.0
- Flask-CORS 4.0.0
- Werkzeug 3.0.0

## Database Info

| Property | Value |
|----------|-------|
| Type | SQLite |
| Location | /sessions/optimistic-zen-bardeen/mnt/GestionEDT/edt.db |
| Tables | 10 |
| Indexes | 9 |
| Auto-Init | Yes (from schema.sql) |

## API Endpoint Summary

| Category | Count | Routes |
|----------|-------|--------|
| Teachers | 7 | CRUD + availability |
| Rooms | 6 | CRUD |
| Semesters | 6 | CRUD |
| Courses | 6 | CRUD |
| Sessions | 7 | CRUD + by-course |
| Weekly Hours | 3 | Get/Create/Batch |
| Service | 2 | Teacher/All |
| Timetable | 4 | Generate/Get/Delete |
| Calendar | 2 | Get/Create |
| Static | 2 | Root/Files |
| **TOTAL** | **42** | |

## Common Queries

### Get Teachers in Department
```bash
curl http://localhost:5000/api/teachers | jq '.[] | select(.structure=="Computer Science")'
```

### Get Courses by Semester
```bash
curl http://localhost:5000/api/courses | jq '.[] | select(.semester_id==1)'
```

### Calculate Weekly Service
```bash
# Get all sessions with hours, multiply by HETD coefficient
curl http://localhost:5000/api/service/all | jq '.[] | select(.total_hetd > 0)'
```

## Batch Operations

### Update Multiple Weekly Hours
```bash
curl -X PUT http://localhost:5000/api/weekly-hours/batch \
  -H "Content-Type: application/json" \
  -d '[
    {"id": 1, "hours": 3, "semester_week": 1},
    {"id": 2, "hours": 2, "semester_week": 1}
  ]'
```

## Testing with Python

```python
import requests

# Get all teachers
resp = requests.get('http://localhost:5000/api/teachers')
teachers = resp.json()

# Create a teacher
data = {'name': 'New Teacher', 'email': 'new@iut.fr'}
resp = requests.post('http://localhost:5000/api/teachers', json=data)
new_teacher = resp.json()

# Update a teacher
resp = requests.put('http://localhost:5000/api/teachers/1', 
                   json={'email': 'updated@iut.fr'})

# Delete a teacher
resp = requests.delete('http://localhost:5000/api/teachers/1')
```

## Tips & Tricks

1. **Use jq for JSON filtering** (if installed):
   ```bash
   curl http://localhost:5000/api/teachers | jq '.[] | .name'
   ```

2. **Save response to file**:
   ```bash
   curl http://localhost:5000/api/teachers > teachers.json
   ```

3. **Pretty print JSON**:
   ```bash
   curl http://localhost:5000/api/teachers | python -m json.tool
   ```

4. **Check server is running**:
   ```bash
   curl -I http://localhost:5000/
   ```

5. **Test with headers**:
   ```bash
   curl -H "Content-Type: application/json" http://localhost:5000/api/teachers
   ```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Port 5000 in use | Change port in app.py |
| Module not found | Run `pip install -r requirements.txt` |
| Database locked | Delete `.db-wal` and `.db-shm` files |
| No response | Check if server is running on correct port |
| Import errors | Ensure Python 3.7+ is installed |

## Resources

- Full API docs: `README.md`
- Setup guide: `DEPLOYMENT.md`
- Configuration: `config.py`
- Examples: `init_sample_data.py`
- Tests: `test_api.py`

## Support

For help, refer to:
1. README.md - Complete documentation
2. DEPLOYMENT.md - Common issues and solutions
3. test_api.py - Working examples
4. init_sample_data.py - Data structure examples

---

**Happy scheduling!** The IUT EDT Management System is ready to use.
