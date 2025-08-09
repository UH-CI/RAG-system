# Financial RAG System

A document search and question-answering system built with ChromaDB and Google AI embeddings. This system demonstrates RAG (Retrieval-Augmented Generation) capabilities using university course data as an example, but can be adapted for any document collection.

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

### 2. Setup chroma_db
download the chroma_db.tar.zst file from https://koacloud.its.hawaii.edu/f/8581276
place file in /src
then run the following command
```bash
# in RAG-system/src
zstd -cd chroma_db.tar.zst | tar -xf -
```

### 3. Start the frontend and backend
```bash
# Return to project root and run deployment with ingestion
cd ..
./GO --init # if your first time running the project, otherwise, omit the "--init" flag
```

**That's it! 🎉** Your API is running at `http://localhost:8200`

---

## 💡 Example Usage

This system demonstrates RAG capabilities using University of Hawaii course data:

1. **Start the server** (production or development)
2. **Search for courses** via the web interface at http://localhost:8200/docs
3. **Ask questions** like:
   - What does the budget for education look like?

---

## 🏛️ Project Architecture

This project is a full-stack application designed to provide a retrieval-augmented generation (RAG) system for financial documents. It is composed of three main components: a React-based frontend, a Python FastAPI backend, and a ChromaDB vector database.

### Frontend

The frontend is a single-page application built with **React** and **TypeScript**. It provides a user-friendly interface for:
- Uploading and managing document collections.
- Interacting with the RAG system through a chat interface.
- Viewing search results and generated responses.

The frontend is located in the `frontend/` directory and is set up to run with a Vite development server.

### Backend

The backend is a **Python** application built with the **FastAPI** framework. It serves as the core of the RAG system and is responsible for:
- **API Server**: Exposing a RESTful API for the frontend to consume.
- **Document Processing**: Handling the ingestion, text extraction, chunking, and embedding of documents.
- **RAG Pipeline**: Orchestrating the retrieval of relevant document chunks from ChromaDB and generating responses using a large language model (LLM) via Google's Generative AI.

The backend code is located in the `src/` directory and is containerized with Docker.

### Database

The vector database is powered by **ChromaDB**. It is responsible for:
- Storing the vector embeddings of the document chunks.
- Providing efficient similarity search to find the most relevant document chunks for a given query.

ChromaDB is run as a service within the Docker Compose setup, and its data is persisted using a Docker volume.

### How It Works

1.  **Document Ingestion**: A user uploads financial documents (e.g., PDFs) through the frontend.
2.  **Text Extraction & Chunking**: The backend extracts the text from these documents and splits it into smaller, manageable chunks.
3.  **Embedding & Storage**: Each chunk is then converted into a vector embedding using Google's Generative AI and stored in ChromaDB.
4.  **User Query**: A user asks a question through the chat interface.
5.  **Retrieval**: The backend takes the user's query, converts it into an embedding, and uses it to search ChromaDB for the most relevant document chunks.
6.  **Augmentation & Generation**: The retrieved chunks are then passed to a large language model, along with the original query, to generate a comprehensive and contextually-aware answer.
7.  **Response**: The final answer is streamed back to the user through the frontend.

## 📄 License

[Your License Here]
