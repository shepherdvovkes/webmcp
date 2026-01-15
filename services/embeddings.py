"""Embedding service - generates embeddings using OpenAI API."""
import logging
from typing import List, Optional
import tiktoken
from openai import AsyncOpenAI
from config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating text embeddings."""
    
    def __init__(self):
        self.model = settings.embedding_model
        self.batch_size = settings.embedding_batch_size
        self.chunk_size = settings.embedding_chunk_size
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.encoding = tiktoken.encoding_for_model("text-embedding-3-small")
    
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings
            
        Returns:
            List of embedding vectors (1536 dimensions for text-embedding-3-small)
        """
        if not texts:
            return []
        
        try:
            # Process in batches
            all_embeddings = []
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i:i + self.batch_size]
                
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=batch
                )
                
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)
                
                logger.debug(f"Generated embeddings for batch {i // self.batch_size + 1}")
            
            return all_embeddings
            
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}", exc_info=True)
            return []
    
    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text string
            
        Returns:
            Embedding vector or None if failed
        """
        embeddings = await self.generate_embeddings([text])
        return embeddings[0] if embeddings else None
    
    def chunk_text(self, text: str, max_tokens: Optional[int] = None) -> List[str]:
        """
        Split text into chunks for embedding.
        
        Args:
            text: Text to chunk
            max_tokens: Maximum tokens per chunk (defaults to chunk_size)
            
        Returns:
            List of text chunks
        """
        if max_tokens is None:
            max_tokens = self.chunk_size
        
        # Tokenize text
        tokens = self.encoding.encode(text)
        
        # Split into chunks
        chunks = []
        for i in range(0, len(tokens), max_tokens):
            chunk_tokens = tokens[i:i + max_tokens]
            chunk_text = self.encoding.decode(chunk_tokens)
            chunks.append(chunk_text)
        
        return chunks
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.encoding.encode(text))
