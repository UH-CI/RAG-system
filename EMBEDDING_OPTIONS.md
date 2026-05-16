# Embedding Model Options for Your RAG System

## Current Resources
- **CPU:** 4 cores
- **RAM:** 15 GB
- **GPU:** None
- **Disk:** 200 GB

---

## Option 1: all-MiniLM-L6-v2 ⭐ **RECOMMENDED**

### Specs
- **Dimensions:** 384
- **Model Size:** ~90 MB
- **RAM Usage:** 500 MB - 1 GB per worker
- **Speed:** Very fast on CPU (2-5x faster than BGE-M3)
- **Quality:** Good for general semantic search

### Resource Impact
- ✅ **4 workers:** ~4-6 GB RAM total (safe)
- ✅ **CPU:** Moderate usage (50-70%)
- ✅ **Fast queries:** 1-3 seconds per query

### Setup Steps

1. **Install dependency:**
```bash
cd /home/exouser/Documents/RAG-system/src
source venv/bin/activate
pip install sentence-transformers
```

2. **Update config.json:**
```bash
cat > config.json << 'EOF'
{
  "collections": ["gateways"],
  "default_collection": "gateways",
  "ingestion_configs": [
    {
      "collection_name": "gateways",
      "original_document_dir": "./documents/storage_documents/gateways",
      "source_file": "chunked_text/gateways/jos_resources_escape.json",
      "contents_to_embed": ["fulltxt", "title"],
      "description": "Papers published in the Science Gateways conference."
    }
  ],
  "search": {
    "default_results": 50,
    "max_results": 300,
    "supported_search_types": ["semantic", "metadata", "both"]
  },
  "api": {
    "title": "Document RAG API",
    "description": "API for managing and searching documents using ChromaDB and RAG",
    "version": "1.0.0"
  },
  "system": {
    "documents_path": "./documents",
    "chroma_db_path": "./chroma_db/data",
    "chroma_collection_name": "default_collection",
    "chroma_distance_function": "cosine",
    "embedding_model": "all-MiniLM-L6-v2",
    "embedding_provider": "sentence-transformers",
    "embedding_dimensions": 384,
    "sambanova_base_url": "https://ai.tejas.tacc.utexas.edu",
    "llm_model": "gemini-1.5-flash",
    "llm_provider": "google",
    "llm_temperature": 0.1,
    "llm_max_tokens": 1000,
    "chunk_size": 500,
    "chunk_overlap": 200,
    "default_k": 10,
    "max_k": 10,
    "batch_size": 10,
    "max_workers": 4,
    "supported_file_types": [".txt", ".pdf", ".json"]
  }
}
EOF
```

3. **Re-embed collection:**
```bash
python3 reembed_gateways_minilm.py
```

4. **Restart Docker:**
```bash
docker-compose restart
```

---

## Option 2: all-mpnet-base-v2 (Better Quality)

### Specs
- **Dimensions:** 768
- **Model Size:** ~420 MB
- **RAM Usage:** 1.5-2.5 GB per worker
- **Speed:** Moderate on CPU (slower than MiniLM)
- **Quality:** Excellent (best in sentence-transformers)

### Resource Impact
- ⚠️ **4 workers:** ~8-12 GB RAM total (tight but workable)
- ⚠️ **CPU:** High usage (70-90%)
- ⚠️ **Slower queries:** 3-6 seconds per query

### Setup
Same as Option 1, but change config.json:
```json
"embedding_model": "all-mpnet-base-v2",
"embedding_dimensions": 768
```

---

## Option 3: SambaNova API (Remote) - NO LOCAL RESOURCES

### Specs
- **Dimensions:** 4096
- **Model:** E5-Mistral-7B-Instruct
- **Local Resources:** None (API call)
- **Speed:** Fast (network dependent)
- **Quality:** Excellent

### Resource Impact
- ✅ **RAM:** Minimal (~100 MB)
- ✅ **CPU:** Minimal (5-10%)
- ✅ **No model loading**
- ⚠️ **Requires API access**

### Setup
Your collection already has 4096-dim embeddings, so just update config.json:
```json
"embedding_model": "E5-Mistral-7B-Instruct",
"embedding_provider": "sambanova",
"embedding_dimensions": 4096
```

---

## Comparison Table

| Model | Dimensions | Size | RAM/Worker | Speed | Quality | Best For |
|-------|-----------|------|------------|-------|---------|----------|
| **MiniLM-L6** | 384 | 90 MB | 0.5-1 GB | ⚡⚡⚡ | ⭐⭐⭐ | **Your setup** |
| **MiniLM-L12** | 384 | 120 MB | 0.8-1.5 GB | ⚡⚡ | ⭐⭐⭐⭐ | Balanced |
| **MPNet-base** | 768 | 420 MB | 1.5-2.5 GB | ⚡ | ⭐⭐⭐⭐⭐ | Quality priority |
| **BGE-M3** | 1024 | 1.2 GB | 4-6 GB | 🐌 | ⭐⭐⭐⭐⭐ | GPU required |
| **SambaNova API** | 4096 | 0 MB | 0.1 GB | ⚡⚡ | ⭐⭐⭐⭐⭐ | API available |

---

## My Recommendation

**Use all-MiniLM-L6-v2** because:
1. ✅ Fits comfortably in your 15 GB RAM with 4 workers
2. ✅ Fast on CPU-only systems
3. ✅ Good quality for most use cases
4. ✅ Open source, no API dependencies
5. ✅ Won't max out CPU/RAM

If you need better quality and can tolerate slower queries, use **all-mpnet-base-v2**.

If you have SambaNova API access and don't want to re-embed, stick with the **SambaNova API**.
