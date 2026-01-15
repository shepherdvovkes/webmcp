"""Prometheus metrics for Court Registry MCP."""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client.core import CollectorRegistry
import time

# Create a custom registry
registry = CollectorRegistry()

# Kafka event metrics
kafka_events_published = Counter(
    'kafka_events_published_total',
    'Total number of Kafka events published',
    ['topic', 'status'],
    registry=registry
)

kafka_events_failed = Counter(
    'kafka_events_failed_total',
    'Total number of failed Kafka event publications',
    ['topic', 'error_type'],
    registry=registry
)

# Document processing metrics
documents_discovered = Counter(
    'documents_discovered_total',
    'Total number of documents discovered',
    registry=registry
)

documents_fetched = Counter(
    'documents_fetched_total',
    'Total number of documents fetched',
    ['status'],
    registry=registry
)

documents_parsed = Counter(
    'documents_parsed_total',
    'Total number of documents parsed',
    ['status'],
    registry=registry
)

document_processing_duration = Histogram(
    'document_processing_duration_seconds',
    'Time spent processing documents',
    ['stage'],
    registry=registry
)

# Database metrics
database_queries = Counter(
    'database_queries_total',
    'Total number of database queries',
    ['operation', 'status'],
    registry=registry
)

database_query_duration = Histogram(
    'database_query_duration_seconds',
    'Time spent executing database queries',
    ['operation'],
    registry=registry
)

# Active processing
active_document_processing = Gauge(
    'active_document_processing',
    'Number of documents currently being processed',
    ['stage'],
    registry=registry
)

# Embedding metrics
embeddings_generated = Counter(
    'embeddings_generated_total',
    'Total number of embeddings generated',
    registry=registry
)

embedding_generation_duration = Histogram(
    'embedding_generation_duration_seconds',
    'Time spent generating embeddings',
    registry=registry
)

# Cache metrics
cache_hits = Counter(
    'cache_hits_total',
    'Total number of cache hits',
    ['cache_type'],
    registry=registry
)

cache_misses = Counter(
    'cache_misses_total',
    'Total number of cache misses',
    ['cache_type'],
    registry=registry
)


def get_metrics():
    """Get Prometheus metrics in text format."""
    return generate_latest(registry)


def get_metrics_content_type():
    """Get content type for metrics endpoint."""
    return CONTENT_TYPE_LATEST
