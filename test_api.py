"""
Test script for IUT EDT Management System API
Tests all API endpoints
"""

import requests
import json

BASE_URL = 'http://localhost:5000'

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_success(msg):
    print(f"{Colors.GREEN}✓ {msg}{Colors.END}")

def print_error(msg):
    print(f"{Colors.RED}✗ {msg}{Colors.END}")

def print_info(msg):
    print(f"{Colors.BLUE}→ {msg}{Colors.END}")

def test_endpoint(method, path, data=None, expected_status=200):
    """Test an API endpoint"""
    url = f"{BASE_URL}{path}"
    try:
        if method == 'GET':
            response = requests.get(url)
        elif method == 'POST':
            response = requests.post(url, json=data)
        elif method == 'PUT':
            response = requests.put(url, json=data)
        elif method == 'DELETE':
            response = requests.delete(url)
        
        if response.status_code == expected_status:
            print_success(f"{method} {path} - {response.status_code}")
            return response.json() if response.text else None
        else:
            print_error(f"{method} {path} - Expected {expected_status}, got {response.status_code}")
            return None
    except Exception as e:
        print_error(f"{method} {path} - {str(e)}")
        return None

def run_tests():
    """Run all API tests"""
    print(f"\n{Colors.YELLOW}=== IUT EDT Management System - API Tests ==={Colors.END}\n")
    
    # Test Teachers
    print_info("Testing Teachers API")
    teacher_data = {
        'name': 'Test Teacher',
        'email': 'test@iut.fr',
        'phone': '01.23.45.67.89',
        'structure': 'Test Dept'
    }
    result = test_endpoint('POST', '/api/teachers', teacher_data, 201)
    teacher_id = result['id'] if result else 1
    
    test_endpoint('GET', '/api/teachers', expected_status=200)
    test_endpoint('GET', f'/api/teachers/{teacher_id}', expected_status=200)
    test_endpoint('PUT', f'/api/teachers/{teacher_id}', {'email': 'updated@iut.fr'}, 200)
    test_endpoint('GET', f'/api/teachers/{teacher_id}/availability', expected_status=200)
    
    # Test Rooms
    print_info("\nTesting Rooms API")
    room_data = {
        'name': 'Test Room',
        'capacity': 30,
        'room_type': 'standard'
    }
    result = test_endpoint('POST', '/api/rooms', room_data, 201)
    room_id = result['id'] if result else 1
    
    test_endpoint('GET', '/api/rooms', expected_status=200)
    test_endpoint('GET', f'/api/rooms/{room_id}', expected_status=200)
    test_endpoint('PUT', f'/api/rooms/{room_id}', {'capacity': 40}, 200)
    
    # Test Semesters
    print_info("\nTesting Semesters API")
    semester_data = {
        'code': 'TEST1',
        'year_group': 1,
        'name': 'Test Semester',
        'start_week': 1,
        'end_week': 15
    }
    result = test_endpoint('POST', '/api/semesters', semester_data, 201)
    semester_id = result['id'] if result else 1
    
    test_endpoint('GET', '/api/semesters', expected_status=200)
    test_endpoint('GET', f'/api/semesters/{semester_id}', expected_status=200)
    
    # Test Courses
    print_info("\nTesting Courses API")
    course_data = {
        'code': 'TEST01',
        'name': 'Test Course',
        'semester_id': semester_id,
        'course_type': 'ressource'
    }
    result = test_endpoint('POST', '/api/courses', course_data, 201)
    course_id = result['id'] if result else 1
    
    test_endpoint('GET', '/api/courses', expected_status=200)
    test_endpoint('GET', f'/api/courses/{course_id}', expected_status=200)
    
    # Test Course Sessions
    print_info("\nTesting Course Sessions API")
    session_data = {
        'course_id': course_id,
        'teacher_id': teacher_id,
        'formation_type': 0,
        'teaching_type': 'CM',
        'nb_sessions': 10,
        'total_hours': 15
    }
    result = test_endpoint('POST', '/api/course-sessions', session_data, 201)
    session_id = result['id'] if result else 1
    
    test_endpoint('GET', '/api/course-sessions', expected_status=200)
    test_endpoint('GET', f'/api/course-sessions/{session_id}', expected_status=200)
    test_endpoint('GET', f'/api/course-sessions/by-course/{course_id}', expected_status=200)
    
    # Test Weekly Hours
    print_info("\nTesting Weekly Hours API")
    hours_data = {
        'week_number': 1,
        'semester_week': 1,
        'hours': 3
    }
    test_endpoint('POST', f'/api/weekly-hours/{session_id}', hours_data, 201)
    test_endpoint('GET', f'/api/weekly-hours/{session_id}', expected_status=200)
    
    # Test Service Calculation
    print_info("\nTesting Service Calculation API")
    test_endpoint('GET', f'/api/service/teacher/{teacher_id}', expected_status=200)
    test_endpoint('GET', '/api/service/all', expected_status=200)
    
    # Test Calendar
    print_info("\nTesting Calendar API")
    event_data = {
        'week_number': 3,
        'date': '2024-01-15',
        'event_type': 'vacation',
        'description': 'Test Vacation'
    }
    test_endpoint('POST', '/api/calendar', event_data, 201)
    test_endpoint('GET', '/api/calendar', expected_status=200)
    
    # Test Timetable Generation
    print_info("\nTesting Timetable API")
    timetable_data = {'weeks': [1, 2, 3]}
    test_endpoint('POST', '/api/generate-timetable', timetable_data, 200)
    test_endpoint('GET', '/api/timetable/week/1', expected_status=200)
    test_endpoint('GET', f'/api/timetable/teacher/{teacher_id}/week/1', expected_status=200)
    
    # Test cleanup
    print_info("\nTesting Cleanup")
    test_endpoint('DELETE', '/api/timetable/week/1', expected_status=200)
    test_endpoint('DELETE', f'/api/course-sessions/{session_id}', expected_status=200)
    test_endpoint('DELETE', f'/api/courses/{course_id}', expected_status=200)
    test_endpoint('DELETE', f'/api/semesters/{semester_id}', expected_status=200)
    test_endpoint('DELETE', f'/api/rooms/{room_id}', expected_status=200)
    test_endpoint('DELETE', f'/api/teachers/{teacher_id}', expected_status=200)
    
    print(f"\n{Colors.YELLOW}=== Tests Complete ==={Colors.END}\n")

if __name__ == '__main__':
    try:
        run_tests()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Tests interrupted by user{Colors.END}")
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
