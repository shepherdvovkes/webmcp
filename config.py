"""Configuration management for Court Registry MCP Server."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings."""
    
    # OpenAI
    openai_api_key: str
    
    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "court_registry"
    postgres_user: str = "court_user"
    postgres_password: str
    
    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    redis_db: int = 0
    
    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_enabled: bool = True
    kafka_auto_create_topics: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        # Allow environment variables to override defaults
        fields = {
            'kafka_bootstrap_servers': {'env': 'KAFKA_BOOTSTRAP_SERVERS'}
        }
    
    # MCP Server
    mcp_server_port: int = 8000
    mcp_server_host: str = "0.0.0.0"
    
    # Court Registry
    court_registry_base_url: str = "https://reyestr.court.gov.ua"
    court_registry_search_endpoint: str = "/Search"
    court_registry_rss_endpoint: str = "/RSS"
    
    # Fetcher
    # Note: fetcher_workers must be set in .env file as FETCHER_WORKERS
    fetcher_workers: int  # Required: set FETCHER_WORKERS in .env
    fetcher_max_retries: int = 3
    fetcher_timeout: int = 30
    
    # Parser
    parser_version: str = "1.0.0"
    parser_confidence_threshold: float = 0.7
    
    # Embedding
    embedding_model: str = "text-embedding-3-small"
    embedding_batch_size: int = 100
    embedding_chunk_size: int = 512
    
    # Storage
    storage_type: str = "minio"
    storage_path: str = "/app/storage"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket_name: str = "court-registry"
    minio_use_ssl: bool = False
    minio_region: str = "us-east-1"
    
    # Monitoring
    discovery_interval_minutes: int = 10
    reconciliation_interval_hours: int = 24
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    
    # Security
    secret_key: str
    allowed_origins: str = "http://localhost:3000,http://localhost:8000"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
