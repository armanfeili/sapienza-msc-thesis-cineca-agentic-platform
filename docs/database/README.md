# Database Documentation

This directory contains documentation for all database systems used in the Cineca Agentic Platform.

## 📚 Database Systems

The platform uses three database systems:

### PostgreSQL
Primary relational database for structured data.

**Documentation:**
- **DATABASE_POSTGRESQL_REFERENCE.md** - PostgreSQL reference and schema
- **POSTGRES_FILES_REORGANIZATION.md** - File organization in PostgreSQL
- Migration guides and implementation docs

### Redis
In-memory data store for caching, job queues, and session management.

**Documentation:**
- **DATABASE_REDIS_REFERENCE.md** - Redis reference and key patterns
- **REDIS_CACHE_REFERENCE.md** - Redis caching implementation
- **REDIS_KEYS_INTERNAL.md** - Internal Redis key structure
- **REDIS_MIGRATION.md** - Redis migration guide
- **redis-job-store-production.md** - Production job store setup
- **redis-job-store-quickstart.md** - Job store quick start

### Memgraph
Graph database for relationship and graph-based queries.

**Documentation:**
- **DATABASE_MEMGRAPH_REFERENCE.md** - Memgraph reference and usage

---

## 🗄️ Database Usage by Feature

### PostgreSQL
Used for:
- User accounts and authentication
- Agent configurations
- Job definitions and history
- Model instances and providers
- Tenant data
- Configuration and settings

### Redis
Used for:
- Job queue management
- Session storage
- Cache layer
- Rate limiting counters
- Real-time data

### Memgraph
Used for:
- Graph-based queries
- Relationship mapping
- Knowledge graphs
- Graph tool operations

---

## 📖 Implementation Guides

### Database Integration
- **TOOLS_POSTGRES_REDIS_IMPLEMENTATION.md** - Tools database implementation

### Migration Guides
- **POSTGRES_FILES_REORGANIZATION.md** - PostgreSQL reorganization
- **REDIS_MIGRATION.md** - Redis migration procedures

### Job Store
- **redis-job-store-production.md** - Production job store configuration
- **redis-job-store-quickstart.md** - Quick start for job store

---

## 🔧 Database Operations

### For Developers

**PostgreSQL:**
1. Review schema: [DATABASE_POSTGRESQL_REFERENCE.md](./DATABASE_POSTGRESQL_REFERENCE.md)
2. Implementation: [TOOLS_POSTGRES_REDIS_IMPLEMENTATION.md](./TOOLS_POSTGRES_REDIS_IMPLEMENTATION.md)

**Redis:**
1. Key patterns: [REDIS_KEYS_INTERNAL.md](./REDIS_KEYS_INTERNAL.md)
2. Caching: [REDIS_CACHE_REFERENCE.md](./REDIS_CACHE_REFERENCE.md)
3. Job store: [redis-job-store-quickstart.md](./redis-job-store-quickstart.md)

**Memgraph:**
1. Reference: [DATABASE_MEMGRAPH_REFERENCE.md](./DATABASE_MEMGRAPH_REFERENCE.md)
2. Graph tools: [../features/graph-tools/](../features/graph-tools/)

### For Operators

**Setup:**
1. PostgreSQL configuration
2. Redis setup: [redis-job-store-production.md](./redis-job-store-production.md)
3. Memgraph deployment

**Migrations:**
1. Review: [REDIS_MIGRATION.md](./REDIS_MIGRATION.md)
2. Follow: [POSTGRES_FILES_REORGANIZATION.md](./POSTGRES_FILES_REORGANIZATION.md)

**Monitoring:**
- Database metrics: [../operations/monitoring/](../operations/monitoring/)
- Performance: [../operations/monitoring/PERFORMANCE_TESTING.md](../operations/monitoring/PERFORMANCE_TESTING.md)

---

## 🔗 Related Documentation

### Features Using Databases
- [Jobs](../features/jobs/) - Job storage and queuing
- [Agents](../features/agents/) - Agent configurations
- [Models](../features/models/) - Model instances
- [Providers](../features/providers/) - Provider data
- [Tenants](../features/tenants/) - Multi-tenancy data
- [Graph Tools](../features/graph-tools/) - Graph database usage

### Operations
- [Deployment](../operations/deployment/) - Database deployment
- [Monitoring](../operations/monitoring/) - Database monitoring
- [Disaster Recovery](../operations/monitoring/DISASTER_RECOVERY.md) - Database backup and recovery

### Development
- [Architecture](../architecture/) - Database architecture
- [Migration Guide](../implementation/) - Migration procedures

---

## 📊 Database Schema References

### Quick Reference Tables

**PostgreSQL Tables:**
- Users and authentication
- Agents, jobs, models, providers
- Tenants and configurations
- See [DATABASE_POSTGRESQL_REFERENCE.md](./DATABASE_POSTGRESQL_REFERENCE.md) for complete schema

**Redis Key Patterns:**
- `job:*` - Job queue keys
- `cache:*` - Cache keys
- `session:*` - Session keys
- `ratelimit:*` - Rate limit counters
- See [REDIS_KEYS_INTERNAL.md](./REDIS_KEYS_INTERNAL.md) for complete patterns

**Memgraph:**
- Graph nodes and relationships
- See [DATABASE_MEMGRAPH_REFERENCE.md](./DATABASE_MEMGRAPH_REFERENCE.md) for details

---

## 🛠️ Troubleshooting

For database issues:
1. Check [../operations/runbooks/troubleshooting-tools.md](../operations/runbooks/troubleshooting-tools.md)
2. Review monitoring: [../operations/monitoring/](../operations/monitoring/)
3. See feature-specific docs for feature database issues

---

*For the complete documentation structure, see [00_DOCUMENTATION_STRUCTURE.md](../00_DOCUMENTATION_STRUCTURE.md)*

