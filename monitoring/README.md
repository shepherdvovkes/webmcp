# Monitoring Setup

This directory contains the monitoring configuration for the Court Registry MCP system using Prometheus and Grafana.

## Architecture

```
┌─────────────┐
│  Grafana    │  Port 3000
│  (UI)       │
└──────┬──────┘
       │
       ↓
┌─────────────┐
│ Prometheus  │  Port 9090
│ (Metrics)   │
└──────┬──────┘
       │
       ├──→ Kafka Exporter (Port 9308)
       ├──→ PostgreSQL Exporter (Port 9187)
       ├──→ Redis Exporter (Port 9121)
       └──→ Application Metrics (Port 8000/metrics)
```

## Services

### Prometheus
- **Port**: 9090
- **Config**: `monitoring/prometheus.yml`
- **Data**: Stored in `prometheus_data` volume (30 days retention)

### Grafana
- **Port**: 3000
- **Default credentials**: admin/admin
- **Dashboards**: Auto-provisioned from `monitoring/grafana/dashboards/`
- **Data**: Stored in `grafana_data` volume

### Exporters

1. **Kafka Exporter** (Port 9308)
   - Exports Kafka broker and topic metrics
   - Metrics: messages in/out, consumer lag, partition info

2. **PostgreSQL Exporter** (Port 9187)
   - Exports PostgreSQL database metrics
   - Metrics: connections, transactions, tuples, cache hit ratio

3. **Redis Exporter** (Port 9121)
   - Exports Redis cache metrics
   - Metrics: memory, connections, commands, hit rate

4. **Application Metrics** (Port 8000/metrics)
   - Custom metrics from Python application
   - Metrics: document processing, Kafka events, embeddings

## Dashboards

### 1. Kafka Overview
- Messages in/out per second
- Topic messages per second
- Consumer lag
- Bytes in/out
- Partition count

### 2. PostgreSQL Overview
- Database size
- Active connections
- Transactions per second
- Tuples inserted/updated/deleted
- Cache hit ratio
- Table sizes

### 3. Redis Overview
- Connected clients
- Memory used
- Commands processed per second
- Keyspace operations
- Hit rate
- Network I/O

### 4. Application Overview
- Documents discovered/fetched/parsed
- Processing duration
- Active processing
- Kafka events published/failed
- Embeddings generated

## Access

After starting services with `docker-compose up -d`:

- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090
- **Application Metrics**: http://localhost:8000/metrics

## Custom Metrics

The application exports custom metrics via `/metrics` endpoint:

- `documents_discovered_total` - Total documents discovered
- `documents_fetched_total{status}` - Documents fetched (success/failed)
- `documents_parsed_total{status}` - Documents parsed (success/failed)
- `document_processing_duration_seconds{stage}` - Processing time by stage
- `kafka_events_published_total{topic,status}` - Kafka events published
- `kafka_events_failed_total{topic,error_type}` - Kafka event failures
- `embeddings_generated_total` - Total embeddings generated
- `embedding_generation_duration_seconds` - Embedding generation time

## Adding New Metrics

1. Add metric definition in `services/metrics.py`
2. Use metric in application code
3. Metric will automatically appear in Prometheus
4. Add panel to Grafana dashboard if needed

## Troubleshooting

### Prometheus not scraping
- Check exporter containers are running: `docker ps`
- Check Prometheus targets: http://localhost:9090/targets
- Check exporter endpoints: `curl http://localhost:9308/metrics`

### Grafana dashboards not loading
- Check dashboard files in `monitoring/grafana/dashboards/`
- Check Grafana logs: `docker logs court-registry-grafana`
- Verify datasource: http://localhost:3000/connections/datasources

### Metrics not appearing
- Verify application is exposing metrics: `curl http://localhost:8000/metrics`
- Check Prometheus config includes the target
- Wait for scrape interval (15s default)
