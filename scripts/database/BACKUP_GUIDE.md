# Database Backup and Restore Scripts

This directory contains scripts for backing up and restoring the PostgreSQL database.

## Backup Script

**File:** `backup_database.sh`

### Features

- Automated daily backups using `pg_dump`
- Compressed backups (gzip) to save disk space
- Automatic retention management (keeps backups for 7 days by default)
- Timestamped backup files
- Optional S3 upload support

### Usage

```bash
# Run manually
./scripts/backup_database.sh

# Or configure environment variables first
export BACKUP_DIR="/path/to/backups"
export RETENTION_DAYS=14
export POSTGRES_HOST="postgres"
export POSTGRES_DB="cineca_agentic_platform"
export POSTGRES_USER="cineca"
export POSTGRES_PASSWORD="your_password"

./scripts/backup_database.sh
```

### Automated Daily Backups

To run backups automatically every day at 2 AM, add to crontab:

```bash
# Edit crontab
crontab -e

# Add this line:
0 2 * * * /path/to/Cineca-Agentic-Platform/scripts/backup_database.sh >> /var/log/db_backup.log 2>&1
```

Or use docker-compose to run as a scheduled job:

```yaml
services:
  backup:
    image: postgres:16
    container_name: db-backup
    environment:
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
      - POSTGRES_DB=cineca_agentic_platform
      - POSTGRES_USER=cineca
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - BACKUP_DIR=/backups
      - RETENTION_DAYS=7
    volumes:
      - ./backups:/backups
      - ./scripts:/scripts
    command: /bin/bash -c "while true; do /scripts/backup_database.sh; sleep 86400; done"
    depends_on:
      - postgres
```

### Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKUP_DIR` | `/backups/postgres` | Directory to store backups |
| `RETENTION_DAYS` | `7` | Number of days to keep old backups |
| `POSTGRES_HOST` | `postgres` | PostgreSQL hostname |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `cineca_agentic_platform` | Database name |
| `POSTGRES_USER` | `cineca` | Database user |
| `POSTGRES_PASSWORD` | (required) | Database password |

## Restore Script

**File:** `restore_database.sh`

### Features

- Restore from compressed backup files
- Safety confirmation before overwriting data
- Lists available backups if no file specified

### Usage

```bash
# List available backups
./scripts/restore_database.sh

# Restore from specific backup
./scripts/restore_database.sh /backups/postgres/backup_cineca_agentic_platform_20250102_120000.sql.gz

# With environment variables
export POSTGRES_HOST="postgres"
export POSTGRES_DB="cineca_agentic_platform"
export POSTGRES_USER="cineca"
export POSTGRES_PASSWORD="your_password"

./scripts/restore_database.sh /backups/postgres/backup_cineca_agentic_platform_20250102_120000.sql.gz
```

### Important Notes

⚠️ **WARNING:** Restoring a backup will **REPLACE ALL DATA** in the database. Always:

1. Backup current data before restoring
2. Verify the backup file is correct
3. Test in a non-production environment first
4. Confirm you understand the consequences

## Best Practices

### 1. Regular Backups

- Schedule daily backups at low-traffic times (e.g., 2 AM)
- Keep at least 7 days of backups
- Store backups in a different location from the database

### 2. Backup Verification

Regularly test your backups:

```bash
# Create a test database
docker compose exec postgres createdb -U cineca test_restore

# Restore to test database
export POSTGRES_DB=test_restore
./scripts/restore_database.sh /backups/postgres/backup_cineca_agentic_platform_20250102_120000.sql.gz

# Verify data
docker compose exec postgres psql -U cineca -d test_restore -c "SELECT COUNT(*) FROM tenants;"

# Clean up
docker compose exec postgres dropdb -U cineca test_restore
```

### 3. Off-site Backups

For production systems, also upload backups to cloud storage:

**AWS S3:**
```bash
# Uncomment the S3 upload section in backup_database.sh and configure:
export AWS_S3_BUCKET="my-backup-bucket"
aws s3 cp "$BACKUP_FILE" "s3://${AWS_S3_BUCKET}/backups/postgres/"
```

**Google Cloud Storage:**
```bash
gsutil cp "$BACKUP_FILE" "gs://my-backup-bucket/backups/postgres/"
```

### 4. Monitoring

Monitor backup success:

```bash
# Check last backup
ls -lth /backups/postgres/ | head -5

# Check backup log
tail -f /var/log/db_backup.log

# Alert on failures (example with email)
if ! ./scripts/backup_database.sh; then
    echo "Database backup failed!" | mail -s "ALERT: Backup Failure" admin@example.com
fi
```

## Troubleshooting

### Backup Fails with Permission Error

```bash
# Ensure backup directory is writable
mkdir -p /backups/postgres
chmod 755 /backups/postgres

# Or run with sudo
sudo ./scripts/backup_database.sh
```

### "pg_dump: command not found"

```bash
# Install PostgreSQL client tools
# Ubuntu/Debian:
sudo apt-get install postgresql-client

# macOS:
brew install postgresql

# Or use Docker:
docker run --rm -e POSTGRES_PASSWORD=password postgres:16 pg_dump --version
```

### Restore Hangs or Fails

```bash
# Check database connections
docker compose exec postgres psql -U cineca -d postgres -c "SELECT * FROM pg_stat_activity WHERE datname='cineca_agentic_platform';"

# Terminate connections before restore
docker compose exec postgres psql -U cineca -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='cineca_agentic_platform';"
```

## Recovery Scenarios

### Scenario 1: Accidental Data Deletion

1. Stop the application immediately
2. Find the most recent backup
3. Restore from backup
4. Verify data integrity
5. Restart application

### Scenario 2: Database Corruption

1. Identify the last known good backup
2. Create a backup of current state (for forensics)
3. Restore from last known good backup
4. Replay any missing transactions if needed

### Scenario 3: Disaster Recovery

1. Set up new database server
2. Configure connection parameters
3. Restore from off-site backup
4. Update application configuration
5. Verify all services are operational

## Additional Resources

- [PostgreSQL Backup Documentation](https://www.postgresql.org/docs/current/backup.html)
- [pg_dump Reference](https://www.postgresql.org/docs/current/app-pgdump.html)
- [Docker Postgres Backup Strategies](https://docs.docker.com/samples/postgres/)

---

**Last Updated:** November 2, 2025  
**Maintainer:** Cineca Agentic Platform Team
