FROM python:3.11-slim

# Set working directory
WORKDIR /src

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    poppler-utils \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/* 

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code into a src subdirectory
COPY . .

# Note: ChromaDB data will be provided via volume mount in production
# (chroma_db/ should be excluded via .dockerignore to avoid conflicts)

# Set environment variables
ENV PYTHONPATH=/src
ENV PYTHONUNBUFFERED=1

# Expose ports (8200 for API, 8280 for test interface)
EXPOSE 8200 8280

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8200/ || exit 1

# Production command: gunicorn with 4 uvicorn workers (tuned for 4 CPU cores / 15 GB RAM)
CMD ["gunicorn", "api:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8200", \
     "--timeout", "120", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]