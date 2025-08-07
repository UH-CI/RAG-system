#!/bin/bash

# A script to initialize and run the RAG system project

# --- Configuration ---
FRONTEND_DIR="frontend"
DOCKER_COMPOSE_FILE="docker-compose.yml"

# --- Helper Functions ---
print_info() {
    echo "ℹ️  $1"
}

print_success() {
    echo "✅ $1"
}

print_error() {
    echo "❌ $1" >&2
}

# --- Main Logic ---

# Default behavior
INIT=false

# Check for --init flag
if [ "$1" == "--init" ]; then
    INIT=true
fi

# Initialization step
if [ "$INIT" = true ]; then
    print_info "Running frontend setup (--init flag detected)..."
    
    # Check if frontend directory exists
    if [ ! -d "$FRONTEND_DIR" ]; then
        print_error "Frontend directory '$FRONTEND_DIR' not found!"
        exit 1
    fi

    # Navigate to the frontend directory
    cd "$FRONTEND_DIR" || exit

    # Install npm dependencies
    print_info "Installing frontend dependencies..."
    if ! npm install; then
        print_error "npm install failed."
        exit 1
    fi
    
    # Navigate back to the root directory
    cd ..
    print_success "Frontend setup complete."
fi

# Start the backend services
print_info "Starting backend services with Docker Compose..."
if ! docker-compose -f "$DOCKER_COMPOSE_FILE" up -d --build; then
    print_error "Docker Compose failed to start."
    exit 1
fi
print_success "Backend services are up and running."

# Start the frontend development server
print_info "Starting the frontend development server..."
if [ -d "$FRONTEND_DIR" ]; then
    cd "$FRONTEND_DIR" || exit
    npm run dev
else
    print_error "Frontend directory '$FRONTEND_DIR' not found!"
    exit 1
fi 