# HOA Bot: Complete Implementation Plan
## From Docker Migration to Benchmarks & Evals

**Status:** Ready to execute  
**Total Time:** ~40-50 hours across 2-3 weeks  
**Approach:** Iterative (complete one phase before next)  
**Last Updated:** 2026-08-22

---

## 📋 **PHASE OVERVIEW**

```
Phase 1: Infrastructure (Docker + Tesseract)
   ↓ (2 days)
Phase 2: Incremental Chunking & Embedding
   ↓ (3 days)
Phase 3: Dual Storage (ChromaDB + Pinecone)
   ↓ (2 days)
Phase 4: Sample Data Setup
   ↓ (1 day)
Phase 5: UI Toggles & Settings
   ↓ (2 days)
Phase 6: Test Suite
   ↓ (2 days)
Phase 7: Benchmarking Framework
   ↓ (2 days)
Phase 8: Run Benchmarks
   ↓ (2 days)
Phase 9: Analysis & Report
   ↓ (1 day)
Phase 10: Documentation & Polish
   ↓ (1 day)
```

---

# PHASE 1: Infrastructure Migration (Docker + Tesseract)
**Time:** 2 days | **Status:** Not started

## Goal
Migrate from Alpine to Slim Linux, add OCR capabilities, verify all dependencies work.

### Step 1.1: Update Consumer Dockerfile
**Time:** 30 min | **Checkpoint:** Build succeeds

- [ ] Open `Consumer_dockerfile`
- [ ] Change base: `python:3.11-alpine` → `python:3.11-slim`
- [ ] Add system dependencies:
  - [ ] `apt-get update && apt-get install -y tesseract-ocr libtesseract-dev`
- [ ] Add Python packages to requirements.txt:
  - [ ] `pytesseract==0.3.10`
  - [ ] `pdf2image==1.16.3`
  - [ ] `Pillow==10.0.0`
- [ ] Build image: `docker build -f Consumer_dockerfile -t consumer:latest .`
- [ ] Verify build succeeds (no errors)

**Validation:**
```
✅ Docker image built successfully
✅ Image size < 500MB
✅ tesseract-ocr installed (can check: docker run consumer:latest tesseract --version)
```

### Step 1.2: Update Web UI Dockerfile
**Time:** 30 min | **Checkpoint:** Build succeeds

- [ ] Open `Web_UI_dockerfile`
- [ ] Change base: `python:3.11-alpine` → `python:3.11-slim`
- [ ] Keep same Python dependencies (Flask, pika, etc already in requirements.txt)
- [ ] Build image: `docker build -f Web_UI_dockerfile -t web-ui:latest .`
- [ ] Verify build succeeds

**Validation:**
```
✅ Docker image built successfully
✅ Image size < 300MB
```

### Step 1.3: Update Producer Dockerfile (if keeping it)
**Time:** 30 min | **Checkpoint:** Build succeeds

- [ ] Open `Producer_dockerfile`
- [ ] Change base: `python:3.11-alpine` → `python:3.11-slim`
- [ ] Build image: `docker build -f Producer_dockerfile -t producer:latest .`
- [ ] Verify build succeeds

**Validation:**
```
✅ Docker image built successfully
```

### Step 1.4: Import Updated Images to k3d
**Time:** 30 min | **Checkpoint:** All images available in cluster

- [ ] Import consumer: `k3d image import consumer:latest -c HOA-Bot`
- [ ] Import web-ui: `k3d image import web-ui:latest -c HOA-Bot`
- [ ] Import producer (optional): `k3d image import producer:latest -c HOA-Bot`
- [ ] Verify imports: `k3d image list -c HOA-Bot | grep -E 'consumer|web-ui|producer'`

**Validation:**
```
✅ All 3 images listed
✅ Images ready for deployment
```

### Step 1.5: Redeploy to Kubernetes
**Time:** 30 min | **Checkpoint:** All pods running

- [ ] Delete old deployments: `kubectl delete deployment web-ui consumer producer -n hoa-pipeline`
- [ ] Verify deleted: `kubectl get pods -n hoa-pipeline` (should only see RabbitMQ)
- [ ] Redeploy: `kubectl apply -f web-ui-deployment.yaml consumer-deployment.yaml`
- [ ] Wait for pods to start: `kubectl -n hoa-pipeline get pods -w`

**Validation:**
```
✅ web-ui pod: Running
✅ consumer pod: Running
✅ All pods: READY 1/1
```

### Step 1.6: Verify Tesseract Works
**Time:** 15 min | **Checkpoint:** OCR functional

- [ ] SSH into consumer pod: `kubectl -n hoa-pipeline exec -it deployment/consumer -- bash`
- [ ] Test tesseract: `tesseract --version`
- [ ] Create test PDF (mock): `python -c "print('test')" > /tmp/test.txt`
- [ ] Exit pod

**Validation:**
```
✅ tesseract-ocr version printed
✅ No errors
```

**End of Phase 1:** Docker infrastructure ready for OCR  
**Commit to Git:** "Migrate Docker images from Alpine to Slim, add tesseract-ocr"

---

# PHASE 2: Incremental Chunking & Embedding
**Time:** 3 days | **Status:** Not started

## Goal
Integrate chunking and embedding directly into consumer, handle PDFs incrementally without batch processing.

### Step 2.1: Prepare Sample PDF Corpus
**Time:** 1 day | **Checkpoint:** 5 sample PDFs ready

- [ ] Create `/docs/samples/` folder
- [ ] Generate 5 synthetic PDFs (NOT real HOA docs):
  - [ ] Document 1: "Sample_Governing_Rules.pdf" (synthetic CC&Rs-like text)
  - [ ] Document 2: "Sample_Financial_Report.pdf" (synthetic budget-like)
  - [ ] Document 3: "Sample_Inspection.pdf" (synthetic inspection-like)
  - [ ] Document 4: "Sample_Disclosure.pdf" (synthetic disclosure-like)
  - [ ] Document 5: "Sample_Meeting_Minutes.pdf" (synthetic minutes-like)
- [ ] Each PDF should be ~10-20 pages of coherent text
- [ ] Use Lorem ipsum or public domain text as base
- [ ] Goal: Realistic structure, not real HOA content

**Tools to use:**
- Python: `reportlab` or `fpdf2` to generate PDFs programmatically
- OR: Copy-paste public domain text into Google Docs → Export as PDF

**Validation:**
```
✅ 5 PDFs created
✅ Each 5-50KB size
✅ All readable
```

### Step 2.2: Prepare chunks.json Structure
**Time:** 4 hours | **Checkpoint:** Empty chunks.json ready

- [ ] Create empty file: `chunks.json` in project root
- [ ] Initialize as: `[]` (empty array)
- [ ] Create metadata structure documentation:
  ```
  Each chunk will have:
  - chunk_id: "DocName:chunk_N"
  - source: "DocName.pdf"
  - doc_id: UUID from message
  - text: actual chunk text
  - doc_type: governing/financial/advisory/report
  - sections: [list of section numbers]
  - page_start, page_end: page numbers
  - char_start, char_end: positions
  - uploaded_at: timestamp
  - embedding: [384 float values] - ADDED LATER
  ```
- [ ] Add chunks.json to .gitignore (will grow large)

**Validation:**
```
✅ chunks.json exists and is empty []
✅ .gitignore updated
```

### Step 2.3: Update Requirements.txt with Embedding Dependencies
**Time:** 30 min | **Checkpoint:** All packages installable

- [ ] Add to requirements.txt:
  - [ ] `sentence-transformers==2.2.2` (BGE embeddings)
  - [ ] `torch==2.0.1` (required by sentence-transformers)
  - [ ] `numpy==1.24.3` (data handling)
  - [ ] `pdf2image==1.16.3` (text extraction)
  - [ ] `pytesseract==0.3.10` (OCR)
- [ ] Verify no conflicts: Check if all versions compatible
- [ ] Test install locally: `pip install -r requirements.txt` in venv

**Validation:**
```
✅ All packages install without error
✅ No version conflicts
✅ sentence-transformers loads BGE model
```

### Step 2.4: Design Consumer Enhancement (Document in comments)
**Time:** 1 day | **Checkpoint:** Flow documented

In a new file `consumer_enhancement_flow.txt` (for reference, not code):

Document the flow:
```
Current consumer.py flow:
  Read message → Extract text → Delete file → Acknowledge

New flow should be:
  Read message
    ↓
  Extract text from PDF (with OCR fallback)
    ↓
  CHUNK the text (use chunk.py logic)
    ↓
  For each chunk created:
    ├─ EMBED with BGE-small
    ├─ Append to chunks.json
    ├─ Store in ChromaDB (local)
    ├─ Store in Pinecone (if enabled)
    └─ Log progress
    ↓
  Delete file from PVC
    ↓
  Acknowledge to RabbitMQ
```

Key decisions to document:
- How to handle OCR failures? (Fallback to text extraction)
- How to handle chunking failures? (Log, continue, acknowledge anyway)
- How to handle embedding failures? (Retry? Log? Continue?)
- Batch size for embeddings? (Process chunks as they come, not in batches)

**Validation:**
```
✅ Flow documented
✅ Error handling strategy decided
✅ Edge cases identified
```

### Step 2.5: Audit Current chunk.py for Reusability
**Time:** 4 hours | **Checkpoint:** Reusable functions identified

- [ ] Read current chunk.py
- [ ] Identify reusable functions:
  - [ ] `classify_doc_type(source: str)`
  - [ ] `find_sections_in_text(text: str)`
  - [ ] `chunks_from_paragraphs(paragraphs: list)`
  - [ ] `chunk_document(...)`
- [ ] For each function, note:
  - [ ] Input parameters
  - [ ] Output structure
  - [ ] Dependencies (imports)
  - [ ] Whether it can be imported into consumer.py
- [ ] Create a `chunking_utils.py` that exports core functions
  - [ ] This allows reuse without copy-pasting code
  - [ ] Same logic, both in batch (chunk.py) and incremental (consumer)

**Validation:**
```
✅ Reusable functions identified
✅ chunking_utils.py can be imported cleanly
✅ No circular dependencies
```

**End of Phase 2:** Consumer ready to do chunking + embedding incrementally  
**Checkpoint:** Sample PDFs, chunks.json structure, utils ready  
**Commit to Git:** "Add sample data, prepare incremental chunking infrastructure"

---

# PHASE 3: Dual Storage (ChromaDB + Pinecone)
**Time:** 2 days | **Status:** Not started

## Goal
Abstract vector DB layer so consumer can write to both simultaneously.

### Step 3.1: Create Vector DB Abstraction (Document structure)
**Time:** 1 day | **Checkpoint:** Architecture documented

Create a file `vector_db_architecture.md` (documentation, not code yet):

Document the abstraction:
```
Abstract Interface (what any vector DB must support):
├─ add_embeddings(chunk_id, vector, metadata)
│  └─ Write a single embedding to the DB
├─ search(query_vector, k=8)
│  └─ Search for top-k similar vectors
├─ delete_all()
│  └─ Clear the database
└─ health_check()
   └─ Verify DB is responsive

ChromaDB Implementation:
├─ Uses: .chroma_data/ folder (local files)
├─ Interface:
│  ├─ add: Uses collection.upsert()
│  ├─ search: Uses collection.query()
│  └─ delete: Uses client.delete_collection()

Pinecone Implementation:
├─ Uses: Pinecone API (cloud)
├─ Interface:
│  ├─ add: Uses index.upsert()
│  ├─ search: Uses index.query()
│  └─ delete: Uses index.delete()

Configuration:
├─ Toggle in config which to use (or both)
├─ Both get same data simultaneously
└─ At query time, choose which to search
```

**Validation:**
```
✅ Abstract interface defined
✅ Both implementations mapped
✅ No conflicts between interfaces
```

### Step 3.2: Prepare Pinecone Setup (Document requirements)
**Time:** 1 day | **Checkpoint:** Pinecone account ready

- [ ] Go to pinecone.io
- [ ] Create free account (if not already done)
- [ ] Create index:
  - [ ] Name: `hoa-documents`
  - [ ] Dimension: `384` (matches BGE-small output)
  - [ ] Metric: `cosine`
  - [ ] Environment: `gcp-starter` (free tier)
- [ ] Copy API key
- [ ] Store in environment variable: `PINECONE_API_KEY`
- [ ] Document in a file `pinecone_setup.txt`:
  ```
  Pinecone Index Created:
  - Name: hoa-documents
  - Dimension: 384
  - Metric: cosine
  - Free tier: supports up to 1M vectors
  - Cost: $0 for free tier
  - API Key stored in: $PINECONE_API_KEY
  ```

**Validation:**
```
✅ Pinecone account created
✅ Index created
✅ API key accessible
✅ Can connect via Python SDK
```

### Step 3.3: Document Config Structure
**Time:** 2 hours | **Checkpoint:** Config file structure finalized

Create a file `config_structure.md` (documentation):

Document the configuration:
```
config.py should support:

Vector Database Selection:
├─ vector_db_backend: "local" | "pinecone" | "both"
├─ if both:
│  ├─ Write to ChromaDB
│  ├─ Write to Pinecone
│  └─ At query time, choose which to search

Memory Backend Selection:
├─ memory_backend: "simple" | "mem0"

RAG Framework Selection:
├─ rag_framework: "langgraph" | "llamaindex"

Retrieval Mode Selection:
├─ retrieval_mode: "fast" | "thinking"

Pinecone Config (if needed):
├─ pinecone_api_key: from environment
├─ pinecone_index_name: "hoa-documents"

Embedding Config:
├─ embedding_model: "BAAI/bge-small-en-v1.5"
├─ embedding_dimension: 384
└─ embedding_batch_size: 32

Chunking Config:
├─ chunk_size: 3200
├─ overlap: 1
└─ min_chunk_size: 100

Application Config:
├─ app_name: "HOA Bot"
├─ log_level: "INFO"
└─ debug: false
```

**Validation:**
```
✅ Config structure finalized
✅ All options documented
✅ Defaults reasonable
```

**End of Phase 3:** Dual storage architecture designed  
**Checkpoint:** Pinecone ready, config structure finalized  
**Commit to Git:** "Add architecture docs for dual vector DB storage and config structure"

---

# PHASE 4: Sample Data Setup
**Time:** 1 day | **Status:** Not started

## Goal
Prepare sample PDFs for testing the full pipeline end-to-end.

### Step 4.1: Create Sample PDF Generation Script
**Time:** 2 hours | **Checkpoint:** Script exists (not run yet)

Create a file `generate_sample_pdfs.py` (reference, document the approach):

Document what this script would do:
```
Purpose: Generate 5 realistic sample PDFs for testing

Approach:
├─ Use reportlab or fpdf2 library to create PDFs programmatically
├─ For each PDF:
│  ├─ Add title
│  ├─ Add multiple sections with varying content
│  ├─ Include some structure (headings, paragraphs)
│  ├─ Make ~10-20 pages
│  └─ Save to /docs/samples/
│
├─ PDF 1: Governing Document
│  ├─ Title: "Sample_Governing_Rules.pdf"
│  ├─ Content: Sections about rules, restrictions, procedures
│  └─ Expected chunks: ~100-150
│
├─ PDF 2: Financial Report
│  ├─ Title: "Sample_Financial_Report.pdf"
│  ├─ Content: Budget information, assessments, fees
│  └─ Expected chunks: ~80-120
│
├─ PDF 3: Inspection Report
│  ├─ Title: "Sample_Inspection_Report.pdf"
│  ├─ Content: Property inspection findings, conditions
│  └─ Expected chunks: ~60-100
│
├─ PDF 4: Disclosure Document
│  ├─ Title: "Sample_Disclosure_Document.pdf"
│  ├─ Content: Legal disclosures, advisories
│  └─ Expected chunks: ~70-110
│
└─ PDF 5: Meeting Minutes
   ├─ Title: "Sample_Meeting_Minutes.pdf"
   ├─ Content: Board meeting notes, decisions, action items
   └─ Expected chunks: ~50-80

Total expected chunks from 5 PDFs: ~360-560 chunks
```

**Validation:**
```
✅ Script documented
✅ All 5 PDFs planned
✅ Expected chunk counts reasonable
```

### Step 4.2: Generate Sample PDFs
**Time:** 2 hours | **Checkpoint:** 5 PDFs exist

- [ ] Create `/docs/samples/` folder if not exists
- [ ] Run sample PDF generation (manually or script)
  - [ ] Can use: Python PDF library (reportlab, fpdf2)
  - [ ] OR: Create in Google Docs, export to PDF
  - [ ] OR: Copy from public domain sources
- [ ] Verify 5 PDFs created
- [ ] Verify each is readable (open in browser)
- [ ] Document the content briefly:
  ```
  samples/README.md:
  - Sample_Governing_Rules.pdf: Lorem ipsum + sections about rules
  - Sample_Financial_Report.pdf: Lorem ipsum + sections about budget
  - etc...
  ```

**Validation:**
```
✅ 5 PDFs created in /docs/samples/
✅ Each 5-50KB
✅ All readable
✅ Total: ~150-250KB
```

### Step 4.3: Create Ground Truth Queries & Labels
**Time:** 3 hours | **Checkpoint:** 30 queries labeled

Create a file `benchmark_queries.json` (JSON file with structure):

Document the query structure:
```
[
  {
    "id": 1,
    "category": "governing",
    "query": "What are the main rules and restrictions?",
    "expected_chunks": [
      "Sample_Governing_Rules:chunk_0",
      "Sample_Governing_Rules:chunk_5",
      "Sample_Governing_Rules:chunk_12"
    ],
    "expected_answer_summary": "Rules cover..."
  },
  {
    "id": 2,
    "category": "financial",
    "query": "What is the annual assessment?",
    "expected_chunks": [...],
    "expected_answer_summary": "..."
  },
  ...30 total queries
]
```

Split queries by:
- 5 governing questions
- 5 financial questions
- 5 inspection questions
- 5 disclosure questions
- 5 edge case / complex questions

**Validation:**
```
✅ 30 queries created
✅ Each has expected chunks labeled
✅ Each has expected answer summary
✅ Covers all 5 documents
✅ Mix of easy and hard queries
```

**End of Phase 4:** Sample data ready for testing  
**Checkpoint:** 5 sample PDFs + 30 benchmark queries  
**Commit to Git:** "Add sample PDF corpus and benchmark query suite"

---

# PHASE 5: UI Toggles & Settings
**Time:** 2 days | **Status:** Not started

## Goal
Add UI controls for switching backends without code changes.

### Step 5.1: Design UI Layout (Document structure)
**Time:** 1 day | **Checkpoint:** Layout documented

Create a file `ui_settings_design.md`:

Document the UI:
```
Current UI: Single input box + Send button

New UI Structure:
├─ Left Sidebar (Settings Panel)
│  ├─ Section: 📦 Vector Database
│  │  ├─ Radio: Local (ChromaDB) [selected]
│  │  ├─ Radio: Cloud (Pinecone)
│  │  └─ Status badge showing active DB
│  │
│  ├─ Section: 🧠 Memory System
│  │  ├─ Radio: Simple Session Only [selected]
│  │  ├─ Radio: Intelligent (Mem0)
│  │  └─ Status badge showing memory type
│  │
│  ├─ Section: 🔄 RAG Framework
│  │  ├─ Radio: LangGraph [selected]
│  │  ├─ Radio: LlamaIndex
│  │  └─ Status badge showing framework
│  │
│  └─ Section: ⚡ Retrieval Mode
│     ├─ Radio: Fast (2-5s) [selected]
│     ├─ Radio: Thinking (10-30s)
│     └─ Status badge showing mode
│
├─ Main Chat Area
│  ├─ Header showing current config:
│  │  "Local • Simple • LangGraph • Fast"
│  │
│  ├─ Chat messages (existing)
│  │
│  ├─ Input box (existing)
│  │
│  └─ Send button (existing)
│
└─ Color scheme:
   ├─ Sidebar: White background
   ├─ Active setting: Blue highlight
   ├─ Status badges: Green (active) / Gray (inactive)
   └─ Main area: Light gradient background
```

**Validation:**
```
✅ Layout documented
✅ All toggles defined
✅ No conflicts between settings
✅ Visual hierarchy clear
```

### Step 5.2: Design API Endpoints (Document)
**Time:** 4 hours | **Checkpoint:** API spec documented

Create a file `api_endpoints.md`:

Document the API:
```
Current endpoints:
├─ POST /ask
│  ├─ Request: {"question": "..."}
│  └─ Response: {"answer": "...", "sources": [...]}

New endpoints needed:

1. GET /config
   Purpose: Get current configuration
   Response: {
     "vector_db": "local" | "pinecone",
     "memory_backend": "simple" | "mem0",
     "rag_framework": "langgraph" | "llamaindex",
     "retrieval_mode": "fast" | "thinking",
     "embedding_model": "BAAI/bge-small-en-v1.5"
   }

2. POST /config
   Purpose: Update configuration
   Request: {
     "vector_db": "local",
     "memory_backend": "simple",
     "rag_framework": "langgraph",
     "retrieval_mode": "fast"
   }
   Response: {
     "status": "updated",
     "config": {...}
   }

3. POST /ask (enhanced)
   Request: {
     "question": "...",
     "user_id": "optional-user-id",
     "retrieval_mode": "fast" (overrides config for this request)
   }
   Response: {
     "answer": "...",
     "sources": [...],
     "config_used": {...},
     "metadata": {
       "latency_ms": 4200,
       "chunks_searched": 8,
       "chunks_relevant": 6
     }
   }

4. GET /health
   Purpose: Check service health
   Response: {
     "status": "healthy",
     "vector_db_status": "connected",
     "config": {...}
   }
```

**Validation:**
```
✅ All endpoints documented
✅ Request/response formats clear
✅ Error cases considered
✅ No conflicts between endpoints
```

### Step 5.3: Document Frontend Changes Needed
**Time:** 2 hours | **Checkpoint:** Changes listed

Create a file `ui_implementation_checklist.md`:

List all changes needed (don't code yet):
```
HTML Changes:
├─ Add sidebar div with settings
├─ Add radio buttons for each toggle
├─ Add status badges
├─ Add config display in header
└─ Reorganize layout with grid

JavaScript Changes:
├─ Add function: updateConfig() - calls POST /config
├─ Add function: getConfig() - calls GET /config
├─ Add function: loadConfigUI() - populates UI from config
├─ Add event listeners for radio button changes
├─ Update askQuestion() to accept retrieval_mode parameter
├─ Update message display to show metadata (latency, etc)
└─ Add error handling for config changes

CSS Changes:
├─ Add sidebar styling (width, background, padding)
├─ Add radio button styling
├─ Add status badge styling
├─ Update main chat area to account for sidebar
├─ Add transitions/animations for config changes
└─ Ensure responsive (sidebar collapses on mobile)
```

**Validation:**
```
✅ All changes catalogued
✅ Frontend + backend aligned
✅ No missing pieces
```

**End of Phase 5:** UI settings architecture designed  
**Checkpoint:** Layouts, APIs, and implementation plan documented  
**Commit to Git:** "Document UI settings design and API endpoints"

---

# PHASE 6: Test Suite
**Time:** 2 days | **Status:** Not started

## Goal
Create automated tests to verify chunking, embedding, storage, and retrieval work correctly.

### Step 6.1: Design Test Structure
**Time:** 1 day | **Checkpoint:** Test categories defined

Create a file `test_suite_plan.md`:

Document test categories:
```
Test Suite Structure:

1. UNIT TESTS (test individual components)
   Location: tests/unit/
   
   ├─ test_chunking.py
   │  ├─ Test: chunk_document() produces correct # of chunks
   │  ├─ Test: chunk_sizes are within bounds (1500-3500 chars)
   │  ├─ Test: overlap works (chunks share content)
   │  ├─ Test: section extraction works
   │  └─ Test: page mapping correct
   │
   ├─ test_embedding.py
   │  ├─ Test: BGE model loads
   │  ├─ Test: embedding dimension is 384
   │  ├─ Test: query embedding adds prefix
   │  ├─ Test: batch embedding works
   │  └─ Test: embeddings are normalized
   │
   ├─ test_vector_db.py
   │  ├─ Test: ChromaDB add/search works
   │  ├─ Test: Pinecone add/search works
   │  ├─ Test: Both DBs return same results
   │  ├─ Test: Search returns top-k
   │  └─ Test: Metadata preserved
   │
   └─ test_rag.py
      ├─ Test: retrieval returns chunks
      ├─ Test: grading identifies relevant chunks
      ├─ Test: rewriting reformulates query
      └─ Test: generation produces answer

2. INTEGRATION TESTS (test workflows)
   Location: tests/integration/
   
   ├─ test_pdf_to_chunks.py
   │  ├─ Test: Load PDF → extract text → chunk → embed
   │  ├─ Test: End-to-end produces valid chunks.json
   │  └─ Test: All chunks can be embedded
   │
   ├─ test_dual_storage.py
   │  ├─ Test: Write to both ChromaDB and Pinecone
   │  ├─ Test: Search both, results identical
   │  └─ Test: Toggle between them
   │
   ├─ test_consumer_pipeline.py
   │  ├─ Test: Message received → chunked → embedded → stored
   │  ├─ Test: Concurrent processing (3 messages)
   │  ├─ Test: Error recovery (retry logic)
   │  └─ Test: File deletion after processing
   │
   └─ test_query_pipeline.py
      ├─ Test: Query → embed → search → retrieve → answer
      ├─ Test: Fast mode (2-5s)
      ├─ Test: Thinking mode with rewriting
      └─ Test: Citations present in answer

3. BENCHMARK TESTS (performance)
   Location: tests/benchmarks/
   
   ├─ benchmark_latency.py
   │  ├─ Measure: Search latency (local vs cloud)
   │  ├─ Measure: Embedding time
   │  ├─ Measure: End-to-end latency
   │  └─ Output: JSON with timings
   │
   ├─ benchmark_accuracy.py
   │  ├─ Run: 30 test queries
   │  ├─ Measure: Precision@8, Recall@8, NDCG@8
   │  ├─ Compare: Local vs Pinecone
   │  └─ Output: JSON with metrics
   │
   └─ benchmark_throughput.py
      ├─ Measure: Queries/second (local vs cloud)
      ├─ Measure: Documents processed/second
      └─ Output: JSON with throughput

4. EVALUATION TESTS (quality)
   Location: tests/evals/
   
   ├─ eval_retrieval.py
   │  ├─ For each of 30 queries:
   │  │  ├─ Get top-8 results
   │  │  ├─ Compare to ground truth
   │  │  ├─ Calculate accuracy metrics
   │  │  └─ Log misses
   │  └─ Output: eval_results.json with per-query metrics
   │
   └─ eval_answer_quality.py
      ├─ For each of 30 queries:
      │  ├─ Generate answer
      │  ├─ Check citations present
      │  ├─ Check answer completeness
      │  └─ Manual scoring (0-5 scale)
      └─ Output: eval_answer_results.json
```

**Validation:**
```
✅ Test categories clear
✅ Each test has clear purpose
✅ No overlap between tests
✅ Benchmark test outputs defined
```

### Step 6.2: Document Test Data Requirements
**Time:** 2 hours | **Checkpoint:** Test data strategy defined

Create a file `test_data_strategy.md`:

Document test data:
```
Test Data Locations:

1. Sample PDFs (for integration tests)
   Location: /docs/samples/
   Count: 5 PDFs
   Size: ~200KB total
   Purpose: Test full pipeline (PDF → chunks → embed → store)

2. Sample Chunks (for unit tests)
   Location: tests/fixtures/sample_chunks.json
   Content: 20 pre-created chunks with known embeddings
   Purpose: Test embedding/storage without chunking logic
   Format: [{"chunk_id": "...", "text": "...", "embedding": [...]}, ...]

3. Ground Truth Queries (for evaluation)
   Location: tests/fixtures/benchmark_queries.json
   Count: 30 queries
   Format: [{"id": 1, "query": "...", "expected_chunks": [...], ...}, ...]
   Purpose: Evaluate retrieval accuracy

4. Expected Embeddings (for verification)
   Location: tests/fixtures/expected_embeddings.json
   Content: Pre-computed BGE embeddings for sample chunks
   Purpose: Verify embedding consistency

Test Data Lifecycle:
├─ Setup: Load fixtures before each test
├─ Isolation: Each test gets fresh copy
├─ Teardown: Clean up after each test
└─ Cache: Pre-computed embeddings cached for speed
```

**Validation:**
```
✅ Test data locations defined
✅ Fixtures prepared
✅ Lifecycle clear
```

### Step 6.3: Create Test Execution Plan
**Time:** 2 hours | **Checkpoint:** Execution order defined

Create a file `test_execution_plan.md`:

Document test order:
```
Test Execution Order:

Phase 1: Unit Tests (dependencies for others)
├─ Run: pytest tests/unit/ -v
├─ Expected: All pass
├─ Time: ~2 minutes
├─ If fails: Fix code immediately
└─ Must pass before moving to Phase 2

Phase 2: Integration Tests (build on unit tests)
├─ Run: pytest tests/integration/ -v
├─ Expected: All pass
├─ Time: ~5 minutes
├─ If fails: Debug integration, check unit tests passed
└─ Must pass before moving to Phase 3

Phase 3: Benchmark Tests (collect performance data)
├─ Run: pytest tests/benchmarks/ -v --benchmark-only
├─ Expected: Generate benchmark_results.json
├─ Time: ~10 minutes
├─ If fails: Check system resources, retry
└─ Continue to Phase 4 regardless (benchmarks are informational)

Phase 4: Evaluation Tests (compare local vs cloud)
├─ Run: pytest tests/evals/ -v
├─ Expected: Generate eval_results.json + eval_answer_results.json
├─ Time: ~15 minutes
├─ If fails: Check query format, ground truth labels
└─ Result: Accuracy comparison ready

Total Test Time: ~30-40 minutes
Test Coverage Target: 80%+ of code paths
```

**Validation:**
```
✅ Execution order clear
✅ Dependencies respected
✅ Time estimates reasonable
```

**End of Phase 6:** Test suite architecture designed  
**Checkpoint:** Test categories, data, and execution plan documented  
**Commit to Git:** "Document comprehensive test suite plan"

---

# PHASE 7: Benchmarking Framework
**Time:** 2 days | **Status:** Not started

## Goal
Create infrastructure to capture and compare local vs cloud performance.

### Step 7.1: Design Benchmark Output Format
**Time:** 1 day | **Checkpoint:** Output schemas defined

Create a file `benchmark_output_schemas.md`:

Document all output JSON structures:
```
1. benchmark_results.json
   Purpose: Raw latency and throughput measurements
   Schema:
   {
     "timestamp": "2026-08-22T10:30:00Z",
     "environment": "local-dev",
     "results": {
       "search_latency": {
         "local": {
           "mean_ms": 4.2,
           "p50_ms": 3.8,
           "p95_ms": 6.1,
           "p99_ms": 8.4
         },
         "pinecone": {
           "mean_ms": 87.3,
           "p50_ms": 82.1,
           "p95_ms": 120.5,
           "p99_ms": 180.2
         }
       },
       "embedding_latency": {
         "mean_ms": 45.2,
         "p95_ms": 52.3
       },
       "throughput_queries_per_sec": {
         "local": 2400,
         "pinecone": 11.5
       }
     }
   }

2. eval_results.json
   Purpose: Retrieval accuracy metrics
   Schema:
   {
     "timestamp": "2026-08-22T10:30:00Z",
     "total_queries": 30,
     "results_by_backend": {
       "local": {
         "overall": {
           "precision_8": 0.753,
           "recall_8": 0.621,
           "ndcg_8": 0.782,
           "mrr": 0.512
         },
         "by_category": {
           "governing": { "precision": 0.80, ... },
           "financial": { "precision": 0.75, ... },
           ...
         },
         "per_query": [
           {
             "query_id": 1,
             "query": "Can I rent my unit?",
             "correct_chunks": 4,
             "retrieved_chunks": 8,
             "precision": 0.5,
             "mrr": 0.25
           },
           ...
         ]
       },
       "pinecone": { ... same structure ... }
     }
   }

3. eval_answer_results.json
   Purpose: Answer quality evaluation
   Schema:
   {
     "timestamp": "2026-08-22T10:30:00Z",
     "total_queries": 30,
     "results": [
       {
         "query_id": 1,
         "query": "Can I rent my unit?",
         "answer_generated": "...",
         "has_citations": true,
         "citation_accuracy": 1.0,
         "completeness_score": 0-5,
         "correctness_score": 0-5,
         "notes": "..."
       },
       ...
     ]
   }

4. comparison_report.json
   Purpose: Final comparison summary
   Schema:
   {
     "timestamp": "2026-08-22T10:30:00Z",
     "summary": {
       "latency_winner": "local",
       "accuracy_winner": "pinecone",
       "overall_recommendation": "local for MVP, pinecone for scale",
       "latency_difference": "20x faster (local)"
     },
     "metrics": {
       "retrieval_accuracy": { "local": 75.3, "pinecone": 76.1 },
       "search_latency": { "local": 4.2, "pinecone": 87.3 },
       "cost_per_month": { "local": 0, "pinecone": 1.20 }
     }
   }
```

**Validation:**
```
✅ All output formats defined
✅ JSON schemas valid
✅ Can be programmatically compared
```

### Step 7.2: Design Comparison Analysis Functions
**Time:** 1 day | **Checkpoint:** Analysis functions documented

Create a file `analysis_functions_plan.md`:

Document what needs to be calculated:
```
Functions needed (don't code yet, just design):

1. calculate_retrieval_metrics(queries, results, ground_truth)
   Input:
   - queries: list of test queries
   - results: retrieved chunks per query
   - ground_truth: labeled correct chunks per query
   
   Output:
   - precision@8, recall@8, ndcg@8, mrr for each query
   - Aggregated metrics overall and by category
   
   Logic needed:
   └─ For each query:
      ├─ Get top-8 results
      ├─ Compare to ground truth
      ├─ Calculate position-based metrics
      └─ Store per-query and aggregate

2. calculate_latency_metrics(timings)
   Input: list of measured latencies (in ms)
   
   Output:
   - mean, median, p95, p99
   - std dev
   - min, max
   
   Logic needed:
   └─ Sort timings
      ├─ Calculate percentiles
      ├─ Calculate mean/std dev
      └─ Format for output

3. compare_backends(local_results, pinecone_results)
   Input: Results from both backends
   
   Output:
   - Which is faster
   - Which is more accurate
   - Trade-offs explained
   - Recommendation
   
   Logic needed:
   └─ For each metric:
      ├─ Calculate difference (absolute + %)
      ├─ Determine winner
      └─ Note significance

4. generate_comparison_report(all_results)
   Input: All benchmarks, evals, analysis
   
   Output: Human-readable markdown report
   
   Logic needed:
   └─ Structure:
      ├─ Executive summary
      ├─ Detailed metrics tables
      ├─ Charts/visualizations description
      ├─ Analysis per metric
      ├─ Trade-offs
      └─ Recommendations
```

**Validation:**
```
✅ Analysis functions defined
✅ Inputs/outputs clear
✅ Logic steps documented
```

**End of Phase 7:** Benchmarking infrastructure designed  
**Checkpoint:** Output formats and analysis functions documented  
**Commit to Git:** "Document benchmark output schemas and analysis functions"

---

# PHASE 8: Run Benchmarks
**Time:** 2 days | **Status:** Not started

## Goal
Actually execute benchmarks on both local and cloud backends.

### Step 8.1: Prepare Local ChromaDB
**Time:** 2 hours | **Checkpoint:** ChromaDB populated

- [ ] Verify ChromaDB installed locally
- [ ] Clear existing .chroma_data/ folder
- [ ] Upload sample PDFs (from Phase 4) to web UI
- [ ] Watch consumer process them incrementally
- [ ] Verify 5 PDFs chunked and embedded
- [ ] Confirm chunks.json populated with ~360-560 chunks
- [ ] Verify ChromaDB has same chunks indexed

**Validation:**
```
✅ ChromaDB populated with sample data
✅ chunks.json contains all chunks
✅ All chunks have embeddings
✅ Ready for search tests
```

### Step 8.2: Prepare Pinecone
**Time:** 2 hours | **Checkpoint:** Pinecone populated

- [ ] Verify Pinecone API key configured
- [ ] Create empty index if not exists
- [ ] Upload same sample PDFs to web UI (Pinecone enabled)
- [ ] Watch consumer process them to Pinecone
- [ ] Verify all chunks indexed in Pinecone
- [ ] Test search works: `index.query(test_vector)`

**Validation:**
```
✅ Pinecone index populated
✅ All chunks indexed (~360-560)
✅ Search functional
✅ Both DBs have identical data
```

### Step 8.3: Run Latency Benchmarks
**Time:** 2 hours | **Checkpoint:** benchmark_results.json generated

- [ ] Run benchmark test suite: `pytest tests/benchmarks/benchmark_latency.py -v`
- [ ] Collects:
  - [ ] Search latency: 100 searches per backend
  - [ ] Embedding latency: 50 query embeddings
  - [ ] End-to-end latency: 20 full queries (retrieve → answer)
- [ ] Generates: benchmark_results.json
- [ ] Review results:
  - [ ] Local should be ~20x faster
  - [ ] Pinecone should be ~87ms search
  - [ ] No timeouts or errors

**Validation:**
```
✅ benchmark_results.json created
✅ All metrics collected
✅ Results reasonable (local faster)
✅ No errors in output
```

### Step 8.4: Run Accuracy Benchmarks
**Time:** 2 hours | **Checkpoint:** eval_results.json generated

- [ ] Run evaluation: `pytest tests/evals/eval_retrieval.py -v`
- [ ] For each of 30 queries:
  - [ ] Search in Local
  - [ ] Get top-8 results
  - [ ] Compare to ground truth (from Phase 4)
  - [ ] Calculate accuracy metrics
  - [ ] Record per-query and aggregate
- [ ] Repeat for Pinecone
- [ ] Generates: eval_results.json
- [ ] Review results:
  - [ ] Both should be ~75-77% accuracy
  - [ ] Pinecone might be slightly better
  - [ ] Check which queries were hard

**Validation:**
```
✅ eval_results.json created
✅ All 30 queries tested on both backends
✅ Metrics calculated
✅ Accuracy ~75%+ (reasonable)
✅ No major outliers
```

### Step 8.5: Run Answer Quality Evaluation
**Time:** 3 hours | **Checkpoint:** eval_answer_results.json generated

- [ ] Run answer evaluation: `pytest tests/evals/eval_answer_quality.py -v`
- [ ] For each of 30 queries:
  - [ ] Generate answer using retrieved chunks
  - [ ] Check if citations present
  - [ ] Manually score completeness (0-5)
  - [ ] Manually score correctness (0-5)
  - [ ] Record all scores
- [ ] Generates: eval_answer_results.json
- [ ] Review results:
  - [ ] Citation accuracy should be 100%
  - [ ] Completeness score 3-5
  - [ ] Correctness score 3-5

**Validation:**
```
✅ eval_answer_results.json created
✅ All answers generated
✅ Quality scores recorded
✅ Citations verified
```

### Step 8.6: Generate Comparison Report
**Time:** 1 hour | **Checkpoint:** comparison_report.json generated

- [ ] Run analysis function (when written in Phase 7)
- [ ] Input:
  - [ ] benchmark_results.json
  - [ ] eval_results.json
  - [ ] eval_answer_results.json
- [ ] Output: comparison_report.json
- [ ] Manual review:
  - [ ] Does report make sense?
  - [ ] Are conclusions supported by data?
  - [ ] Any surprising findings?

**Validation:**
```
✅ comparison_report.json created
✅ All metrics populated
✅ Recommendations clear
✅ Data supports conclusions
```

**End of Phase 8:** Benchmarks executed and analyzed  
**Checkpoint:** All benchmark results collected and compared  
**Commit to Git:** "Add benchmark results: local vs pinecone comparison"

---

# PHASE 9: Analysis & Report
**Time:** 1 day | **Status:** Not started

## Goal
Create a professional benchmark report with findings and recommendations.

### Step 9.1: Create Comparison Markdown Report
**Time:** 3 hours | **Checkpoint:** benchmark-comparison.md created

- [ ] Create file: `benchmark-comparison.md`
- [ ] Structure:
  - [ ] Executive Summary (1 para)
  - [ ] Methodology (how tests run, sample size, etc)
  - [ ] Results Tables (copy from JSON)
  - [ ] Analysis per metric
  - [ ] Trade-offs discussion
  - [ ] Recommendations
  - [ ] Conclusion
- [ ] Include:
  - [ ] Accuracy comparison table
  - [ ] Performance comparison table
  - [ ] Cost comparison table
  - [ ] Trade-offs analysis
  - [ ] Use case recommendations

**Validation:**
```
✅ benchmark-comparison.md created
✅ All sections complete
✅ Data accurate (from JSON results)
✅ Recommendations clear
```

### Step 9.2: Create Visualizations Description
**Time:** 2 hours | **Checkpoint:** visualization-plan.md created

- [ ] Create file: `visualization-plan.md`
- [ ] Document what visualizations show:
  - [ ] Chart 1: Accuracy comparison (bar chart)
  - [ ] Chart 2: Latency comparison (log scale)
  - [ ] Chart 3: Cost vs scale (line chart)
  - [ ] Chart 4: Throughput comparison (bar chart)
- [ ] Include:
  - [ ] What each chart shows
  - [ ] Key insight from each chart
  - [ ] How to interpret results

**Validation:**
```
✅ visualization-plan.md created
✅ All charts described
✅ Insights documented
```

### Step 9.3: Create Executive Summary Document
**Time:** 2 hours | **Checkpoint:** BENCHMARK_SUMMARY.md created

- [ ] Create file: `BENCHMARK_SUMMARY.md`
- [ ] Content (1-2 pages max):
  - [ ] What we benchmarked (local vs cloud)
  - [ ] Key findings (3-5 bullet points)
  - [ ] Trade-offs (latency vs cost vs accuracy)
  - [ ] Recommendation (when to use each)
  - [ ] Next steps (future testing, scaling)
- [ ] Tone: Professional, data-driven, actionable

**Validation:**
```
✅ BENCHMARK_SUMMARY.md created
✅ Concise and complete
✅ Conclusions justified
✅ Recommendation clear
```

**End of Phase 9:** Comprehensive benchmark report completed  
**Checkpoint:** Analysis documented and reported  
**Commit to Git:** "Add benchmark analysis and comparison report"

---

# PHASE 10: Documentation & Polish
**Time:** 1 day | **Status:** Not started

## Goal
Update all project documentation with benchmark findings and finalize for submission.

### Step 10.1: Update README.md
**Time:** 1 hour | **Checkpoint:** README updated

- [ ] Add new "Benchmarking" section to README.md
- [ ] Include:
  - [ ] Link to benchmark-comparison.md
  - [ ] Summary of findings (1 para)
  - [ ] Recommendation for new users
  - [ ] How to run benchmarks themselves

### Step 10.2: Update PROMPTS.md
**Time:** 30 min | **Checkpoint:** PROMPTS.md includes benchmarking

- [ ] Add to PROMPTS.md:
  - [ ] "Phase 8: Run Benchmarks" as a top prompt
  - [ ] What benchmarking revealed
  - [ ] Impact on architecture

### Step 10.3: Create SUBMISSION_CHECKLIST.md
**Time:** 30 min | **Checkpoint:** Checklist created

- [ ] Create file: `SUBMISSION_CHECKLIST.md`
- [ ] Contents:
  - [ ] Infrastructure ready (Docker, K8s)
  - [ ] Sample data included
  - [ ] Code tested
  - [ ] Benchmarks run
  - [ ] Report complete
  - [ ] Documentation updated
  - [ ] Git history clean

### Step 10.4: Final Git Cleanup
**Time:** 30 min | **Checkpoint:** Ready for submission

- [ ] Review all commits
- [ ] Verify no sensitive data in repo
- [ ] Verify all documentation complete
- [ ] Create final commit: "Complete benchmarking and submit"

**Validation:**
```
✅ All documentation updated
✅ Benchmarks documented
✅ Ready for submission
✅ No outstanding TODOs
```

**End of Phase 10:** Project finalized and ready for submission  
**Final Checkpoint:** Complete, tested, documented, benchmarked  

---

# APPENDIX: Time Estimates & Dependencies

## Total Time Estimate
```
Phase 1: Infrastructure        2 days
Phase 2: Incremental Chunking  3 days
Phase 3: Dual Storage          2 days
Phase 4: Sample Data           1 day
Phase 5: UI Toggles            2 days
Phase 6: Test Suite            2 days
Phase 7: Benchmarking Framework 2 days
Phase 8: Run Benchmarks        2 days
Phase 9: Analysis & Report     1 day
Phase 10: Documentation        1 day
─────────────────────────────────────
TOTAL: ~18 days of work
```

## Critical Path (what blocks what)
```
Phase 1 → Phase 2 → Phase 4 → Phase 8
        ├─ Phase 3 ─────────────┘
        ├─ Phase 5 (can happen in parallel)
        ├─ Phase 6 (can start after Phase 2)
        └─ Phase 7 (can start after Phase 6)

Fastest route if parallel:
- Phases 1, 2 (sequential, 5 days)
- Phases 3, 4, 5, 6, 7 (parallel, ~3 days)
- Phases 8, 9, 10 (sequential, ~4 days)
= ~12 days minimum with parallelization
```

## What you can parallelize
- Phase 3 (Dual Storage) and Phase 5 (UI) can happen simultaneously after Phase 2
- Phase 6 (Tests) and Phase 7 (Benchmarking Framework) can happen simultaneously
- Phase 9 can start before Phase 8 finishes (write report template)

## Success Criteria
```
✅ All 10 phases complete
✅ Sample data (5 PDFs) working
✅ Both backends (local + Pinecone) functional
✅ 30 benchmark queries tested
✅ Latency measurements done
✅ Accuracy metrics calculated
✅ Report generated
✅ Documentation complete
✅ Ready for project submission
```

---

**Ready to start Phase 1?** Let me know when you're done with each phase, and I'll guide you through the next one.
