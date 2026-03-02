````markdown
# Runbook — Backup & Restore

## Overview

This runbook describes how to **safely back up and restore** the system’s core components:

- **Memgraph database**
- **Configuration files & environment variables**
- **Prometheus & Grafana data** (optional)
- **Application logs** (optional)

The procedures below are designed for both **scheduled backups** and **ad-hoc recovery** in incident scenarios.

---

## 1. Pre-Checks

Before performing backup or restore:

1. Verify you have **SSH access** to the target server.
2. Ensure **disk space** is sufficient for the backup (at least 2× current data size).
3. Confirm that **services are running normally** or, for restore, that you have a safe window to stop services.
4. Export environment variables:

```bash
export BACKUP_DIR=/opt/backups/$(date +%Y%m%d_%H%M%S)
export MEMGRAPH_DATA_DIR=/var/lib/memgraph
export CONFIG_DIR=/etc/mcp
export PROMETHEUS_DATA_DIR=/var/lib/prometheus
export GRAFANA_DATA_DIR=/var/lib/grafana
````

---

## 2. Backup Procedure

### 2.1 Create Backup Directory

```bash
mkdir -p "$BACKUP_DIR"
```

### 2.2 Stop Services (optional but recommended for consistency)

```bash
docker compose down
# or for systemd
sudo systemctl stop memgraph
sudo systemctl stop prometheus
sudo systemctl stop grafana-server
```

### 2.3 Backup Memgraph Data

```bash
tar -czf "$BACKUP_DIR/memgraph-data.tar.gz" -C "$MEMGRAPH_DATA_DIR" .
```

**Note:** If Memgraph is running in Docker:

```bash
docker run --rm \
  -v memgraph-data:/data \
  -v "$BACKUP_DIR":/backup \
  alpine tar -czf /backup/memgraph-data.tar.gz -C /data .
```

### 2.4 Backup Configuration

```bash
tar -czf "$BACKUP_DIR/config.tar.gz" -C "$CONFIG_DIR" .
cp .env "$BACKUP_DIR/.env" || echo "No .env found"
```

### 2.5 Backup Prometheus & Grafana Data (if persistence enabled)

```bash
tar -czf "$BACKUP_DIR/prometheus-data.tar.gz" -C "$PROMETHEUS_DATA_DIR" .
tar -czf "$BACKUP_DIR/grafana-data.tar.gz" -C "$GRAFANA_DATA_DIR" .
```

### 2.6 Backup Logs (optional)

```bash
tar -czf "$BACKUP_DIR/logs.tar.gz" /var/log/mcp || echo "No logs found"
```

### 2.7 Restart Services

```bash
docker compose up -d
# or
sudo systemctl start memgraph prometheus grafana-server
```

### 2.8 Verify Backup

```bash
ls -lh "$BACKUP_DIR"
```

---

## 3. Restore Procedure

⚠ **Warning:** This will overwrite existing data. Ensure you have confirmed downtime.

### 3.1 Stop Services

```bash
docker compose down
# or
sudo systemctl stop memgraph prometheus grafana-server
```

### 3.2 Restore Memgraph Data

```bash
rm -rf "$MEMGRAPH_DATA_DIR"/*
tar -xzf "$BACKUP_SOURCE/memgraph-data.tar.gz" -C "$MEMGRAPH_DATA_DIR"
```

If using Docker volumes:

```bash
docker run --rm \
  -v memgraph-data:/data \
  -v "$BACKUP_SOURCE":/backup \
  alpine sh -c "rm -rf /data/* && tar -xzf /backup/memgraph-data.tar.gz -C /data"
```

### 3.3 Restore Configuration

```bash
tar -xzf "$BACKUP_SOURCE/config.tar.gz" -C "$CONFIG_DIR"
cp "$BACKUP_SOURCE/.env" .env || echo "No .env to restore"
```

### 3.4 Restore Prometheus & Grafana Data (if applicable)

```bash
tar -xzf "$BACKUP_SOURCE/prometheus-data.tar.gz" -C "$PROMETHEUS_DATA_DIR"
tar -xzf "$BACKUP_SOURCE/grafana-data.tar.gz" -C "$GRAFANA_DATA_DIR"
```

### 3.5 Restore Logs (optional)

```bash
tar -xzf "$BACKUP_SOURCE/logs.tar.gz" -C /var/log/mcp
```

### 3.6 Restart Services

```bash
docker compose up -d
# or
sudo systemctl start memgraph prometheus grafana-server
```

---

## 4. Automation & Scheduling

### 4.1 Cron Example — Daily Backup at 02:00

```bash
0 2 * * * /usr/local/bin/mcp-backup.sh >> /var/log/mcp-backup.log 2>&1
```

Where `mcp-backup.sh` is a wrapper script implementing the above **backup procedure**.

---

## 5. Testing Backups

1. **Perform test restore** in a staging environment once per month.
2. Validate:

   * Memgraph starts successfully.
   * Configuration loads without errors.
   * Historical metrics are accessible (if Prometheus/Grafana data restored).

---

## 6. Troubleshooting

| Issue                                  | Possible Cause                             | Resolution                              |
| -------------------------------------- | ------------------------------------------ | --------------------------------------- |
| Backup file missing                    | Incorrect BACKUP\_DIR or permission denied | Check path, create dirs with `mkdir -p` |
| Restore fails due to file locks        | Service still running                      | Stop services before restore            |
| Prometheus data not restoring properly | Corruption or WAL mismatch                 | Try restoring without WAL files         |
| Grafana dashboards missing             | Restored data dir mismatch                 | Verify correct provisioning path        |

---

## 7. References

* [Memgraph Backup Documentation](https://memgraph.com/docs)
* [Prometheus Data Backup](https://prometheus.io/docs/prometheus/latest/storage/)
* [Grafana Backup & Restore](https://grafana.com/docs/grafana/latest/administration/backup/)
