#!/bin/bash

# A script to initialize and run the RAG system project

# --- Configuration ---
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

# Start all services (backend + frontend) with Docker Compose
print_info "Starting all services with Docker Compose..."
if ! docker compose -f "$DOCKER_COMPOSE_FILE" up -d --build; then
    print_error "Docker Compose failed to start."
    exit 1
fi
print_success "All services are up and running."
print_info "Frontend: http://localhost:3000"
print_info "Backend API: http://localhost:8200" 