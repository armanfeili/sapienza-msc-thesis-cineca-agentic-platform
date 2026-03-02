# Quickstart: Bulk Data Import

**Difficulty**: Intermediate  
**Time**: 20 minutes  
**Prerequisites**: Python 3.11+, Docker, valid OAuth2 token with `graph:query` scope

---

## Overview

This guide demonstrates how to efficiently import large datasets into Memgraph using batch operations, transactions, and best practices for performance and data integrity.

### What You'll Learn

- Batch insert strategies for high performance
- Transaction management for data consistency
- Error handling and rollback patterns
- Memory-efficient streaming imports
- Validation and data quality checks

---

## Setup

### 1. Prepare Your Data

Supported formats:
- **CSV**: Comma-separated values
- **JSON/NDJSON**: JSON or newline-delimited JSON
- **Parquet**: Columnar data format

Example CSV (`people.csv`):
```csv
name,age,email,company
Alice Johnson,30,alice@example.com,Acme Corp
Bob Smith,25,bob@example.com,Tech Inc
Charlie Brown,35,charlie@example.com,Data LLC
```

Example NDJSON (`people.ndjson`):
```json
{"name": "Alice Johnson", "age": 30, "email": "alice@example.com", "company": "Acme Corp"}
{"name": "Bob Smith", "age": 25, "email": "bob@example.com", "company": "Tech Inc"}
{"name": "Charlie Brown", "age": 35, "email": "charlie@example.com", "company": "Data LLC"}
```

### 2. Start Services

```bash
docker compose up -d
curl http://localhost:8000/health
```

### 3. Install Python Dependencies

```bash
pip install requests pandas tqdm python-dotenv
```

---

## Basic Bulk Import

### Strategy 1: Batch Inserts (Small to Medium Datasets)

For datasets < 10,000 rows, batch inserts are simplest:

```python
import requests
import pandas as pd
import os
from tqdm import tqdm

API_BASE = "http://localhost:8000/v1"
TOKEN = os.getenv("ACCESS_TOKEN")

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def batch_insert_people(csv_file: str, batch_size: int = 100):
    """Import people from CSV in batches"""
    
    # Load data
    df = pd.read_csv(csv_file)
    total_rows = len(df)
    
    print(f"Importing {total_rows} rows in batches of {batch_size}...")
    
    success_count = 0
    error_count = 0
    
    # Process in batches
    for i in tqdm(range(0, total_rows, batch_size)):
        batch = df.iloc[i:i+batch_size]
        
        # Build Cypher for batch
        cypher = "UNWIND $batch AS row\n"
        cypher += "CREATE (p:Person {name: row.name, age: row.age, email: row.email})\n"
        cypher += "WITH p, row\n"
        cypher += "MERGE (c:Company {name: row.company})\n"
        cypher += "CREATE (p)-[:WORKS_AT]->(c)\n"
        cypher += "RETURN count(p) AS created"
        
        # Convert batch to list of dicts
        batch_data = batch.to_dict('records')
        
        # Execute batch
        payload = {
            "action": "execute",
            "cypher": cypher,
            "params": {"batch": batch_data},
            "timeout": 60
        }
        
        try:
            response = requests.post(
                f"{API_BASE}/tools/graph.query/invoke",
                headers=headers,
                json=payload
            )
            
            result = response.json()
            
            if result["status"] == "success":
                created = result["results"][0]["created"]
                success_count += created
            else:
                print(f"Batch {i//batch_size + 1} failed: {result.get('message')}")
                error_count += len(batch)
                
        except Exception as e:
            print(f"Error in batch {i//batch_size + 1}: {e}")
            error_count += len(batch)
    
    print(f"\n✅ Import complete:")
    print(f"   Success: {success_count} rows")
    print(f"   Errors: {error_count} rows")
    
    return success_count, error_count

# Usage
batch_insert_people("people.csv", batch_size=100)
```

---

## Advanced Import Strategies

### Strategy 2: Transaction-Based Import (Data Integrity)

For critical data requiring rollback on errors:

```python
def transactional_import(csv_file: str):
    """Import with transaction support"""
    
    df = pd.read_csv(csv_file)
    
    # Start transaction
    cypher = "BEGIN TRANSACTION;\n"
    
    # Add all inserts
    for _, row in df.iterrows():
        cypher += f"""
        CREATE (p:Person {{
            name: '{row['name']}',
            age: {row['age']},
            email: '{row['email']}'
        }});
        """
    
    # Commit transaction
    cypher += "COMMIT;"
    
    payload = {
        "action": "execute",
        "cypher": cypher,
        "timeout": 300  # 5 minutes for large imports
    }
    
    try:
        response = requests.post(
            f"{API_BASE}/tools/graph.query/invoke",
            headers=headers,
            json=payload
        )
        
        result = response.json()
        
        if result["status"] == "success":
            print(f"✅ Transaction committed: {len(df)} rows imported")
        else:
            print(f"❌ Transaction rolled back: {result.get('message')}")
            
    except Exception as e:
        print(f"❌ Transaction failed: {e}")
        # Transaction automatically rolled back on error
```

### Strategy 3: Streaming Import (Memory-Efficient)

For very large datasets (> 100,000 rows):

```python
import json

def streaming_import(ndjson_file: str, batch_size: int = 500):
    """Memory-efficient streaming import from NDJSON"""
    
    batch = []
    total_imported = 0
    
    with open(ndjson_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            try:
                record = json.loads(line)
                batch.append(record)
                
                # Import when batch is full
                if len(batch) >= batch_size:
                    count = import_batch(batch)
                    total_imported += count
                    batch = []
                    
                    # Progress update
                    if line_num % 10000 == 0:
                        print(f"Processed {line_num:,} lines ({total_imported:,} imported)")
                        
            except json.JSONDecodeError as e:
                print(f"⚠️  Invalid JSON on line {line_num}: {e}")
                continue
    
    # Import remaining batch
    if batch:
        count = import_batch(batch)
        total_imported += count
    
    print(f"\n✅ Streaming import complete: {total_imported:,} rows")
    return total_imported

def import_batch(batch: list) -> int:
    """Import a batch of records"""
    
    cypher = """
    UNWIND $batch AS row
    CREATE (p:Person {name: row.name, age: row.age, email: row.email})
    RETURN count(p) AS created
    """
    
    payload = {
        "action": "execute",
        "cypher": cypher,
        "params": {"batch": batch}
    }
    
    response = requests.post(
        f"{API_BASE}/tools/graph.query/invoke",
        headers=headers,
        json=payload
    )
    
    result = response.json()
    
    if result["status"] == "success":
        return result["results"][0]["created"]
    else:
        print(f"⚠️  Batch failed: {result.get('message')}")
        return 0

# Usage
streaming_import("large_dataset.ndjson", batch_size=500)
```

---

## Data Validation

### Pre-Import Validation

```python
def validate_data(df: pd.DataFrame) -> tuple[bool, list]:
    """Validate data before import"""
    
    errors = []
    
    # Check required columns
    required_cols = ['name', 'age', 'email']
    missing = set(required_cols) - set(df.columns)
    if missing:
        errors.append(f"Missing columns: {missing}")
    
    # Check for nulls
    null_counts = df[required_cols].isnull().sum()
    if null_counts.any():
        errors.append(f"Null values found: {null_counts[null_counts > 0].to_dict()}")
    
    # Check data types
    if not pd.api.types.is_integer_dtype(df['age']):
        errors.append("'age' column must be integer")
    
    # Check email format
    email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    invalid_emails = ~df['email'].str.match(email_pattern)
    if invalid_emails.any():
        errors.append(f"{invalid_emails.sum()} invalid email addresses")
    
    # Check duplicates
    duplicates = df.duplicated(subset=['email']).sum()
    if duplicates > 0:
        errors.append(f"{duplicates} duplicate emails found")
    
    is_valid = len(errors) == 0
    return is_valid, errors

# Usage
df = pd.read_csv("people.csv")
is_valid, errors = validate_data(df)

if is_valid:
    print("✅ Data validation passed")
    batch_insert_people("people.csv")
else:
    print("❌ Data validation failed:")
    for error in errors:
        print(f"  - {error}")
```

### Post-Import Verification

```python
def verify_import(expected_count: int):
    """Verify import success"""
    
    # Count imported nodes
    cypher = "MATCH (p:Person) RETURN count(p) AS total"
    
    payload = {
        "action": "execute",
        "cypher": cypher
    }
    
    response = requests.post(
        f"{API_BASE}/tools/graph.query/invoke",
        headers=headers,
        json=payload
    )
    
    result = response.json()
    actual_count = result["results"][0]["total"]
    
    if actual_count == expected_count:
        print(f"✅ Verification passed: {actual_count} nodes created")
    else:
        print(f"⚠️  Count mismatch: expected {expected_count}, got {actual_count}")
    
    # Check for orphan nodes (no relationships)
    cypher_orphans = """
    MATCH (p:Person)
    WHERE NOT (p)--()
    RETURN count(p) AS orphans
    """
    
    payload = {"action": "execute", "cypher": cypher_orphans}
    response = requests.post(
        f"{API_BASE}/tools/graph.query/invoke",
        headers=headers,
        json=payload
    )
    
    result = response.json()
    orphan_count = result["results"][0]["orphans"]
    
    if orphan_count > 0:
        print(f"⚠️  Found {orphan_count} orphan nodes (no relationships)")

# Usage
verify_import(expected_count=1000)
```

---

## Performance Optimization

### 1. Use UNWIND for Batch Inserts

```python
# ✅ FAST: Single query with UNWIND
cypher = """
UNWIND $batch AS row
CREATE (p:Person {name: row.name, age: row.age})
"""
# Creates 1000 nodes in ~50ms

# ❌ SLOW: Individual queries
for row in batch:
    cypher = f"CREATE (p:Person {{name: '{row['name']}', age: {row['age']}})"
# Creates 1000 nodes in ~5000ms (100x slower)
```

### 2. Use MERGE for Upserts

```python
# Idempotent import (can run multiple times)
cypher = """
UNWIND $batch AS row
MERGE (p:Person {email: row.email})
ON CREATE SET p.name = row.name, p.age = row.age, p.created_at = timestamp()
ON MATCH SET p.name = row.name, p.age = row.age, p.updated_at = timestamp()
"""
```

### 3. Create Indexes Before Import

```python
def create_indexes():
    """Create indexes for faster lookups"""
    
    indexes = [
        "CREATE INDEX ON :Person(email)",
        "CREATE INDEX ON :Person(name)",
        "CREATE INDEX ON :Company(name)",
    ]
    
    for index_query in indexes:
        payload = {"action": "execute", "cypher": index_query}
        response = requests.post(
            f"{API_BASE}/tools/graph.query/invoke",
            headers=headers,
            json=payload
        )
        print(f"✅ Created index: {index_query}")

# Run before import
create_indexes()
```

### 4. Optimize Batch Size

```python
import time

def find_optimal_batch_size(df: pd.DataFrame):
    """Benchmark different batch sizes"""
    
    test_sizes = [50, 100, 500, 1000, 5000]
    results = {}
    
    for batch_size in test_sizes:
        start = time.time()
        
        # Test import
        test_df = df.head(min(len(df), batch_size * 3))
        success, _ = batch_insert_people_df(test_df, batch_size)
        
        elapsed = time.time() - start
        throughput = success / elapsed if elapsed > 0 else 0
        
        results[batch_size] = {
            "time": elapsed,
            "throughput": throughput,
            "rows": success
        }
        
        print(f"Batch size {batch_size}: {throughput:.0f} rows/sec")
    
    # Find best throughput
    best_size = max(results, key=lambda k: results[k]["throughput"])
    print(f"\n✅ Optimal batch size: {best_size}")
    
    return best_size
```

---

## Error Handling

### Robust Import with Retry Logic

```python
import time

def import_with_retry(batch: list, max_retries: int = 3):
    """Import batch with exponential backoff retry"""
    
    for attempt in range(max_retries):
        try:
            count = import_batch(batch)
            return count
            
        except requests.Timeout:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"⏱️  Timeout. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"❌ Max retries exceeded")
                raise
                
        except requests.ConnectionError:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"🔌 Connection error. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
    
    return 0
```

### Failed Batch Recovery

```python
def import_with_recovery(csv_file: str, batch_size: int = 100):
    """Import with failed batch tracking"""
    
    df = pd.read_csv(csv_file)
    failed_batches = []
    
    for i in range(0, len(df), batch_size):
        batch = df.iloc[i:i+batch_size]
        
        try:
            count = import_batch(batch.to_dict('records'))
            print(f"✅ Batch {i//batch_size + 1}: {count} rows")
            
        except Exception as e:
            print(f"❌ Batch {i//batch_size + 1} failed: {e}")
            failed_batches.append({
                "batch_num": i//batch_size + 1,
                "start_idx": i,
                "end_idx": min(i + batch_size, len(df)),
                "error": str(e)
            })
    
    # Save failed batches for manual review
    if failed_batches:
        import json
        with open("failed_batches.json", "w") as f:
            json.dump(failed_batches, f, indent=2)
        
        print(f"\n⚠️  {len(failed_batches)} batches failed")
        print(f"   Details saved to failed_batches.json")
    else:
        print("\n✅ All batches imported successfully")
```

---

## Best Practices

### ✅ DO

- Validate data before import
- Use batch inserts with UNWIND
- Create indexes before importing large datasets
- Use MERGE for idempotent imports
- Monitor memory usage for very large imports
- Log progress for long-running imports
- Verify import with count checks
- Handle errors gracefully with retry logic

### ❌ DON'T

- Don't import one row at a time (use batches)
- Don't skip data validation
- Don't use string interpolation (use params)
- Don't ignore errors silently
- Don't exceed available memory
- Don't create indexes after import (slower)
- Don't skip verification

---

## Complete Example

```python
#!/usr/bin/env python3
"""Complete bulk import example"""

import requests
import pandas as pd
import os
import time
from tqdm import tqdm

API_BASE = "http://localhost:8000/v1"
TOKEN = os.getenv("ACCESS_TOKEN")

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def main():
    csv_file = "people.csv"
    batch_size = 500
    
    print("🚀 Starting bulk import...")
    
    # Step 1: Load and validate
    print("\n1️⃣  Loading data...")
    df = pd.read_csv(csv_file)
    print(f"   Loaded {len(df):,} rows")
    
    print("\n2️⃣  Validating data...")
    is_valid, errors = validate_data(df)
    if not is_valid:
        print("❌ Validation failed:")
        for error in errors:
            print(f"  - {error}")
        return
    print("   ✅ Validation passed")
    
    # Step 2: Create indexes
    print("\n3️⃣  Creating indexes...")
    create_indexes()
    
    # Step 3: Import
    print(f"\n4️⃣  Importing {len(df):,} rows in batches of {batch_size}...")
    start_time = time.time()
    
    success, errors = batch_insert_people("people.csv", batch_size)
    
    elapsed = time.time() - start_time
    throughput = success / elapsed if elapsed > 0 else 0
    
    print(f"\n   ⏱️  Time: {elapsed:.2f}s")
    print(f"   📊 Throughput: {throughput:.0f} rows/sec")
    
    # Step 4: Verify
    print("\n5️⃣  Verifying import...")
    verify_import(expected_count=len(df))
    
    print("\n✅ Import complete!")

if __name__ == "__main__":
    main()
```

---

## Troubleshooting

### Issue: "Out of memory"

**Solution**: Use streaming import or smaller batch sizes

```python
# Reduce batch size
streaming_import("large_file.ndjson", batch_size=100)
```

### Issue: "Timeout errors"

**Solution**: Increase timeout or use smaller batches

```python
payload = {
    "action": "execute",
    "cypher": cypher,
    "timeout": 300  # 5 minutes
}
```

### Issue: "Duplicate nodes created"

**Solution**: Use MERGE instead of CREATE

```python
cypher = "MERGE (p:Person {email: $email}) SET p.name = $name"
```

---

## Next Steps

- **Archive/Restore**: [archive-restore.md](./archive-restore.md)
- **Secure Queries**: [secure-nl-to-cypher.md](./secure-nl-to-cypher.md)
- **MCP Tools**: [../mcp/TOOLS_REFERENCE.md](../mcp/TOOLS_REFERENCE.md)
