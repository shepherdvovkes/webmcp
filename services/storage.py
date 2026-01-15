"""Storage service for raw documents (MinIO or local filesystem)."""
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging
from config import settings

logger = logging.getLogger(__name__)


class StorageService:
    """Service for storing and retrieving raw documents."""
    
    def __init__(self):
        self.storage_type = settings.storage_type
        self.storage_path = settings.storage_path
        
        if self.storage_type == "local":
            # Create storage directory if it doesn't exist
            Path(self.storage_path).mkdir(parents=True, exist_ok=True)
            logger.info(f"Local storage initialized at {self.storage_path}")
        elif self.storage_type == "minio":
            # MinIO will be initialized lazily
            self._s3_client = None
            logger.info("MinIO storage configured")
        else:
            raise ValueError(f"Unknown storage type: {self.storage_type}")
    
    def _get_s3_client(self):
        """Get or create S3-compatible client for MinIO (not AWS)."""
        if self._s3_client is None:
            try:
                import boto3
                from botocore.config import Config
                
                # Parse endpoint (remove http:// or https:// if present)
                endpoint = settings.minio_endpoint
                if endpoint.startswith('http://'):
                    endpoint = endpoint[7:]
                elif endpoint.startswith('https://'):
                    endpoint = endpoint[8:]
                
                # Build endpoint URL for MinIO (not AWS)
                scheme = 'https' if settings.minio_use_ssl else 'http'
                endpoint_url = f"{scheme}://{endpoint}"
                
                # Create boto3 client configured for MinIO (S3-compatible API)
                # Note: boto3 uses aws_access_key_id/aws_secret_access_key parameter names
                # even for MinIO, as it's S3-compatible
                self._s3_client = boto3.client(
                    's3',
                    endpoint_url=endpoint_url,
                    aws_access_key_id=settings.minio_access_key,
                    aws_secret_access_key=settings.minio_secret_key,
                    region_name=settings.minio_region,
                    config=Config(signature_version='s3v4')
                )
                
                # Ensure bucket exists
                self._ensure_bucket_exists()
                
            except ImportError:
                raise ImportError("boto3 is required for MinIO storage")
        return self._s3_client
    
    def _ensure_bucket_exists(self):
        """Ensure MinIO bucket exists, create if it doesn't."""
        try:
            s3_client = self._get_s3_client()
            s3_client.head_bucket(Bucket=settings.minio_bucket_name)
        except Exception:
            # Bucket doesn't exist, create it
            try:
                s3_client = self._get_s3_client()
                s3_client.create_bucket(Bucket=settings.minio_bucket_name)
                logger.info(f"Created MinIO bucket: {settings.minio_bucket_name}")
            except Exception as e:
                logger.error(f"Failed to create MinIO bucket: {e}")
                raise
    
    def save(self, doc_id: str, content: bytes, extension: str = "html") -> str:
        """
        Save document content to storage.
        
        Args:
            doc_id: Document UUID
            content: Raw document content
            extension: File extension (html, pdf, etc.)
            
        Returns:
            Storage path/URI
        """
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        filename = f"{timestamp}.{extension}"
        
        if self.storage_type == "local":
            # Local filesystem storage
            doc_dir = Path(self.storage_path) / str(doc_id)
            doc_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = doc_dir / filename
            file_path.write_bytes(content)
            
            logger.info(f"Saved document to {file_path}")
            return str(file_path)
        
        elif self.storage_type == "minio":
            # MinIO storage
            if not settings.minio_bucket_name:
                raise ValueError("MinIO bucket name not configured")
            
            s3_key = f"court-registry-raw/{doc_id}/{filename}"
            s3_client = self._get_s3_client()
            
            s3_client.put_object(
                Bucket=settings.minio_bucket_name,
                Key=s3_key,
                Body=content
            )
            
            s3_uri = f"s3://{settings.minio_bucket_name}/{s3_key}"
            logger.info(f"Saved document to {s3_uri}")
            return s3_uri
        
        else:
            raise ValueError(f"Unknown storage type: {self.storage_type}")
    
    def load(self, storage_path: str) -> bytes:
        """
        Load document content from storage.
        
        Args:
            storage_path: Storage path/URI
            
        Returns:
            Document content as bytes
        """
        if storage_path.startswith("s3://"):
            # MinIO storage (using S3-compatible API, not AWS)
            s3_client = self._get_s3_client()
            bucket, key = storage_path.replace("s3://", "").split("/", 1)
            
            response = s3_client.get_object(Bucket=bucket, Key=key)
            return response['Body'].read()
        
        else:
            # Local filesystem storage
            file_path = Path(storage_path)
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {storage_path}")
            return file_path.read_bytes()
    
    def calculate_hash(self, content: bytes) -> str:
        """Calculate SHA256 hash of content."""
        return hashlib.sha256(content).hexdigest()
    
    def exists(self, storage_path: str) -> bool:
        """Check if file exists in storage."""
        if storage_path.startswith("s3://"):
            # MinIO storage (using S3-compatible API, not AWS)
            try:
                s3_client = self._get_s3_client()
                bucket, key = storage_path.replace("s3://", "").split("/", 1)
                s3_client.head_object(Bucket=bucket, Key=key)
                return True
            except Exception:
                return False
        else:
            return Path(storage_path).exists()
