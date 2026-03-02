# Quickstart: Archive & Restore Operations

**Difficulty**: Advanced  
**Time**: 25 minutes  
**Prerequisites**: Python 3.11+, Docker, admin OAuth2 token with `ops:backup` and `ops:restore` scopes

---

## Overview

This guide demonstrates how to safely backup and restore your Memgraph database, PostgreSQL control data, and Redis cache using the platform's built-in archive and restore tools.

### What You'll Learn

- Create full system backups
- Restore from backups with validation
- Schedule automated backups
- Implement disaster recovery procedures
- Handle backup encryption and compression

---

## Setup

### 1. Prerequisites

```bash
# Ensure you have admin credentials
export AUTH0_ADMIN_USERNAME="admin@example.com"
export AUTH0_ADMIN_PASSWORD="your-secure-password"

# Generate admin token with backup/restore scopes
python scripts/generate_test_token.py --admin
```

### 2. Configure Backup Storage

Edit `.env`:
```bash
# Backup configuration
BACKUP_DIR=/opt/backups
BACKUP_RETENTION_DAYS=30
BACKUP_COMPRESSION=gzip
BACKUP_ENCRYPTION_ENABLED=true
```

### 3. Create Backup Directory

```bash
mkdir -p /opt/backups
chmod 700 /opt/backups  # Restrict access
```

---

## Basic Backup Operations

### Create Manual Backup

```python
import requests
import os
from datetime import datetime

API_BASE = "http://localhost:8000/v1"
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

headers = {
    "Authorization": f"Bearer {ADMIN_TOKEN}",
    "Content-Type": "application/json"
}

def create_backup(backup_name: str = None, include_metadata: bool = True):
    """Create a full system backup"""
    
    if backup_name is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"backup_{timestamp}"
    
    payload = {
        "action": "create",
        "backup_name": backup_name,
        "include_metadata": include_metadata,
        "compression": "gzip",
        "encryption": True
    }
    
    print(f"🔄 Creating backup: {backup_name}...")
    
    response = requests.post(
        f"{API_BASE}/tools/ops.backup/invoke",
        headers=headers,
        json=payload,
        timeout=300  # 5 minutes
    )
    
    result = response.json()
    
    if result["status"] == "success":
        print(f"✅ Backup created successfully")
        print(f"   Backup ID: {result['backup_id']}")
        print(f"   Size: {result['size_bytes'] / 1024 / 1024:.2f} MB")
        print(f"   Location: {result['location']}")
        return result
    else:
        print(f"❌ Backup failed: {result.get('message')}")
        return None

# Create backup
backup = create_backup()
```

**Example Output**:
```
🔄 Creating backup: backup_20251026_200000...
✅ Backup created successfully
   Backup ID: backup_20251026_200000
   Size: 125.45 MB
   Location: /opt/backups/backup_20251026_200000.tar.gz.enc
```

---

## Restore Operations

### List Available Backups

```python
def list_backups():
    """List all available backups"""
    
    payload = {"action": "list"}
    
    response = requests.post(
        f"{API_BASE}/tools/ops.backup/invoke",
        headers=headers,
        json=payload
    )
    
    result = response.json()
    
    if result["status"] == "success":
        backups = result["backups"]
        
        print(f"📦 Available backups: {len(backups)}")
        print()
        
        for backup in backups:
            print(f"  ID: {backup['backup_id']}")
            print(f"  Created: {backup['created_at']}")
            print(f"  Size: {backup['size_bytes'] / 1024 / 1024:.2f} MB")
            print(f"  Status: {backup['status']}")
            print()
        
        return backups
    else:
        print(f"❌ Failed to list backups: {result.get('message')}")
        return []

# List backups
backups = list_backups()
```

### Restore from Backup

```python
def restore_backup(backup_id: str, verify: bool = True, dry_run: bool = False):
    """Restore from a backup"""
    
    # WARNING: This is a destructive operation!
    if not dry_run:
        confirm = input(f"⚠️  This will replace ALL data with backup {backup_id}. Type 'yes' to confirm: ")
        if confirm != "yes":
            print("❌ Restore cancelled")
            return None
    
    payload = {
        "action": "execute",
        "backup_id": backup_id,
        "verify": verify,
        "dry_run": dry_run
    }
    
    print(f"🔄 Restoring from backup: {backup_id}...")
    
    response = requests.post(
        f"{API_BASE}/tools/ops.restore/invoke",
        headers=headers,
        json=payload,
        timeout=600  # 10 minutes
    )
    
    result = response.json()
    
    if result["status"] == "success":
        if dry_run:
            print(f"✅ Dry run successful - restore would work")
        else:
            print(f"✅ Restore completed successfully")
        
        print(f"   Nodes restored: {result['stats']['nodes']}")
        print(f"   Relationships restored: {result['stats']['relationships']}")
        print(f"   Execution time: {result['execution_time_ms'] / 1000:.2f}s")
        
        if verify and result.get('verification'):
            print(f"   Verification: {'✅ PASS' if result['verification']['passed'] else '❌ FAIL'}")
        
        return result
    else:
        print(f"❌ Restore failed: {result.get('message')}")
        return None

# Dry run first to verify
restore_backup("backup_20251026_200000", dry_run=True)

# Actual restore
# restore_backup("backup_20251026_200000", verify=True, dry_run=False)
```

---

## Automated Backup Scheduling

### Using Cron (Linux/macOS)

Create backup script (`/opt/scripts/auto_backup.py`):

```python
#!/usr/bin/env python3
"""Automated backup script"""

import requests
import os
import sys
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    filename='/var/log/cineca_backups.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

API_BASE = "http://localhost:8000/v1"
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

def create_automated_backup():
    """Create automated backup with error handling"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"auto_backup_{timestamp}"
    
    headers = {
        "Authorization": f"Bearer {ADMIN_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "action": "create",
        "backup_name": backup_name,
        "include_metadata": True,
        "compression": "gzip",
        "encryption": True
    }
    
    try:
        logging.info(f"Starting automated backup: {backup_name}")
        
        response = requests.post(
            f"{API_BASE}/tools/ops.backup/invoke",
            headers=headers,
            json=payload,
            timeout=300
        )
        
        result = response.json()
        
        if result["status"] == "success":
            size_mb = result['size_bytes'] / 1024 / 1024
            logging.info(f"Backup successful: {backup_name} ({size_mb:.2f} MB)")
            
            # Cleanup old backups
            cleanup_old_backups(retention_days=30)
            
            return 0
        else:
            logging.error(f"Backup failed: {result.get('message')}")
            return 1
            
    except Exception as e:
        logging.error(f"Backup exception: {e}")
        return 1

def cleanup_old_backups(retention_days: int = 30):
    """Delete backups older than retention period"""
    
    payload = {
        "action": "cleanup",
        "retention_days": retention_days
    }
    
    headers = {
        "Authorization": f"Bearer {ADMIN_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            f"{API_BASE}/tools/ops.backup/invoke",
            headers=headers,
            json=payload
        )
        
        result = response.json()
        
        if result["status"] == "success":
            deleted = result.get("deleted_count", 0)
            logging.info(f"Cleaned up {deleted} old backups")
        
    except Exception as e:
        logging.warning(f"Cleanup failed: {e}")

if __name__ == "__main__":
    sys.exit(create_automated_backup())
```

Make it executable:
```bash
chmod +x /opt/scripts/auto_backup.py
```

Add to crontab:
```bash
crontab -e
```

```cron
# Daily backup at 2 AM
0 2 * * * /opt/scripts/auto_backup.py

# Weekly full backup on Sunday at 3 AM
0 3 * * 0 /opt/scripts/auto_backup.py
```

---

## Disaster Recovery

### Complete Recovery Procedure

```python
def disaster_recovery(backup_id: str):
    """Complete disaster recovery workflow"""
    
    print("🚨 DISASTER RECOVERY PROCEDURE")
    print("=" * 50)
    
    # Step 1: Verify backup exists
    print("\n1️⃣  Verifying backup...")
    payload = {"action": "list"}
    response = requests.post(
        f"{API_BASE}/tools/ops.backup/invoke",
        headers=headers,
        json=payload
    )
    
    result = response.json()
    backups = [b for b in result["backups"] if b["backup_id"] == backup_id]
    
    if not backups:
        print(f"❌ Backup {backup_id} not found")
        return False
    
    backup = backups[0]
    print(f"✅ Backup found: {backup['created_at']}, {backup['size_bytes'] / 1024 / 1024:.2f} MB")
    
    # Step 2: Stop application services
    print("\n2️⃣  Stopping application services...")
    os.system("docker compose stop app")
    
    # Step 3: Dry run restore
    print("\n3️⃣  Testing restore (dry run)...")
    payload = {
        "action": "execute",
        "backup_id": backup_id,
        "verify": True,
        "dry_run": True
    }
    
    response = requests.post(
        f"{API_BASE}/tools/ops.restore/invoke",
        headers=headers,
        json=payload
    )
    
    result = response.json()
    
    if result["status"] != "success":
        print(f"❌ Dry run failed: {result.get('message')}")
        os.system("docker compose start app")
        return False
    
    print("✅ Dry run passed")
    
    # Step 4: Confirm restore
    print("\n4️⃣  Ready to restore")
    confirm = input("Type 'RESTORE' to proceed: ")
    
    if confirm != "RESTORE":
        print("❌ Recovery cancelled")
        os.system("docker compose start app")
        return False
    
    # Step 5: Execute restore
    print("\n5️⃣  Executing restore...")
    payload = {
        "action": "execute",
        "backup_id": backup_id,
        "verify": True,
        "dry_run": False
    }
    
    response = requests.post(
        f"{API_BASE}/tools/ops.restore/invoke",
        headers=headers,
        json=payload,
        timeout=600
    )
    
    result = response.json()
    
    if result["status"] != "success":
        print(f"❌ Restore failed: {result.get('message')}")
        return False
    
    print("✅ Restore completed")
    
    # Step 6: Restart services
    print("\n6️⃣  Restarting services...")
    os.system("docker compose start app")
    
    # Step 7: Verify system health
    print("\n7️⃣  Verifying system health...")
    import time
    time.sleep(10)  # Wait for services to start
    
    health_response = requests.get(f"{API_BASE.replace('/v1', '')}/health")
    if health_response.status_code == 200:
        print("✅ System is healthy")
    else:
        print("⚠️  System health check failed")
    
    print("\n✅ DISASTER RECOVERY COMPLETE")
    return True

# Usage
# disaster_recovery("backup_20251026_200000")
```

---

## Backup Validation

### Verify Backup Integrity

```python
def verify_backup_integrity(backup_id: str):
    """Verify backup file integrity"""
    
    payload = {
        "action": "verify",
        "backup_id": backup_id
    }
    
    print(f"🔍 Verifying backup integrity: {backup_id}...")
    
    response = requests.post(
        f"{API_BASE}/tools/ops.backup/invoke",
        headers=headers,
        json=payload
    )
    
    result = response.json()
    
    if result["status"] == "success":
        checks = result["verification"]
        
        print(f"✅ Backup integrity verified")
        print(f"   Checksum: {'✅ Valid' if checks['checksum_valid'] else '❌ Invalid'}")
        print(f"   Encryption: {'✅ Valid' if checks['encryption_valid'] else '❌ Invalid'}")
        print(f"   Structure: {'✅ Valid' if checks['structure_valid'] else '❌ Invalid'}")
        
        if checks.get('metadata'):
            meta = checks['metadata']
            print(f"   Created: {meta['created_at']}")
            print(f"   Platform version: {meta['platform_version']}")
            print(f"   Database version: {meta['database_version']}")
        
        return checks['checksum_valid'] and checks['encryption_valid'] and checks['structure_valid']
    else:
        print(f"❌ Verification failed: {result.get('message')}")
        return False

# Verify backup
verify_backup_integrity("backup_20251026_200000")
```

---

## Best Practices

### 1. Regular Backup Schedule

```python
# Recommended schedule:
# - Daily incremental backups
# - Weekly full backups
# - Monthly archive backups (long-term retention)

def backup_strategy():
    """Implement 3-2-1 backup strategy"""
    
    day_of_week = datetime.now().weekday()
    day_of_month = datetime.now().day
    
    if day_of_month == 1:
        # Monthly archive backup
        create_backup(f"archive_{datetime.now().strftime('%Y%m')}", include_metadata=True)
    elif day_of_week == 0:
        # Weekly full backup
        create_backup(f"weekly_{datetime.now().strftime('%Y%m%d')}", include_metadata=True)
    else:
        # Daily incremental backup
        create_backup(f"daily_{datetime.now().strftime('%Y%m%d')}", include_metadata=False)
```

### 2. Test Restores Regularly

```python
def test_restore_monthly():
    """Monthly restore test to verify backups"""
    
    # Get most recent backup
    backups = list_backups()
    if not backups:
        print("❌ No backups available to test")
        return
    
    latest = backups[0]
    
    print(f"🧪 Testing restore from: {latest['backup_id']}")
    
    # Dry run restore
    result = restore_backup(latest['backup_id'], verify=True, dry_run=True)
    
    if result and result['verification']['passed']:
        print("✅ Monthly restore test PASSED")
        
        # Log success
        logging.info(f"Monthly restore test passed: {latest['backup_id']}")
    else:
        print("❌ Monthly restore test FAILED")
        
        # Alert administrators
        send_alert("Backup restore test failed", latest['backup_id'])

# Schedule this to run monthly
```

### 3. Encrypt Sensitive Backups

```python
def create_encrypted_backup():
    """Create encrypted backup with custom key"""
    
    # Use environment variable for encryption key
    encryption_key = os.getenv("BACKUP_ENCRYPTION_KEY")
    
    if not encryption_key:
        print("⚠️  No encryption key found. Using default.")
    
    payload = {
        "action": "create",
        "backup_name": f"secure_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "encryption": True,
        "encryption_key": encryption_key,
        "compression": "gzip"
    }
    
    response = requests.post(
        f"{API_BASE}/tools/ops.backup/invoke",
        headers=headers,
        json=payload
    )
    
    return response.json()
```

### 4. Off-Site Backup Replication

```python
def replicate_to_s3(backup_id: str):
    """Replicate backup to S3 for off-site storage"""
    
    import boto3
    
    s3 = boto3.client('s3')
    bucket_name = "cineca-backups"
    
    # Get local backup file
    backup_file = f"/opt/backups/{backup_id}.tar.gz.enc"
    
    # Upload to S3
    print(f"☁️  Uploading to S3: {bucket_name}/{backup_id}")
    
    s3.upload_file(
        backup_file,
        bucket_name,
        f"backups/{backup_id}.tar.gz.enc"
    )
    
    print("✅ Off-site replication complete")

# After creating backup
backup = create_backup()
if backup:
    replicate_to_s3(backup['backup_id'])
```

---

## Monitoring & Alerts

### Backup Monitoring Script

```python
def monitor_backup_health():
    """Monitor backup health and send alerts"""
    
    # Check for recent backups
    backups = list_backups()
    
    if not backups:
        send_alert("CRITICAL", "No backups found!")
        return
    
    latest = backups[0]
    latest_time = datetime.fromisoformat(latest['created_at'])
    age_hours = (datetime.now() - latest_time).total_seconds() / 3600
    
    # Alert if no backup in last 48 hours
    if age_hours > 48:
        send_alert("WARNING", f"Last backup is {age_hours:.1f} hours old")
    
    # Check backup sizes (detect anomalies)
    if len(backups) >= 5:
        sizes = [b['size_bytes'] for b in backups[:5]]
        avg_size = sum(sizes) / len(sizes)
        
        if latest['size_bytes'] < avg_size * 0.5:
            send_alert("WARNING", f"Latest backup is unusually small: {latest['size_bytes'] / 1024 / 1024:.2f} MB")
        elif latest['size_bytes'] > avg_size * 2:
            send_alert("INFO", f"Latest backup is unusually large: {latest['size_bytes'] / 1024 / 1024:.2f} MB")
    
    print("✅ Backup monitoring complete")

def send_alert(severity: str, message: str):
    """Send alert via email/Slack/etc."""
    
    print(f"🚨 ALERT [{severity}]: {message}")
    
    # Implement your alerting mechanism
    # - Email
    # - Slack webhook
    # - PagerDuty
    # - etc.
```

---

## Troubleshooting

### Issue: "Backup creation timeout"

**Problem**: Backup takes longer than timeout

**Solution**:
```python
# Increase timeout for large databases
payload = {
    "action": "create",
    "backup_name": "large_backup",
    "timeout": 900  # 15 minutes
}
```

### Issue: "Insufficient disk space"

**Problem**: Not enough space for backup

**Solution**:
```bash
# Check disk space
df -h /opt/backups

# Clean up old backups
curl -X POST http://localhost:8000/v1/tools/ops.backup/invoke \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"action": "cleanup", "retention_days": 7}'
```

### Issue: "Restore verification failed"

**Problem**: Restored data doesn't match backup

**Solution**:
```python
# Check backup integrity first
verify_backup_integrity("backup_id")

# Try restoring to a test environment
restore_backup("backup_id", verify=True, dry_run=True)
```

---

## Security Checklist

- ✅ Use encrypted backups for sensitive data
- ✅ Store encryption keys separately from backups
- ✅ Implement off-site backup replication (3-2-1 rule)
- ✅ Test restore procedures regularly (at least monthly)
- ✅ Restrict backup file permissions (chmod 600)
- ✅ Audit backup access logs
- ✅ Use admin-only tokens for backup/restore operations
- ✅ Document disaster recovery procedures
- ✅ Monitor backup health and age
- ✅ Rotate encryption keys periodically

---

## Next Steps

- **Bulk Import**: [bulk-import.md](./bulk-import.md)
- **Secure Queries**: [secure-nl-to-cypher.md](./secure-nl-to-cypher.md)
- **Runbooks**: [../ops/runbooks/](../ops/runbooks/)
- **Security**: [../security.md](../security.md)
