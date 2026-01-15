"""Kafka client for event streaming in Court Registry MCP."""
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError
from config import settings
from services.metrics import kafka_events_published, kafka_events_failed

logger = logging.getLogger(__name__)


class KafkaEventProducer:
    """Kafka producer for publishing events."""
    
    def __init__(self):
        """Initialize Kafka producer."""
        self.producer = None
        if settings.kafka_enabled:
            try:
                self.producer = KafkaProducer(
                    bootstrap_servers=settings.kafka_bootstrap_servers.split(','),
                    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                    key_serializer=lambda k: k.encode('utf-8') if k else None,
                    acks='all',  # Wait for all replicas
                    retries=3,
                    max_in_flight_requests_per_connection=1,
                    enable_idempotence=True
                )
                logger.info(f"Kafka producer initialized: {settings.kafka_bootstrap_servers}")
            except Exception as e:
                logger.error(f"Failed to initialize Kafka producer: {e}")
                self.producer = None
    
    def publish_discovered(self, doc_id: str, case_id: str, url: str, hash_hint: Optional[str] = None):
        """Publish document discovery event.
        
        Topic: court.documents.discovered
        """
        event = {
            'doc_id': doc_id,
            'case_id': case_id,
            'url': url,
            'discovered_at': datetime.utcnow().isoformat(),
            'hash_hint': hash_hint
        }
        return self._publish('court.documents.discovered', doc_id, event)
    
    def publish_fetched(self, doc_id: str, storage_path: str, sha256: str):
        """Publish document fetch event.
        
        Topic: court.documents.fetched
        """
        event = {
            'doc_id': doc_id,
            'storage_path': storage_path,
            'sha256': sha256,
            'fetched_at': datetime.utcnow().isoformat()
        }
        return self._publish('court.documents.fetched', doc_id, event)
    
    def publish_parsed(self, doc_id: str, version_id: str, entities: Dict[str, Any], law_refs: list):
        """Publish document parse event.
        
        Topic: court.documents.parsed
        """
        event = {
            'doc_id': doc_id,
            'version_id': version_id,
            'entities': entities,
            'law_refs': law_refs,
            'parsed_at': datetime.utcnow().isoformat()
        }
        return self._publish('court.documents.parsed', doc_id, event)
    
    def publish_failed(self, doc_id: str, stage: str, error: str, error_details: Optional[Dict] = None):
        """Publish document processing failure event.
        
        Topic: court.documents.failed
        """
        event = {
            'doc_id': doc_id,
            'stage': stage,  # 'discovery', 'fetch', 'parse', 'embedding'
            'error': error,
            'error_details': error_details or {},
            'failed_at': datetime.utcnow().isoformat()
        }
        return self._publish('court.documents.failed', doc_id, event)
    
    def _publish(self, topic: str, key: str, event: Dict[str, Any]) -> bool:
        """Publish event to Kafka topic."""
        if not self.producer:
            logger.warning(f"Kafka producer not available, skipping event: {topic}")
            kafka_events_failed.labels(topic=topic, error_type='producer_unavailable').inc()
            return False
        
        try:
            future = self.producer.send(topic, key=key, value=event)
            # Wait for the message to be sent
            record_metadata = future.get(timeout=10)
            logger.debug(
                f"Published event to {topic} [partition={record_metadata.partition}, "
                f"offset={record_metadata.offset}]"
            )
            kafka_events_published.labels(topic=topic, status='success').inc()
            return True
        except KafkaError as e:
            logger.error(f"Failed to publish event to {topic}: {e}")
            kafka_events_published.labels(topic=topic, status='failed').inc()
            kafka_events_failed.labels(topic=topic, error_type='kafka_error').inc()
            return False
        except Exception as e:
            logger.error(f"Unexpected error publishing to {topic}: {e}")
            kafka_events_published.labels(topic=topic, status='failed').inc()
            kafka_events_failed.labels(topic=topic, error_type='unexpected_error').inc()
            return False
    
    def flush(self):
        """Flush all pending messages."""
        if self.producer:
            self.producer.flush()
    
    def close(self):
        """Close the producer."""
        if self.producer:
            self.flush()
            self.producer.close()
            logger.info("Kafka producer closed")


class KafkaEventConsumer:
    """Kafka consumer for processing events."""
    
    def __init__(self, group_id: str, topics: list, auto_offset_reset: str = 'earliest'):
        """Initialize Kafka consumer.
        
        Args:
            group_id: Consumer group ID
            topics: List of topics to subscribe to
            auto_offset_reset: Where to start reading ('earliest' or 'latest')
        """
        self.consumer = None
        self.topics = topics
        self.group_id = group_id
        
        if settings.kafka_enabled:
            try:
                self.consumer = KafkaConsumer(
                    *topics,
                    bootstrap_servers=settings.kafka_bootstrap_servers.split(','),
                    group_id=group_id,
                    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                    key_deserializer=lambda k: k.decode('utf-8') if k else None,
                    auto_offset_reset=auto_offset_reset,
                    enable_auto_commit=True,
                    consumer_timeout_ms=1000  # Timeout for polling
                )
                logger.info(f"Kafka consumer initialized: group={group_id}, topics={topics}")
            except Exception as e:
                logger.error(f"Failed to initialize Kafka consumer: {e}")
                self.consumer = None
    
    def poll(self, timeout_ms: int = 1000):
        """Poll for messages.
        
        Returns:
            Dict of TopicPartition -> list of ConsumerRecords
        """
        if not self.consumer:
            return {}
        
        try:
            return self.consumer.poll(timeout_ms=timeout_ms)
        except Exception as e:
            logger.error(f"Error polling Kafka: {e}")
            return {}
    
    def commit(self):
        """Commit offsets."""
        if self.consumer:
            self.consumer.commit()
    
    def close(self):
        """Close the consumer."""
        if self.consumer:
            self.consumer.close()
            logger.info(f"Kafka consumer closed: group={self.group_id}")


# Global producer instance
_producer_instance: Optional[KafkaEventProducer] = None


def get_producer() -> KafkaEventProducer:
    """Get or create global Kafka producer instance."""
    global _producer_instance
    if _producer_instance is None:
        _producer_instance = KafkaEventProducer()
    return _producer_instance


def close_producer():
    """Close global producer instance."""
    global _producer_instance
    if _producer_instance:
        _producer_instance.close()
        _producer_instance = None
