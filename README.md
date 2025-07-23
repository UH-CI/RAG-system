# Course RAG System

A generalized document search and question-answering system built with ChromaDB and Google AI embeddings. This system demonstrates RAG (Retrieval-Augmented Generation) capabilities using university course data as an example, but can be adapted for any document collection.

## 🚀 How to Start

### Prerequisites
- Docker installed on your system
- Google API key (for embeddings)
- Git

### 1. Clone and Setup
```bash
# Clone the repository
git clone https://github.com/UH-CI/RAG-system/
cd course-RAG

# Navigate to source directory and setup environment
cd src/
cp .env.example .env
# Edit .env and paste in your Google API key
```

### 2. Initial Deployment with Ingestion
```bash
# Return to project root and run deployment with ingestion
cd ..
./deploy.sh docker --ingest
```

This will start the ingestion process. The documents in `/src/documents` will be ingested according to the configuration in `config.json`.

### 3. Understanding Document Configuration

The `config.json` file controls how documents are processed and ingested:

```json
{
  "collections": ["courses", "programs", "combined_pathways"],
  "ingestion_configs": [
    {
      "collection_name": "courses",
      "source_file": "UH-Manoa_courses.json",
      "contents_to_embed": ["course_id", "subject", "title", "description", "credits", "prerequisites", "program", "department", "institution"]
    },
    {
      "collection_name": "programs", 
      "source_file": "UH-Manoa-programs.json",
      "contents_to_embed": ["name", "program", "department", "college", "institution", "course_count", "courses"]
    }
  ]
}
```

**How it works:**
- Each `ingestion_config` defines a collection to be created in ChromaDB
- `source_file` points to JSON files in the `/src/documents` directory
- `contents_to_embed` specifies which fields from each document will be embedded as searchable content
- The system will look for these files relative to the `/src` directory during ingestion

**Document Structure:**
- Place your JSON data files in `/src/documents/`
- Each file should contain an array of objects with the fields specified in `contents_to_embed`
- The system currently includes example files: `UH-Manoa_courses.json`, `UH-Manoa-programs.json`, etc.

### 4. Production Deployment
Once ingestion is complete and you're satisfied with the setup:

```bash
./deploy.sh docker
```

This will bake the vectors into the ChromaDB database on the Docker image for production usage, creating a self-contained deployment ready for serving.

**The deploy script automatically starts both:**
- **API Server**: `course-rag-api` container on port 8200
- **Web Interface**: `course-rag-test` container on port 8280 (serves `course_rag_interface.html` via `test_server.py`)

### 5. Verify Deployment
```bash
# Check if the API is running
curl http://localhost:8200/

# Check database status and document counts
curl http://localhost:8200/stats

# Access web interface at: http://localhost:8280/course_rag_interface.html
```

**Web Interface Features:**
- **Intelligent Query Tab**: Chat-based interface with preset queries for testing
- **Collections Tab**: Direct vector search across all document collections
- **Real-time Results**: Shows query processing time, document sources, and confidence scores
- **Responsive Design**: Works on desktop and mobile devices

**That's it! 🎉** Your API is running at `http://localhost:8200`

---

## 🛠️ Development Setup

**For developers who want to modify the code**

### Prerequisites
- Python 3.11+
- Git
- Google API key

### 1. Clone Repository
```bash
git clone <your-repo-url>
cd course-RAG
```

### 2. Install Dependencies
```bash
pip install -r src/requirements.txt
```

### 3. Configure Environment
```bash
cp src/.env.example .env
# Edit .env with your Google API key
```

### 4. Run Locally
```bash
cd src
python run_api.py
```

### 5. Run with Document Ingestion
```bash
cd src
python run_api.py --ingest
```

### 6. Test the System
```bash
cd src
python tests/api_client_example.py
```

---

## 📖 Using the API

### Web Interface
- **API Documentation**: http://localhost:8200/docs
- **Interactive Testing**: http://localhost:8200/redoc
- **Test Interface**: http://localhost:8280 (if deployed)

### Search Courses
```bash
curl -X POST "http://localhost:8200/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "computer science programming courses", "n_results": 3}'
```

### Multi-Collection Search
```bash
curl -X POST "http://localhost:8200/search_multi" \
  -H "Content-Type: application/json" \
  -d '{"query": "data science courses and programs", "collections": ["courses", "programs"], "n_results": 5}'
```

### Get Statistics
```bash
curl http://localhost:8200/stats
```

### Upload Custom Documents (if enabled)
```bash
curl -X POST "http://localhost:8200/upload" -F "files=@your-document.pdf"
```

## 📁 Project Structure

```
course-RAG/
├── src/
│   ├── api.py                    # Main FastAPI application
│   ├── run_api.py               # Server startup script
│   ├── settings.py              # Configuration
│   ├── query_processor.py       # Query processing logic
│   ├── config.json              # Collection configurations
│   ├── documents/               # Document processing
│   │   ├── document_processor.py
│   │   ├── embeddings.py
│   │   └── ingest_documents.py
│   ├── chroma_db/              # Database setup
│   ├── tests/                  # Testing utilities
│   └── UH-Manoa_courses.json   # Example course data
├── nginx.conf                  # Nginx configuration (optional)
├── docker-compose.yml          # Docker compose setup
├── deploy.sh                   # Deployment script
└── README.md                   # This file
```

## 🔧 Development Commands

### Ingest Documents
```bash
cd src
python documents/ingest_documents.py --source UH-Manoa_courses.json
```

### Build Docker Image
```bash
cd src
docker build -t course-rag .
```

### Deploy with Script
```bash
chmod +x deploy.sh
./deploy.sh
```

## 💡 Example Usage

This system demonstrates RAG capabilities using University of Hawaii course data:

1. **Start the server** (production or development)
2. **Search for courses** via the web interface at http://localhost:8200/docs
3. **Ask questions** like:
   - "What computer science courses cover machine learning?"
   - "Show me all courses with prerequisites in calculus"
   - "Find programming courses for beginners"
   - "What are the credit requirements for data science programs?"

## 🔄 Collections

The system supports multiple document collections:

- **courses**: Individual course information (8,297 UH courses)
- **programs**: Academic program details
- **combined_pathways**: Integrated course and program pathways

Each collection can be searched independently or combined for comprehensive results.

## 🆘 Troubleshooting

**Server won't start?**
- Check that port 8200 is available: `lsof -i :8200`
- Verify your Google API key is valid
- For Docker: Check logs with `docker logs course-rag-api`

**No search results?**
- Make sure documents were ingested successfully
- Check if collections exist: `curl http://localhost:8200/stats`
- Verify the database has content (should show document_count > 0)

**Ingestion stuck at 0%?**
- Large datasets may take time due to Google API rate limiting
- Consider running without `--ingest` first, then ingest in smaller batches
- Monitor progress with `docker logs course-rag-api`

**Docker issues?**
- Ensure Docker is running: `docker info`
- Check if image exists: `docker images | grep course-rag`
- Restart container: `docker restart course-rag-api`

**ChromaDB errors?**
- Delete old database: `rm -rf src/chroma_db/data`
- Restart with fresh ingestion: `docker run ... --ingest`

**Need help?**
- Check the full API documentation at http://localhost:8200/docs
- Run the test client: `python src/tests/api_client_example.py`
- Use the web interface at http://localhost:8280

## 🔄 Updates

**Production:** Pull the latest image and restart
```bash
docker pull tabalbar/course-rag:latest
docker stop course-rag-api && docker rm course-rag-api
docker run -d -p 8200:8200 --env-file .env --name course-rag-api tabalbar/course-rag:latest
```

**Development:** Pull latest code and restart
```bash
git pull origin main
cd src
python run_api.py
```

## 🎯 Adapting for Your Data

This system can be easily adapted for other document types:

1. **Replace data source**: Update `config.json` with your document collections
2. **Modify embeddings**: Adjust embedding fields in the configuration
3. **Update preprocessing**: Modify document processing logic in `documents/`
4. **Customize API**: Add domain-specific endpoints in `api.py`

## 📄 License

[Your License Here]
