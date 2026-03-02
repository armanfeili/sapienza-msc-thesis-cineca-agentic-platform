# Memgraph Domain Module

This module provides the graph database infrastructure for the **Cineca Agentic Platform**, using [Memgraph](https://memgraph.com/) as the graph database backend. It includes configuration, client utilities, data population scripts, sample queries, and reference datasets for building and managing the knowledge graph.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Directory Structure](#directory-structure)
- [Installation & Setup](#installation--setup)
- [Configuration](#configuration)
- [Module Components](#module-components)
  - [Package Initialization (`__init__.py`)](#package-initialization-__init__py)
  - [Configuration (`config.py`)](#configuration-configpy)
  - [Memgraph Client (`memgraph_client.py`)](#memgraph-client-memgraph_clientpy)
  - [Original Database Creator (`create_original_db.py`)](#original-database-creator-create_original_dbpy)
  - [Data Population (`populate.py`)](#data-population-populatepy)
  - [Docker Configuration (`Dockerfile`)](#docker-configuration-dockerfile)
- [Graph Schema](#graph-schema)
  - [Node Types](#node-types)
  - [Relationship Types](#relationship-types)
  - [Schema Diagram](#schema-diagram)
- [Sample Queries](#sample-queries)
- [Datasets](#datasets)
  - [Original Dataset](#original-dataset)
  - [Populated Dataset](#populated-dataset)
- [Usage Examples](#usage-examples)
- [CLI Reference](#cli-reference)
- [Docker Deployment](#docker-deployment)
- [Integration with Main Application](#integration-with-main-application)
- [Troubleshooting](#troubleshooting)
- [API Reference](#api-reference)

---

## Overview

The `memgraph_domain` module serves as the data layer for managing graph-based data in the Cineca Agentic Platform. It provides:

- **Graph Client Factory**: Easy-to-use Memgraph connection management
- **Pydantic Configuration**: Type-safe settings with environment variable support
- **Data Population Scripts**: Generate synthetic yet schema-correct test data
- **Original Dataset Loader**: Import reference datasets from JSON/CSV files
- **Docker Integration**: Containerized deployment with docker-compose support
- **Sample Queries**: Comprehensive Cypher query library for exploration

The module is designed for **bioinformatics workflows**, modeling users, institutions, computational tasks (BLAST, taxonomy searches, database creation), and file artifacts.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Cineca Agentic Platform                       │
├──────────────────────────────────────────────────────────────────┤
│  Application Layer (FastAPI)                                     │
│       ↓                                                          │
│  db.memgraph_domain package                                      │
│       ├── get_memgraph() → Memgraph client                       │
│       ├── settings → Configuration (env vars / .env)            │
│       └── populate/create_original_db → Data loaders             │
│       ↓                                                          │
│  Memgraph Database (Bolt protocol, port 7687)                    │
└──────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
db/memgraph_domain/
├── __init__.py              # Package exports (get_memgraph, settings)
├── config.py                # Pydantic settings for Memgraph connection
├── memgraph_client.py       # Client factory using gqlalchemy
├── create_original_db.py    # Loader for reference dataset files
├── populate.py              # Synthetic data generator (~762 lines)
├── Dockerfile               # Docker image for db-populate container
├── sample_queries.txt       # Cypher queries for exploration/debugging
├── original-dataset/        # Reference data files
│   ├── export.csv           # Schema summary with index hints
│   ├── node_examples.json   # Actual nodes & relationships (JSON Lines)
│   └── records.json         # Full schema snapshot (1388 lines)
└── populated/               # Output from population scripts
    └── memgraph-query-results-export.csv  # Exported query results (~18K rows)
```

---

## Installation & Setup

### Prerequisites

- **Python 3.11+**
- **Memgraph** (Community or Enterprise)
- **Docker & Docker Compose** (optional, for containerized deployment)

### Python Dependencies

```bash
pip install gqlalchemy mgclient pydantic-settings python-dotenv faker
```

Or install from the project's requirements:

```bash
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the project root or set environment variables:

```bash
# Memgraph connection
MG_HOST=memgraph          # Default: "memgraph" (docker service name)
MG_PORT=7687              # Default: 7687 (Bolt protocol)
MG_USER=                  # Optional: username for auth
MG_PASSWORD=              # Optional: password for auth

# Data population settings
NUM_USERS=200             # Number of User nodes to generate
NUM_INSTITUTIONS=50       # Number of Institution nodes
MAX_TASKS_PER_USER=10     # Max tasks per user
MAX_INPUT_FILES=3         # Max input files per task
```

---

## Configuration

### `config.py`

The configuration module uses **Pydantic Settings** for type-safe, validated configuration:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    MG_HOST: str = "memgraph"
    MG_PORT: int = 7687
    MG_USER: str = ""
    MG_PASSWORD: str = ""

    # Data generation defaults
    NUM_USERS: int = 200
    NUM_INSTITUTIONS: int = 50
    MAX_TASKS_PER_USER: int = 10
    MAX_INPUT_FILES: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()
```

### Configuration Options

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MG_HOST` | str | `"memgraph"` | Memgraph hostname (use `localhost` for local dev) |
| `MG_PORT` | int | `7687` | Memgraph Bolt protocol port |
| `MG_USER` | str | `""` | Username for authentication (optional) |
| `MG_PASSWORD` | str | `""` | Password for authentication (optional) |
| `NUM_USERS` | int | `200` | Number of User nodes to generate |
| `NUM_INSTITUTIONS` | int | `50` | Number of Institution nodes |
| `MAX_TASKS_PER_USER` | int | `10` | Maximum computational tasks per user |
| `MAX_INPUT_FILES` | int | `3` | Maximum input files per task |

---

## Module Components

### Package Initialization (`__init__.py`)

Provides convenient re-exports for the package:

```python
"""
db package — Memgraph helpers and configuration.

Convenience re-exports so callers can simply do:

    from db import settings, get_memgraph

    mg = get_memgraph()
    mg.execute("MATCH (n) RETURN n LIMIT 5")
"""

from .config import settings
from .memgraph_client import get_memgraph

__all__ = ["get_memgraph", "settings"]
```

### Configuration (`config.py`)

See [Configuration](#configuration) section above.

### Memgraph Client (`memgraph_client.py`)

Factory function for creating Memgraph connections using **gqlalchemy**:

```python
from dotenv import load_dotenv
from gqlalchemy import Memgraph
from .config import settings

load_dotenv()

def get_memgraph():
    """
    Returns a Memgraph client instance using environment variables.
    
    Usage:
        mg = get_memgraph()
        mg.execute("MATCH (n) RETURN n LIMIT 5")
    """
    if settings.MG_USER and settings.MG_PASSWORD:
        return Memgraph(
            host=settings.MG_HOST, 
            port=settings.MG_PORT, 
            username=settings.MG_USER, 
            password=settings.MG_PASSWORD
        )
    else:
        return Memgraph(host=settings.MG_HOST, port=settings.MG_PORT)
```

#### Usage Example

```python
from db.memgraph_domain import get_memgraph

# Get a client instance
mg = get_memgraph()

# Execute queries
result = mg.execute_and_fetch("MATCH (n:User) RETURN n.firstName, n.lastName LIMIT 10")
for record in result:
    print(record)

# Run Cypher statements
mg.execute("CREATE (u:User {firstName: 'John', lastName: 'Doe'})")
```

### Original Database Creator (`create_original_db.py`)

Imports the reference dataset from JSON/CSV files into Memgraph:

```python
# Key functions
def load_jsonl(path: Path) -> tuple[list[dict], list[dict]]:
    """Parse JSON Lines file into nodes and relationships."""

def load_index_hints(path: Path) -> list[tuple[str, str]]:
    """Read export.csv for index creation hints."""

def connect() -> mgclient.Connection:
    """Open Memgraph connection with optional auth."""

def ensure_index(cur, label: str, prop: str) -> None:
    """Create index if it doesn't exist."""

def create_all_indexes(cur, nodes, index_hints) -> None:
    """Create orig_id indexes + hints from export.csv."""

def import_nodes(cur, nodes: list[dict]) -> None:
    """MERGE all nodes with orig_id tracking."""

def import_relationships(cur, relationships: list[dict]) -> None:
    """MERGE all relationships by orig_id."""

def main() -> None:
    """Entry point: load files, create indexes, import data."""
```

#### Data Files Used

| File | Format | Purpose |
|------|--------|---------|
| `original-dataset/node_examples.json` | JSON Lines | Node and relationship definitions |
| `original-dataset/export.csv` | CSV | Schema summary with index hints |
| `original-dataset/records.json` | JSON | Full schema snapshot (metadata only) |

### Data Population (`populate.py`)

The main data population script (762 lines) generates synthetic bioinformatics workflow data.

#### Key Features

- **Faker Integration**: Realistic fake data generation
- **Schema-Compliant**: Follows the domain model exactly
- **Reproducible**: Fixed random seeds (`random.seed(42)`, `Faker.seed(42)`)
- **Configurable**: CLI arguments and environment variables
- **Redis Progress Tracking**: Optional job progress reporting
- **Cancellation Support**: Honors cancellation requests via Redis

#### Generated Data Volume

With default settings (~200 users, 50 institutions, 10 tasks/user):
- **Nodes**: 1000+ (Users, Institutions, Tasks, Files)
- **Relationships**: 2000+ (WORKS_AT, RUNS, INPUT, OUTPUT)
- **Properties**: 18,000+ label×property combinations

#### Main Functions

```python
# Generators
def gen_institutions(n: int) -> list[dict]:
    """Generate n Institution nodes with fake company names."""

def gen_users(n: int, institutions: list) -> list[dict]:
    """Generate n User nodes linked to random institutions."""

def gen_files(label: str, n: int) -> list[dict]:
    """Generate file nodes (Fasta, BlastDb, Xml, etc.)."""

def gen_tasks(user: dict, max_tasks: int) -> list[dict]:
    """Generate task nodes for a user (Blast, CreateDb, etc.)."""

# Assembly
def build_graph() -> tuple[list[dict], list[tuple[str, str, str]]]:
    """Assemble complete graph: nodes and relationships."""

# Persistence
def persist_graph(nodes, rels, *, wipe: bool = False) -> None:
    """Write nodes and relationships to Memgraph."""

# Combined workflow
def create_from_original_and_populate(
    original_dir: str = "db/original-dataset",
    *,
    wipe: bool = True,
    users: int = None,
    job_id: str = None
) -> None:
    """Load original dataset, then add synthetic data."""
```

#### CLI Usage

```bash
# Basic usage (uses defaults)
python -m db.memgraph_domain.populate

# Custom parameters
python -m db.memgraph_domain.populate \
    --users 500 \
    --institutions 100 \
    --max-tasks 20
```

#### Programmatic API

```python
from db.memgraph_domain.populate import populate, build_graph, persist_graph

# Use with an existing Memgraph client
mg = get_memgraph()
result = populate(db=mg)
print(f"Imported {result['nodes']} nodes, {result['relationships']} rels")

# Build graph data without persisting
nodes, rels = build_graph()

# Persist with optional wipe
persist_graph(nodes, rels, wipe=True)
```

### Docker Configuration (`Dockerfile`)

Multi-stage Dockerfile for the `db-populate` container:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

# Build dependencies (for pymgclient compilation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake libpq-dev libssl-dev

# Python dependencies
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Application code
COPY db/ db/
COPY db/memgraph_domain/populate.py /app/populate.py

# Cleanup build tools
RUN apt-get purge -y --auto-remove build-essential cmake

CMD ["python", "-m", "db.populate"]
```

---

## Graph Schema

The graph models **bioinformatics workflows** at CINECA, tracking users, their institutions, computational tasks, and file artifacts.

### Node Types

| Label | Description | Key Properties |
|-------|-------------|----------------|
| `User` | Platform user | `user_id`, `firstName`, `lastName`, `user_name`, `email` |
| `Institution` | Organization/company | `name` |
| `SearchbyTaxon` | Taxonomy search task | `task_id`, `status`, `taxon`, `tool`, `output_fasta` |
| `Bold` | BOLD (barcode) search task | `task_id`, `status`, `taxon`, `tool`, `output_fasta` |
| `Command` | Generic command task | `task_id`, `status`, `start`, `tags` |
| `Blast` | BLAST sequence search | `task_id`, `blasttype`, `blast_version`, `dbname`, `output_csv` |
| `BlastSeq` | BLAST sequence task | `task_id`, `blasttype`, `blast_version`, `dbname` |
| `CreateDb` | Database creation task | `task_id`, `dbtype`, `dbname` |
| `File` | Generic file artifact | `file_id`, `user_filename`, `size`, `extension`, `bucket_name` |
| `Fasta` | FASTA sequence file | `file_id`, `user_filename`, `size`, `extension` |
| `BlastDb` | BLAST database file | `file_id`, `dbname`, `size` |
| `BlastedSeq` | BLAST result file | `file_id`, `user_filename`, `size` |
| `Xml` | XML output file | `file_id`, `user_filename`, `size` |
| `PhyloTree` | Phylogenetic tree file | `file_id`, `format`, `size` |

### Relationship Types

| Type | Direction | Description |
|------|-----------|-------------|
| `WORKS_AT` | `(User)-[:WORKS_AT]->(Institution)` | User employment |
| `RUNS` | `(User)-[:RUNS]->(Task)` | User executes task |
| `INPUT` | `(File)-[:INPUT]->(Task)` | File is input to task |
| `OUTPUT` | `(Task)-[:OUTPUT]->(File)` | Task produces output file |

### Schema Diagram

```
                    ┌─────────────┐
                    │ Institution │
                    └──────▲──────┘
                           │ WORKS_AT
                    ┌──────┴──────┐
                    │    User     │
                    └──────┬──────┘
                           │ RUNS
           ┌───────────────┼────────────────┐
           ▼               ▼                ▼
    ┌─────────────┐ ┌─────────────┐  ┌─────────────┐
    │ SearchbyTaxon│ │   Blast    │  │  CreateDb   │
    │    Bold      │ │  BlastSeq  │  │             │
    │   Command    │ │  Command   │  │   Command   │
    └──────┬───────┘ └──────┬─────┘  └──────┬──────┘
           │                │               │
    INPUT──┤──OUTPUT  INPUT─┤──OUTPUT INPUT─┤──OUTPUT
           │                │               │
    ┌──────▼──────┐  ┌──────▼─────┐  ┌──────▼──────┐
    │   Fasta     │  │ BlastedSeq │  │  BlastDb    │
    │    File     │  │    File    │  │    File     │
    │    Xml      │  │  BlastDb   │  │             │
    └─────────────┘  └────────────┘  └─────────────┘
```

### Property Types

| Property | Type | Example |
|----------|------|---------|
| `user_id` | STRING | `"4f4b48b8-5dbf-4031-bd69-baa0dedf7bbf"` |
| `firstName` | STRING | `"Antonio"` |
| `lastName` | STRING | `"Costantini"` |
| `email` | STRING | `"a.costantini@cineca.it"` |
| `task_id` | STRING | `"010ff05d-798b-4fd5-8656-03bd3e71e51b"` |
| `status` | STRING | `"Pending"` / `"Running"` / `"Complete"` |
| `start` | STRING (ISO 8601) | `"2025-05-16T14:10:00.954748"` |
| `blasttype` | STRING | `"blastn"` / `"blastp"` |
| `blast_version` | STRING | `"2.14"` / `"2.15"` |
| `size` | INTEGER | `173088` |
| `uploaded` | BOOLEAN | `true` / `false` |
| `tags` | LIST | `[]` |
| `input_files` | LIST | `["uuid1", "uuid2", ...]` |

---

## Sample Queries

The `sample_queries.txt` file contains comprehensive Cypher queries organized into categories:

### Schema Inventory Query

Get a complete inventory of labels, properties, and relationships:

```cypher
CALL {
  -- Relationship types with targets
  MATCH (a)-[r]->(b)
  WITH type(r) AS _label, labels(a)[0] AS _property, count(*) AS _count,
       collect(DISTINCT labels(b)[0]) AS _targets
  RETURN _label AS label, _property AS property, _count AS count,
         'RELATIONSHIP' AS type, 'relationship' AS elementType

  UNION ALL

  -- Node labels with outgoing relationships
  MATCH (n)-[r]->(m)
  UNWIND labels(n) AS lbl
  WITH lbl AS _label, type(r) AS _property, count(*) AS _count
  RETURN _label AS label, _property AS property, _count AS count,
         'RELATIONSHIP' AS type, 'node' AS elementType

  UNION ALL

  -- Node properties
  MATCH (n)
  UNWIND labels(n) AS lbl
  UNWIND keys(n) AS prop
  WITH lbl AS _label, prop AS _property, count(*) AS _count
  RETURN _label AS label, _property AS property, _count AS count,
         'STRING' AS type, 'node' AS elementType
}
RETURN label, property, count, type, elementType
ORDER BY elementType, label, property;
```

### Common Exploration Queries

```cypher
-- View entire graph
MATCH (a)-[r]->(b) RETURN a, r, b;

-- Count all nodes
MATCH (n) RETURN count(n) AS node_count;

-- Count all relationships
MATCH ()-[r]->() RETURN count(r) AS rel_count;

-- Users and their institutions
MATCH (u:User)-[:WORKS_AT]->(i:Institution)
RETURN u.firstName + ' ' + u.lastName AS user,
       u.user_name AS username,
       i.name AS institution
ORDER BY institution, user;

-- User tasks with status
MATCH (u:User)-[:RUNS]->(t)
RETURN u.user_name AS username,
       labels(t)[0] AS task_type,
       t.task_id AS task_id,
       t.status AS status,
       t.start AS started
ORDER BY t.start DESC
LIMIT 25;

-- Task inputs
MATCH (f)-[:INPUT]->(t)
WHERE 'Fasta' IN labels(f) OR 'File' IN labels(f) OR 'BlastDb' IN labels(f)
RETURN labels(t)[0] AS task_type,
       t.task_id AS task_id,
       labels(f)[0] AS input_label,
       f.user_filename AS file_name,
       f.size AS bytes
ORDER BY task_type, input_label
LIMIT 25;

-- Task outputs
MATCH (t)-[:OUTPUT]->(f)
RETURN labels(t)[0] AS task_type,
       t.task_id AS task_id,
       labels(f)[0] AS output_label,
       f.user_filename AS file_name,
       f.size AS bytes
ORDER BY task_type, output_label
LIMIT 25;
```

### Schema Introspection

```cypher
-- List all node labels
MATCH (n)
WITH DISTINCT labels(n) AS lbls
UNWIND lbls AS label
RETURN DISTINCT label ORDER BY label;

-- List all relationship types
MATCH ()-[r]->()
RETURN DISTINCT type(r) AS relationship_type
ORDER BY relationship_type;

-- All node property keys
MATCH (n)
UNWIND keys(n) AS prop
RETURN DISTINCT prop ORDER BY prop;

-- Node counts per label
MATCH (n)
UNWIND labels(n) AS lbl
RETURN lbl AS label, count(*) AS count
ORDER BY count DESC;

-- Relationship counts per type
MATCH ()-[r]->()
RETURN type(r) AS rel_type, count(r) AS count
ORDER BY count DESC;

-- Show indexes
SHOW INDEX INFO;

-- Distinct relationship patterns
MATCH (a)-[r]->(b)
WITH labels(a)[0] AS from, type(r) AS rel, labels(b)[0] AS to
RETURN DISTINCT from, rel, to
ORDER BY from, rel, to;
```

### Database Maintenance

```cypher
-- Remove all relationships
MATCH ()-[r]-() DELETE r;

-- Remove all nodes
MATCH (n) DELETE n;

-- Complete graph reset (careful!)
DROP GRAPH;
```

---

## Datasets

### Original Dataset

Located in `original-dataset/`, this contains reference data from a real CINECA workflow:

#### `node_examples.json` (JSON Lines)

Each line is a complete node or relationship:

```json
{"type":"node","id":"0","labels":["User"],"properties":{"lastName":"Costantini","firstName":"Antonio","user_id":"4f4b48b8-5dbf-4031-bd69-baa0dedf7bbf","user_name":"acostantini","email":"a.costantini@cineca.it"}}
{"type":"node","id":"1","labels":["Institution"],"properties":{"name":"CINECA"}}
{"type":"node","id":"6","labels":["Blast","BlastSeq","Command"],"properties":{"blasttype":"blastn","blast_version":"2.15","status":"Complete",...}}
{"type":"relationship","id":"0","label":"WORKS_AT","start":{"id":"0","labels":["User"]},"end":{"id":"1","labels":["Institution"]}}
```

#### `export.csv`

Schema summary with index recommendations:

```csv
label,property,count,unique,index,existence,type,array,sample,left,right,other,otherLabels,elementType
"WORKS_AT","User",5,false,false,false,"RELATIONSHIP",false,null,1,0,"[""Institution""]",[],"relationship"
"RUNS","User",4,false,false,false,"RELATIONSHIP",true,null,5,0,"[""SearchbyTaxon"", ""Bold"", ""Command""]",[],"relationship"
"User","email",0,false,false,false,"STRING",false,null,0,0,[],[],"node"
```

#### `records.json`

Full schema snapshot with property metadata:

```json
[
  {
    "value": {
      "User": {
        "count": 5,
        "labels": [],
        "properties": {
          "lastName": {"unique": false, "indexed": false, "type": "STRING"},
          "email": {"unique": false, "indexed": false, "type": "STRING"}
        },
        "relationships": {
          "WORKS_AT": {"direction": "out", "labels": ["Institution"]},
          "RUNS": {"direction": "out", "labels": ["SearchbyTaxon", "Bold", "Command", "Blast"]}
        }
      }
    }
  }
]
```

### Populated Dataset

Located in `populated/`, this contains exports after running the population scripts:

#### `memgraph-query-results-export.csv` (~18,171 rows)

Complete label×property inventory of the populated graph:

```csv
label,property,count,unique,index,existence,type,array,sample,left,right,other,otherLabels,elementType
Blast,blast_version,186,false,false,false,STRING,false,,0,0,[],[],node
Blast,blasttype,186,false,false,false,STRING,false,,0,0,[],[],node
Blast,OUTPUT,186,false,false,false,RELATIONSHIP,false,,3,0,"[""File"", ""BlastDb"", ""BlastedSeq""]",[],node
User,firstName,200,false,false,false,STRING,false,,0,0,[],[],node
User,RUNS,200,false,false,false,RELATIONSHIP,false,,5,0,"[""Blast"", ""CreateDb"", ...]",[],node
```

The populated dataset demonstrates the scale:
- 200 Users
- 50 Institutions  
- ~186 Blast tasks (per property occurrence)
- Thousands of file nodes

---

## Usage Examples

### Basic Connection Test

```python
from db.memgraph_domain import get_memgraph

mg = get_memgraph()
print(f"Connected to Memgraph at {mg.host}:{mg.port}")

# Test query
result = mg.execute_and_fetch("MATCH (n) RETURN count(n) AS total")
for record in result:
    print(f"Total nodes: {record['total']}")
```

### Import Original Dataset

```python
from db.memgraph_domain.create_original_db import main

# Run the import
main()
# Output: ✔  Original dataset loaded into Memgraph
```

### Generate Synthetic Data

```python
from db.memgraph_domain.populate import (
    build_graph,
    persist_graph,
    create_from_original_and_populate
)

# Option 1: Build and persist graph
nodes, rels = build_graph()
print(f"Built {len(nodes)} nodes, {len(rels)} relationships")
persist_graph(nodes, rels, wipe=True)

# Option 2: Full workflow (original + synthetic)
create_from_original_and_populate(
    original_dir="db/memgraph_domain/original-dataset",
    wipe=True,
    users=500
)
```

### Query Users and Tasks

```python
from db.memgraph_domain import get_memgraph

mg = get_memgraph()

# Find all users at CINECA
query = """
MATCH (u:User)-[:WORKS_AT]->(i:Institution {name: 'CINECA'})
RETURN u.firstName, u.lastName, u.email
"""
for record in mg.execute_and_fetch(query):
    print(f"{record['u.firstName']} {record['u.lastName']}: {record['u.email']}")

# Find BLAST tasks with their outputs
query = """
MATCH (u:User)-[:RUNS]->(t:Blast)-[:OUTPUT]->(f:File)
RETURN u.user_name AS user, t.blasttype AS type, f.user_filename AS output
LIMIT 10
"""
for record in mg.execute_and_fetch(query):
    print(record)
```

### Job Progress Tracking

The populate script supports Redis-based progress tracking:

```python
import os
from db.memgraph_domain.populate import create_from_original_and_populate

# Set job ID for progress tracking
job_id = "my-job-123"

# Progress updates will be published to Redis at:
# - db:job:{job_id} - status updates
# - db:job:{job_id}:cancel - cancellation flag

create_from_original_and_populate(
    wipe=True,
    users=1000,
    job_id=job_id
)
```

---

## CLI Reference

### `db.memgraph_domain.populate`

```bash
python -m db.memgraph_domain.populate [OPTIONS]

Options:
  --users INT          Number of User nodes (default: 200)
  --institutions INT   Number of Institution nodes (default: 50)
  --max-tasks INT      Maximum tasks per user (default: 10)
  -h, --help           Show help message
```

Examples:

```bash
# Default settings
python -m db.memgraph_domain.populate

# Large dataset
python -m db.memgraph_domain.populate --users 1000 --institutions 200 --max-tasks 50

# Small test dataset
python -m db.memgraph_domain.populate --users 10 --institutions 5 --max-tasks 3
```

### `db.memgraph_domain.create_original_db`

```bash
# Import original dataset
python -c "from db.memgraph_domain.create_original_db import main; main()"
```

---

## Docker Deployment

### Build the Image

```bash
docker build -t cineca/db-populate -f db/memgraph_domain/Dockerfile .
```

### Run with Docker Compose

In your `docker-compose.yml`:

```yaml
services:
  memgraph:
    image: memgraph/memgraph-platform:latest
    ports:
      - "7687:7687"  # Bolt
      - "7474:7474"  # Lab UI
    volumes:
      - memgraph-data:/var/lib/memgraph

  db-populate:
    build:
      context: .
      dockerfile: db/memgraph_domain/Dockerfile
    environment:
      - MG_HOST=memgraph
      - MG_PORT=7687
      - NUM_USERS=200
    depends_on:
      - memgraph
    command: python -m db.populate

volumes:
  memgraph-data:
```

### Environment Variables

```bash
# Connection
MG_HOST=memgraph
MG_PORT=7687
MG_USER=
MG_PASSWORD=

# Generation
NUM_USERS=200
NUM_INSTITUTIONS=50
MAX_TASKS_PER_USER=10
MAX_INPUT_FILES=3

# Job tracking (optional)
DB_POPULATE_JOB_ID=job-123
```

---

## Integration with Main Application

### FastAPI Dependency

```python
# In src/dependencies.py
from db.memgraph_domain import get_memgraph

def get_graph_db():
    """Dependency for Memgraph client."""
    return get_memgraph()

# In routers
from fastapi import Depends

@router.get("/users")
async def list_users(mg = Depends(get_graph_db)):
    result = mg.execute_and_fetch("MATCH (u:User) RETURN u LIMIT 100")
    return [dict(r) for r in result]
```

### MCP Tool Integration

The Memgraph domain can be exposed as an MCP tool:

```python
# graph.query tool
async def invoke_graph_query(args: dict):
    mg = get_memgraph()
    cypher = args.get("cypher")
    result = mg.execute_and_fetch(cypher)
    return {"records": [dict(r) for r in result]}
```

### Health Checks

```python
# In src/health/checks.py
async def check_memgraph():
    try:
        mg = get_memgraph()
        mg.execute("RETURN 1")
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
```

---

## Troubleshooting

### Connection Issues

**Error**: `Connection refused on memgraph:7687`

```bash
# Check if Memgraph is running
docker ps | grep memgraph

# Check connectivity
nc -zv localhost 7687

# Verify environment
echo $MG_HOST $MG_PORT
```

**Solution**: Ensure Memgraph is running and `MG_HOST` is correct:
- Use `localhost` for local development
- Use `memgraph` for Docker Compose networks

### Import Errors

**Error**: `ModuleNotFoundError: No module named 'db'`

```bash
# Set PYTHONPATH
export PYTHONPATH=/path/to/project:$PYTHONPATH

# Or run as module
python -m db.memgraph_domain.populate
```

### Memory Issues

**Error**: `Out of memory during population`

```bash
# Reduce data size
python -m db.memgraph_domain.populate --users 50 --max-tasks 5

# Or increase Memgraph memory
docker run -e MEMGRAPH_MEMORY_LIMIT=4G memgraph/memgraph
```

### Index Errors

**Error**: `Index already exists`

This is normal and handled gracefully by `ensure_index()`.

### Transaction Errors

**Error**: `DDL not allowed inside transaction`

Solution: The populate script handles this by creating indexes with `autocommit=True` before starting the import transaction.

---

## API Reference

### `get_memgraph() -> Memgraph`

Returns a configured Memgraph client instance.

### `settings: Settings`

Pydantic settings object with configuration values.

### `populate(db=None, *, nodes=None, relationships=None, job_id=None) -> dict`

Programmatic data population.

**Parameters:**
- `db`: Memgraph client instance
- `nodes`: Optional list of node dicts
- `relationships`: Optional list of relationship dicts
- `job_id`: Optional job ID for progress tracking

**Returns:** `{"ok": True, "nodes": int, "relationships": int}`

### `build_graph() -> tuple[list[dict], list[tuple[str, str, str]]]`

Generate synthetic graph data without persisting.

**Returns:** `(nodes, relationships)` tuple

### `persist_graph(nodes, rels, *, wipe=False) -> None`

Persist nodes and relationships to Memgraph.

**Parameters:**
- `nodes`: List of node dicts
- `rels`: List of `(from_id, rel_type, to_id)` tuples
- `wipe`: Clear database before inserting

### `create_from_original_and_populate(original_dir, *, wipe=True, users=None, job_id=None) -> None`

Full workflow: import original dataset + synthetic data.

### `import_original_dataset(path) -> tuple[list, list, list]`

Load original dataset files.

**Returns:** `(nodes, relationships, index_hints)`

---

## License

This module is part of the Cineca Agentic Platform. See the main project [LICENSE](../../LICENSE) for details.

---

## Contributing

1. Follow the existing code style
2. Add tests for new functionality
3. Update this README for API changes
4. Run the population script to verify schema compatibility

---

## Changelog

See the main project [CHANGELOG.md](../../CHANGELOG.md) for version history.
