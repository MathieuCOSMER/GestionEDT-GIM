#!/bin/bash

# IUT EDT Management System - Quick Start Script

set -e

PROJECT_DIR="/sessions/optimistic-zen-bardeen/mnt/GestionEDT"
PYTHON_CMD="python3"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "${BLUE}======================================${NC}"
    echo -e "${BLUE}IUT EDT Management System${NC}"
    echo -e "${BLUE}======================================${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}→ $1${NC}"
}

# Main script
main() {
    print_header
    
    # Check if Python is installed
    if ! command -v $PYTHON_CMD &> /dev/null; then
        print_error "Python 3 is not installed or not in PATH"
        exit 1
    fi
    print_success "Python 3 found: $($PYTHON_CMD --version)"
    
    # Navigate to project directory
    cd "$PROJECT_DIR"
    print_success "Changed to project directory"
    
    # Check if requirements.txt exists
    if [ ! -f "requirements.txt" ]; then
        print_error "requirements.txt not found"
        exit 1
    fi
    
    # Check if pip packages are installed
    print_info "Checking Python dependencies..."
    if ! $PYTHON_CMD -c "import flask" 2>/dev/null; then
        print_info "Installing dependencies..."
        $PYTHON_CMD -m pip install -q -r requirements.txt
        print_success "Dependencies installed"
    else
        print_success "Dependencies already installed"
    fi
    
    # Show menu
    echo ""
    echo "Select an option:"
    echo "1) Start Flask server"
    echo "2) Initialize sample data"
    echo "3) Run API tests"
    echo "4) Reset database"
    echo "5) Show configuration"
    echo "6) Exit"
    echo ""
    read -p "Enter your choice (1-6): " choice
    
    case $choice in
        1)
            print_info "Starting Flask server on http://localhost:5000"
            echo ""
            $PYTHON_CMD app.py
            ;;
        2)
            print_info "Loading sample data..."
            $PYTHON_CMD init_sample_data.py
            ;;
        3)
            print_info "Running API tests..."
            if ! $PYTHON_CMD -c "import requests" 2>/dev/null; then
                print_info "Installing requests library..."
                $PYTHON_CMD -m pip install -q requests
            fi
            $PYTHON_CMD test_api.py
            ;;
        4)
            print_info "This will delete all data. Are you sure? (yes/no)"
            read confirm
            if [ "$confirm" = "yes" ]; then
                rm -f edt.db
                print_success "Database reset. Run the server to reinitialize."
            else
                print_info "Cancelled"
            fi
            ;;
        5)
            print_info "Configuration:"
            $PYTHON_CMD -c "from config import get_config; import json; print(json.dumps(get_config(), indent=2))"
            ;;
        6)
            print_info "Exiting..."
            exit 0
            ;;
        *)
            print_error "Invalid choice"
            exit 1
            ;;
    esac
}

main "$@"
