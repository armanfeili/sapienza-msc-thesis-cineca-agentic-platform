```markdown
# Distributed Tracing Guide

## Overview

This document describes the **distributed tracing strategy** for the platform, enabling:
- End-to-end visibility into requests
- Latency breakdown across services
- Root cause analysis of performance issues
- Correlation of traces with metrics and logs

We use **OpenTelemetry** instrumentation with **Jaeger** as the tracing backend by default, but the system can also export to Tempo, Zipkin, or any OTLP-compatible backend.

---

## 1. Tracing Architecture

```

\[ Application Services ]
|
\[ OpenTelemetry SDK ]
|
\[ OTLP Exporter (HTTP/gRPC) ]
|
\[ OTel Collector ]
|
\[ Jaeger / Tempo / Zipkin Backend ]
|
\[ Grafana / Jaeger UI ]

```

---

## 2. Trace Context Propagation

We follow the **W3C Trace Context** standard:
- `traceparent`: contains the trace ID, span ID, trace flags
- `tracestate`: vendor-specific context

### Supported Protocols:
- **HTTP**: Headers automatically injected/extracted by the OTel HTTP instrumentation
- **gRPC**: Metadata propagation handled by gRPC interceptors
- **Async Tasks**: Context propagation supported via OTel context managers

---

## 3. Key Concepts

| Term       | Description |
|------------|-------------|
| **Trace**  | A collection of spans representing a single transaction/request |
| **Span**   | A single unit of work within a trace |
| **Attributes** | Key-value metadata associated with spans |
| **Events** | Time-stamped annotations within a span |
| **Links**  | Relationships between spans from different traces |

---

## 4. Instrumentation Strategy

We instrument the following components:

### 4.1 Application Layer
- HTTP server and client
- gRPC server and client
- Background jobs (Celery, RQ, custom)
- CLI commands (optional)

### 4.2 Database Layer
- Memgraph queries
- SQL queries (if applicable)
- Query execution time
- Query text (with sensitive data scrubbed)

### 4.3 Messaging / Streaming
- Kafka, RabbitMQ, or Redis Streams
- Producer and consumer latency
- Message size metrics

---

## 5. Span Naming Conventions

| Component | Span Name Format |
|-----------|------------------|
| HTTP Server | `HTTP {METHOD} {ROUTE}` |
| HTTP Client | `{METHOD} {HOST}:{PORT}{PATH}` |
| gRPC Server | `{PACKAGE}.{SERVICE}/{METHOD}` |
| gRPC Client | `{PACKAGE}.{SERVICE}/{METHOD}` |
| DB Query | `DB {OPERATION}` (e.g., `DB QUERY`, `DB TRANSACTION`) |
| Background Job | `Job {QUEUE}:{TASK_NAME}` |

---

## 6. Attributes to Include

### HTTP
- `http.method`
- `http.url`
- `http.status_code`
- `net.peer.ip`
- `net.peer.port`

### Database
- `db.system` (e.g., `memgraph`, `postgresql`)
- `db.statement` (scrubbed)
- `db.operation`
- `db.response_time_ms`

### Messaging
- `messaging.system` (e.g., `kafka`)
- `messaging.destination`
- `messaging.message_id`
- `messaging.payload_size_bytes`

---

## 7. Sampling Policy

We use **parent-based, probability sampling**:
- Default: 10% sampling rate in production
- 100% sampling in staging/testing
- Always sample error traces

Configurable via environment variable:
```

OTEL\_TRACES\_SAMPLER=parentbased\_traceidratio
OTEL\_TRACES\_SAMPLER\_ARG=0.1

````

---

## 8. Correlating Traces with Logs & Metrics

We add the `trace_id` and `span_id` to:
- **Logs**: Enables searching logs by trace
- **Metrics**: Enables drill-down from metrics to traces in Grafana

Example log entry:
```json
{
  "timestamp": "2025-08-09T14:32:21Z",
  "level": "ERROR",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "message": "Database query failed"
}
````

---

## 9. Jaeger Integration

### Jaeger Query UI

* View traces
* Filter by service, operation, latency, or tags
* Compare traces

### Example Jaeger Deployment in `docker-compose.yml`:

```yaml
jaeger:
  image: jaegertracing/all-in-one:latest
  ports:
    - "16686:16686" # UI
    - "14250:14250" # gRPC collector
    - "14268:14268" # HTTP collector
```

---

## 10. Example Trace Flow

```
[ HTTP GET /recommendations ]
   |
   |-- [ gRPC call → RecommendationService ]
   |       |
   |       |-- [ DB Query: MATCH (u:User)-[:LIKES]->(i:Item) ... ]
   |
   |-- [ External API call: GET /pricing ]
```

In Jaeger, this appears as a hierarchical tree of spans, each with timing, attributes, and logs.

---

## 11. Best Practices

* **Minimize span size**: avoid storing large payloads in attributes
* **Scrub sensitive data** before adding to span attributes
* **Name spans consistently** for better search and aggregation
* **Link spans** when processing asynchronous workflows
* **Instrument dependencies** (DB, queues, external APIs) to reduce "blind spots"

---

## 12. Troubleshooting

| Symptom               | Possible Cause              | Resolution                                    |
| --------------------- | --------------------------- | --------------------------------------------- |
| Missing traces        | Incorrect sampling config   | Set `OTEL_TRACES_SAMPLER_ARG=1.0` temporarily |
| Broken trace chain    | Missing context propagation | Ensure OTel middleware is registered          |
| High tracing overhead | Sampling too high           | Reduce sampling rate in production            |

---

**Last reviewed:** 2025-08-09
