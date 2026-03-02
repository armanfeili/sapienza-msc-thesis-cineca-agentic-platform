# Cineca Agentic Platform - Memgraph Database Reference

**Last Updated:** 2025-10-24  
**Purpose:** Comprehensive reference for Memgraph graph database implementation

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Core Files](#core-files)
   - [Configuration](#configuration)
   - [Client Connection](#client-connection)
   - [Database Creation](#database-creation)
   - [Population Module](#population-module)
4. [Graph Schema](#graph-schema)
5. [Data Generation](#data-generation)
6. [Docker Integration](#docker-integration)
7. [Sample Queries](#sample-queries)
8. [Best Practices](#best-practices)

---

## Overview

Memgraph is an in-memory graph database used in the Cineca Agentic Platform for:

- **Graph-Based Relationships**: Model complex relationships between entities (users, institutions, tasks, files)
- **High-Performance Queries**: Sub-millisecond graph traversals using openCypher query language
- **Real-Time Analytics**: Pattern matching and path finding for workflow analysis
- **Scalable Storage**: Efficient storage of nodes and relationships with property graphs

**Technology Stack:**
- **Database:** Memgraph 2.x (in-memory ACID graph database)
- **Query Language:** openCypher (Cypher dialect for graph queries)
- **Python Client:** GQLAlchemy (object-graph mapper) + mgclient (low-level driver)
- **Deployment:** Docker container with persistent volume storage

**Use Cases:**
- User-Institution relationships (WORKS_AT)
- Task execution workflows (RUNS, INPUT, OUTPUT)
- File dependencies and lineage tracking
- Bioinformatics tool chains (BLAST, BOLD, taxonomy searches)

---

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                   Memgraph Container                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │        Memgraph Engine (Port 7687)                   │   │
│  │  ┌─────────────────────────────────────────────┐     │   │
│  │  │   Graph Storage (In-Memory + Disk)          │     │   │
│  │  │   • Nodes: User, Institution, Task, File    │     │   │
│  │  │   • Edges: WORKS_AT, RUNS, INPUT, OUTPUT    │     │   │
│  │  │   • Indexes: orig_id, task_id, file_id      │     │   │
│  │  └─────────────────────────────────────────────┘     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
         ↑                              ↑
         │ Bolt Protocol (TCP)          │ HTTP
         │                              │
    ┌────────────┐              ┌──────────────┐
    │ GQLAlchemy │              │  mgclient    │
    │   Client   │              │  (low-level) │
    └────────────┘              └──────────────┘
         ↑                              ↑
         └──────────────┬───────────────┘
                        │
           ┌────────────────────────┐
           │  db/memgraph_domain/   │
           │  • config.py           │
           │  • memgraph_client.py  │
           │  • populate.py         │
           │  • create_original_db.py
           └────────────────────────┘
```

### Data Flow

1. **Configuration** → `config.py` loads environment variables (host, port, credentials)
2. **Connection** → `memgraph_client.py` creates GQLAlchemy/mgclient connection
3. **Schema Creation** → `create_original_db.py` creates indexes and constraints
4. **Data Import** → Loads original dataset from `original-dataset/node_examples.json`
5. **Synthetic Population** → `populate.py` generates test data (users, institutions, tasks)
6. **Query Execution** → Application executes openCypher queries via client

---

## Core Files

### Configuration

**File:** `db/memgraph_domain/config.py`  
**Lines:** 20  
**Purpose:** Centralized configuration for Memgraph connection

#### Configuration Class

```python
class Settings(BaseSettings):
    MG_HOST: str = "memgraph"         # Docker service name
    MG_PORT: int = 7687               # Bolt protocol port
    MG_USER: str = ""                 # Optional username
    MG_PASSWORD: str = ""             # Optional password
    
    # Data generation parameters
    NUM_USERS: int = 200              # Default user count
    NUM_INSTITUTIONS: int = 50        # Default institution count
    MAX_TASKS_PER_USER: int = 10      # Tasks per user
    MAX_INPUT_FILES: int = 3          # Max files per task input
```

#### Environment Variables

```bash
# .env file
MG_HOST=memgraph                      # Docker service name or IP
MG_PORT=7687                          # Bolt protocol port
MG_USER=                              # Leave empty for no auth
MG_PASSWORD=                          # Leave empty for no auth

# Data generation
NUM_USERS=200
NUM_INSTITUTIONS=50
MAX_TASKS_PER_USER=10
MAX_INPUT_FILES=3
```

#### Features

- **Pydantic Settings**: Type-safe configuration with validation
- **Environment Override**: All settings can be overridden via `.env` file
- **Sensible Defaults**: Works out-of-the-box for local development
- **Docker-Friendly**: Uses service names for container networking

---

### Client Connection

**File:** `db/memgraph_domain/memgraph_client.py`  
**Lines:** 45  
**Purpose:** Connection factory for Memgraph database

#### Connection Factory

```python
def get_memgraph() -> Memgraph:
    """
    Returns a GQLAlchemy Memgraph client instance.
    
    Features:
    - Lazy connection (connects on first query)
    - Optional authentication
    - Connection pooling handled by GQLAlchemy
    
    Returns:
        Memgraph client instance
    
    Usage:
        mg = get_memgraph()
        results = mg.execute_and_fetch("MATCH (n:User) RETURN n LIMIT 5")
        for record in results:
            print(record["n"].to_dict())
    """
    if MG_USER and MG_PASSWORD:
        return Memgraph(
            host=MG_HOST, 
            port=MG_PORT, 
            username=MG_USER, 
            password=MG_PASSWORD
        )
    else:
        return Memgraph(host=MG_HOST, port=MG_PORT)
```

#### Usage Examples

**Basic Query:**
```python
from db.memgraph_domain.memgraph_client import get_memgraph

mg = get_memgraph()

# Count all nodes
result = mg.execute_and_fetch("MATCH (n) RETURN count(n) as total")
total_nodes = next(result)["total"]

print(f"Total nodes: {total_nodes}")
```

**Parameterized Query:**
```python
mg = get_memgraph()

# Find user by email
query = "MATCH (u:User {email: $email}) RETURN u"
result = mg.execute_and_fetch(query, {"email": "user@example.com"})

for record in result:
    user = record["u"]
    print(f"Found user: {user.to_dict()}")
```

**Create Node:**
```python
mg = get_memgraph()

# Create new user
query = """
CREATE (u:User {
    user_id: $user_id,
    email: $email,
    firstName: $first_name,
    lastName: $last_name
})
RETURN u
"""

params = {
    "user_id": "usr_123",
    "email": "new.user@example.com",
    "first_name": "New",
    "last_name": "User"
}

result = mg.execute_and_fetch(query, params)
```

#### Connection Health Check

```python
def check_memgraph_health() -> bool:
    """Check if Memgraph is reachable."""
    try:
        mg = get_memgraph()
        mg.execute("RETURN 1")
        return True
    except Exception as e:
        print(f"Memgraph health check failed: {e}")
        return False
```

---

### Database Creation

**File:** `db/memgraph_domain/create_original_db.py`  
**Lines:** 180  
**Purpose:** Create database schema and import original dataset

#### Purpose

This module initializes the Memgraph database with:
1. **Schema Definition**: Creates indexes on critical properties
2. **Data Import**: Loads nodes and relationships from JSON-Lines files
3. **Constraint Enforcement**: Ensures uniqueness on `orig_id` property

#### Data Sources

**Directory:** `db/memgraph_domain/original-dataset/`

1. **export.csv** - Schema metadata with index hints
   ```csv
   type,label,property,index
   node,User,orig_id,true
   node,Institution,orig_id,true
   node,File,file_id,true
   relationship,WORKS_AT,,false
   ```

2. **node_examples.json** - JSONL file with actual data
   ```json
   {"type":"node","id":"usr_001","labels":["User"],"properties":{"email":"alice@example.com"}}
   {"type":"relationship","id":"rel_001","label":"WORKS_AT","start":{"id":"usr_001"},"end":{"id":"inst_001"},"properties":{}}
   ```

3. **records.json** - Full schema snapshot (unused in import, for reference)

#### Key Functions

**Load JSONL Data:**
```python
def load_jsonl(path: Path) -> tuple[List[dict], List[dict]]:
    """
    Parse JSON-Lines file into nodes and relationships.
    
    Returns:
        (nodes, relationships) - Two separate lists
    """
    nodes = []
    relationships = []
    
    with path.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec["type"] == "node":
                nodes.append(rec)
            elif rec["type"] == "relationship":
                relationships.append(rec)
    
    return nodes, relationships
```

**Load Index Hints:**
```python
def load_index_hints(path: Path) -> List[Tuple[str, str]]:
    """
    Read export.csv and extract (label, property) pairs for indexing.
    
    Only includes rows where index=true.
    """
    hints = []
    
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("type") != "node":
                continue
            if row.get("index", "").lower() != "true":
                continue
            
            label = row["label"].strip(' "')
            prop = row["property"].strip(' "')
            hints.append((label, prop))
    
    return hints
```

**Create Indexes:**
```python
def create_all_indexes(cur, nodes: List[dict], index_hints: List[Tuple[str, str]]) -> None:
    """
    Create indexes for:
    1. orig_id on all node labels (for lookups during import)
    2. Additional indexes from export.csv hints
    """
    # Index orig_id for every label in dataset
    seen_labels = set()
    for n in nodes:
        for lbl in n["labels"]:
            if lbl not in seen_labels:
                seen_labels.add(lbl)
                ensure_index(cur, lbl, "orig_id")
    
    # Extra indexes from CSV hints
    for lbl, prop in index_hints:
        ensure_index(cur, lbl, prop)

def ensure_index(cur, label: str, prop: str) -> None:
    """Create index, ignoring 'already exists' errors."""
    try:
        cur.execute(f"CREATE INDEX ON :`{label}`(`{prop}`)")
    except mgclient.DatabaseError:
        pass  # Index already exists
```

**Import Nodes:**
```python
def import_nodes(cur, nodes: List[dict]) -> None:
    """
    MERGE all nodes using orig_id as unique key.
    
    Uses MERGE instead of CREATE to handle re-imports gracefully.
    """
    for n in nodes:
        labels = ":".join(f"`{l}`" for l in n["labels"])
        props = n["properties"] or {}
        props["orig_id"] = n["id"]
        
        query = f"""
        MERGE (n:{labels} {{orig_id: $orig_id}})
        SET n += $props
        """
        
        cur.execute(query, {"orig_id": n["id"], "props": props})
```

**Import Relationships:**
```python
def import_relationships(cur, relationships: List[dict]) -> None:
    """
    MERGE all relationships between nodes.
    
    Requires nodes to exist first (matched by orig_id).
    """
    for r in relationships:
        label = f"`{r['label']}`"
        start_id = r["start"]["id"]
        end_id = r["end"]["id"]
        props = r.get("properties", {})
        
        query = f"""
        MATCH (a {{orig_id: $start}}), (b {{orig_id: $end}})
        MERGE (a)-[rel:{label}]->(b)
        SET rel += $props
        """
        
        cur.execute(query, {"start": start_id, "end": end_id, "props": props})
```

#### Main Execution Flow

```python
def main() -> None:
    """
    Complete database initialization:
    1. Load data from JSONL and CSV
    2. Connect to Memgraph
    3. Drop existing data (optional)
    4. Create indexes
    5. Import nodes
    6. Import relationships
    7. Commit transaction
    """
    # Load data
    nodes, relationships = load_jsonl(NODES_FILE)
    index_hints = load_index_hints(EXPORT_CSV)
    
    print(f"Nodes: {len(nodes):>3} | Relationships: {len(relationships):>3}")
    
    # Connect to Memgraph
    conn = connect()
    
    try:
        cur = conn.cursor()
        conn.autocommit = False
        
        # Drop existing data
        cur.execute("MATCH (n) DETACH DELETE n")
        
        # Create indexes
        create_all_indexes(cur, nodes, index_hints)
        
        # Import data
        import_nodes(cur, nodes)
        import_relationships(cur, relationships)
        
        # Commit
        conn.commit()
        print("✔  Original dataset loaded into Memgraph")
    
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
```

#### Running the Script

**From Docker Container:**
```bash
docker-compose exec db-populate python /app/db/memgraph_domain/create_original_db.py
```

**From Host (if Memgraph exposed on localhost:7687):**
```bash
cd db/memgraph_domain
python create_original_db.py
```

---

### Population Module

**File:** `db/memgraph_domain/populate.py`  
**Lines:** 650  
**Purpose:** Generate synthetic data for testing and development

#### Features

- **Synthetic Data Generation**: Create realistic test data using Faker library
- **Schema-Correct Data**: Maintains graph schema integrity
- **Configurable Volume**: Control number of users, institutions, tasks
- **Progress Tracking**: Redis-based progress reporting for background jobs
- **Cancellation Support**: Honor job cancellation requests via Redis

#### Graph Schema

The populate module generates the following graph structure:

```
User ──[:WORKS_AT]──► Institution
 │
 └──[:RUNS]──────► Task (SearchbyTaxon | Bold | Command | Blast | BlastSeq | CreateDb)
                    ↓
                 [:INPUT]──► File (Fasta | File | BlastDb)
                    ↓
                 [:OUTPUT]─► File (File | BlastedSeq | Fasta | Xml | BlastDb)
```

#### Data Generators

**Institutions:**
```python
def gen_institutions(n: int) -> List[Dict[str, Any]]:
    """
    Generate N institution nodes with random properties.
    
    Each institution has:
    - id: UUID
    - labels: ["Institution"]
    - props: {"name": company_name, ...extra_props}
    """
    return [
        {
            "id": uuid_str(),
            "labels": ["Institution"],
            "props": {"name": fake.company()} | random_extra_props(),
        }
        for _ in range(n)
    ]
```

**Users:**
```python
def gen_users(n: int, institutions: List[Dict]) -> List[Dict]:
    """
    Generate N user nodes, each linked to a random institution.
    
    Each user has:
    - id: UUID (also stored as user_id property)
    - labels: ["User"]
    - props: {firstName, lastName, user_name, email, ...}
    - _institution_id: Foreign key for WORKS_AT relationship
    """
    users = []
    for _ in range(n):
        inst = random.choice(institutions)
        uid = uuid_str()
        
        users.append({
            "id": uid,
            "labels": ["User"],
            "props": {
                "user_id": uid,
                "firstName": fake.first_name(),
                "lastName": fake.last_name(),
                "user_name": fake.user_name(),
                "email": fake.email(),
            } | random_extra_props(),
            "_institution_id": inst["id"],
        })
    
    return users
```

**Tasks:**
```python
TASK_LABELS = ["SearchbyTaxon", "Bold", "Command", "Blast", "BlastSeq", "CreateDb"]

def gen_tasks(user: Dict, max_tasks: int) -> List[Dict]:
    """
    Generate 1-N tasks for a user.
    
    Each task has:
    - Type-specific properties (e.g., blasttype, dbname)
    - Common properties (task_id, status, start, tags)
    - _user_id: Foreign key for RUNS relationship
    """
    tasks = []
    
    for _ in range(random.randint(1, max_tasks)):
        lbl = random.choice(TASK_LABELS)
        t_id = uuid_str()
        
        common = {
            "task_id": t_id,
            "status": random.choice(["Pending", "Running", "Complete"]),
            "start": rand_datetime(),
            "tags": [],
        }
        
        # Type-specific properties
        specific = {}
        if lbl in {"Blast", "BlastSeq"}:
            specific = {
                "blasttype": random.choice(["blastn", "blastp"]),
                "blast_version": random.choice(["2.14", "2.15"]),
                "dbname": fake.lexify(text="????_DB"),
                "output_csv": fake.file_name(extension="csv"),
                "output_result": fake.word() + "_run",
            }
        elif lbl == "CreateDb":
            specific = {
                "dbtype": random.choice(["nucl", "prot"]),
                "dbname": fake.lexify(text="????_DB"),
            }
        # ... (other task types)
        
        tasks.append({
            "id": t_id,
            "labels": [lbl, "Command"] if lbl != "Command" else [lbl],
            "props": common | specific | random_extra_props(),
            "_user_id": user["id"],
        })
    
    return tasks
```

**Files:**
```python
def gen_files(label: str, n: int) -> List[Dict]:
    """
    Generate N file nodes of a specific type.
    
    File types: Fasta, File, BlastDb, BlastedSeq, Xml
    
    Each file has:
    - file_id, bucket_name, user_filename
    - extension, size, etag
    - uploaded (bool), date
    """
    return [
        {
            "id": uuid_str(),
            "labels": [label, "File"],
            "props": {
                "file_id": uuid_str(),
                "bucket_name": fake.lexify(text="???"),
                "user_filename": fake.file_name(),
                "extension": fake.file_extension(),
                "size": random.randint(100, 2_000_000),
                "etag": fake.md5(),
                "uploaded": rand_bool(),
                "date": rand_datetime(),
            } | random_extra_props(),
        }
        for _ in range(max(1, n))
    ]
```

#### Graph Assembly

```python
def build_graph() -> Tuple[List[Dict], List[Tuple[str, str, str]]]:
    """
    Assemble complete graph structure.
    
    Returns:
        (nodes, relationships)
        - nodes: List of node dicts
        - relationships: List of (from_id, rel_type, to_id) tuples
    """
    nodes = []
    rels = []
    
    # Generate base entities
    institutions = gen_institutions(NUM_INSTITUTIONS)
    users = gen_users(NUM_USERS, institutions)
    nodes.extend(institutions + users)
    
    # WORKS_AT relationships
    rels.extend((u["id"], "WORKS_AT", u["_institution_id"]) for u in users)
    
    # Generate tasks for each user
    all_tasks = []
    for u in users:
        tasks = gen_tasks(u, MAX_TASKS_PER_USER)
        all_tasks.extend(tasks)
        # RUNS relationships
        rels.extend((u["id"], "RUNS", t["id"]) for t in tasks)
    
    nodes.extend(all_tasks)
    
    # Generate file pools
    fasta_files = gen_files("Fasta", NUM_USERS)
    generic_files = gen_files("File", NUM_USERS * 3)
    blastdb_files = gen_files("BlastDb", NUM_USERS)
    # ... (other file types)
    
    nodes.extend(fasta_files + generic_files + blastdb_files + ...)
    
    # INPUT/OUTPUT relationships
    for task in all_tasks:
        labels = set(task["labels"])
        
        # Input files (1-3 per task)
        for _ in range(random.randint(1, MAX_INPUT_FILES)):
            if labels & {"Blast", "BlastSeq"}:
                f = random.choice(blastdb_files + fasta_files)
            else:
                f = random.choice(generic_files + fasta_files)
            
            rels.append((f["id"], "INPUT", task["id"]))
        
        # Output file (1 per task)
        if labels & {"Blast", "BlastSeq"}:
            out = random.choice(blastedseq_files + generic_files)
        else:
            out = random.choice(fasta_files + xml_files)
        
        rels.append((task["id"], "OUTPUT", out["id"]))
    
    return nodes, rels
```

#### Persistence

```python
def persist_graph(
    nodes: List[Dict], 
    rels: List[Tuple[str, str, str]], 
    *, 
    wipe: bool = False
) -> None:
    """
    Persist graph to Memgraph with progress tracking.
    
    Args:
        nodes: List of node dicts
        rels: List of (from_id, rel_type, to_id) tuples
        wipe: If True, delete existing data first
    
    Features:
    - Atomic transaction (all-or-nothing)
    - Progress reporting via Redis
    - Cancellation support via Redis signal
    """
    conn = connect()
    
    try:
        cur = conn.cursor()
        
        # Wipe existing data if requested
        if wipe:
            conn.autocommit = True
            cur.execute("MATCH (n) DETACH DELETE n")
            cur.close()
            cur = conn.cursor()
        
        # Start transaction
        conn.autocommit = False
        
        # Import nodes
        for n in nodes:
            labels = ":".join(f"`{l}`" for l in n["labels"])
            props = n["props"] | {"orig_id": n["id"]}
            
            cur.execute(
                f"MERGE (n:{labels} {{orig_id: $id}}) SET n += $props",
                {"id": n["id"], "props": props}
            )
        
        # Import relationships
        for a, rel_type, b in rels:
            cur.execute(
                f"""
                MATCH (x {{orig_id: $a}}), (y {{orig_id: $b}})
                MERGE (x)-[:`{rel_type}`]->(y)
                """,
                {"a": a, "b": b}
            )
        
        # Commit
        conn.commit()
        print(f"✔  Populated graph with {len(nodes)} nodes and {len(rels)} relationships")
    
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()
```

#### Usage

**CLI:**
```bash
# Default (200 users, 50 institutions)
python db/memgraph_domain/populate.py

# Custom parameters
python db/memgraph_domain/populate.py --users 500 --institutions 100 --max-tasks 15
```

**Programmatic:**
```python
from db.memgraph_domain.populate import build_graph, persist_graph

# Generate data
nodes, rels = build_graph()

# Persist to Memgraph (append to existing data)
persist_graph(nodes, rels, wipe=False)

# Or wipe first
persist_graph(nodes, rels, wipe=True)
```

---

## Graph Schema

### Node Types

**User:**
```cypher
(:User {
    orig_id: "usr_123",
    user_id: "usr_123",
    firstName: "Alice",
    lastName: "Smith",
    user_name: "asmith",
    email: "alice@example.com",
    // ...extra random properties
})
```

**Institution:**
```cypher
(:Institution {
    orig_id: "inst_42",
    name: "ACME Corporation",
    // ...extra random properties
})
```

**Task (Blast example):**
```cypher
(:Blast:Command {
    orig_id: "task_789",
    task_id: "task_789",
    status: "Complete",
    start: "2025-10-15T10:30:00",
    blasttype: "blastn",
    blast_version: "2.15",
    dbname: "NCBI_DB",
    output_csv: "results.csv",
    output_result: "blast_run_001"
})
```

**File (Fasta example):**
```cypher
(:Fasta:File {
    orig_id: "file_456",
    file_id: "file_456",
    bucket_name: "xyz",
    user_filename: "sequences.fasta",
    extension: "fasta",
    size: 1048576,
    etag: "a1b2c3d4e5f6",
    uploaded: true,
    date: "2025-10-20T14:00:00"
})
```

### Relationship Types

**WORKS_AT:**
```cypher
(:User)-[:WORKS_AT]->(:Institution)
```

**RUNS:**
```cypher
(:User)-[:RUNS]->(:Task)
```

**INPUT:**
```cypher
(:File)-[:INPUT]->(:Task)
```

**OUTPUT:**
```cypher
(:Task)-[:OUTPUT]->(:File)
```

---

## Docker Integration

**File:** `db/memgraph_domain/Dockerfile`  
**Purpose:** Container image for database population service

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy database modules
COPY db/ /app/db/
COPY src/config.py /app/src/

# Set Python path
ENV PYTHONPATH=/app

# Default command (can be overridden)
CMD ["python", "/app/db/memgraph_domain/populate.py"]
```

### Docker Compose Integration

```yaml
services:
  memgraph:
    image: memgraph/memgraph:2.14.1
    container_name: cineca-memgraph
    ports:
      - "7687:7687"    # Bolt protocol
      - "7444:7444"    # Monitoring
    volumes:
      - memgraph_data:/var/lib/memgraph
    environment:
      - MEMGRAPH_LOG_LEVEL=INFO
    healthcheck:
      test: ["CMD", "nc", "-z", "localhost", "7687"]
      interval: 10s
      timeout: 5s
      retries: 5

  db-populate:
    build:
      context: .
      dockerfile: db/memgraph_domain/Dockerfile
    depends_on:
      memgraph:
        condition: service_healthy
    environment:
      - MG_HOST=memgraph
      - MG_PORT=7687
      - NUM_USERS=200
      - NUM_INSTITUTIONS=50
    volumes:
      - ./db:/app/db
    command: python /app/db/memgraph_domain/populate.py

volumes:
  memgraph_data:
```

---

## Sample Queries

**File:** `db/memgraph_domain/sample_queries.txt`  
**Purpose:** Collection of useful openCypher queries

### Node Queries

**Count Nodes by Label:**
```cypher
MATCH (n)
RETURN labels(n)[0] AS label, count(n) AS count
ORDER BY count DESC;
```

**Find Users:**
```cypher
MATCH (u:User)
WHERE u.email CONTAINS "@example.com"
RETURN u.firstName, u.lastName, u.email
LIMIT 10;
```

### Relationship Queries

**User Institutions:**
```cypher
MATCH (u:User)-[:WORKS_AT]->(i:Institution)
RETURN u.email, i.name
LIMIT 25;
```

**Task Inputs:**
```cypher
MATCH (f:File)-[:INPUT]->(t:Task)
WHERE t.status = "Complete"
RETURN t.task_id, collect(f.user_filename) AS input_files
LIMIT 10;
```

### Path Queries

**User to File (through Task):**
```cypher
MATCH path = (u:User)-[:RUNS]->(t:Task)-[:OUTPUT]->(f:File)
WHERE u.email = "alice@example.com"
RETURN path
LIMIT 5;
```

**Degree Distribution:**
```cypher
MATCH (u:User)-[:RUNS]->(t)
WITH u, count(t) AS task_count
RETURN task_count, count(u) AS users
ORDER BY task_count;
```

---

## Best Practices

### 1. Indexing

**Always index lookup properties:**
```cypher
CREATE INDEX ON :User(user_id);
CREATE INDEX ON :User(email);
CREATE INDEX ON :Task(task_id);
CREATE INDEX ON :File(file_id);
```

### 2. Query Optimization

**Use LIMIT for exploration:**
```cypher
MATCH (n:User)
RETURN n
LIMIT 10;  -- Prevent accidentally fetching millions of nodes
```

**Filter early:**
```cypher
// Good: Filter before expand
MATCH (u:User {email: "alice@example.com"})-[:RUNS]->(t:Task)
RETURN t;

// Bad: Expand then filter
MATCH (u:User)-[:RUNS]->(t:Task)
WHERE u.email = "alice@example.com"
RETURN t;
```

### 3. Transaction Management

**Use explicit transactions for bulk operations:**
```python
conn.autocommit = False
try:
    for item in large_dataset:
        cur.execute(query, params)
    conn.commit()
except:
    conn.rollback()
    raise
```

### 4. Property Management

**Use property maps for flexibility:**
```python
# Instead of many individual SET statements
props = {"name": "Alice", "age": 30, "city": "NYC"}
cur.execute("MERGE (u:User {id: $id}) SET u += $props", {"id": "123", "props": props})
```

### 5. Monitoring

**Check database size:**
```cypher
MATCH (n)
RETURN count(n) AS nodes, 
       count{MATCH ()-[r]->() RETURN r} AS relationships;
```

**Profile slow queries:**
```cypher
PROFILE
MATCH (u:User)-[:RUNS]->(t:Task)
WHERE t.status = "Complete"
RETURN u, t;
```

---

**Document Version:** 1.0  
**Last Updated:** 2025-10-24  
**Maintainer:** Cineca Agentic Platform Team
