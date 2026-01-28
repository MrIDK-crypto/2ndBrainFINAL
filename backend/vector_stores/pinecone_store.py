"""
Pinecone Vector Store - Production-Ready Multi-tenant RAG

Features:
- Multi-tenant isolation via namespaces + metadata filtering
- Batch upsert with retry logic
- Hybrid search (dense + keyword boosting)
- Automatic embedding with Azure OpenAI
- Document deduplication via upsert
- Smart chunking with sentence-aware splitting

Updated 2025-12-09:
- Increased chunk size to 2000 chars (better context)
- Increased overlap to 400 chars (better continuity)
- Improved sentence-aware splitting (multiple boundary types)
- Removed aggressive truncation (chunks are already sized correctly)
"""

import os
import re
import time
import hashlib
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from services.openai_client import get_openai_client

# Embedding dimensions - using 1536 for compatibility with existing index
# text-embedding-3-large supports native dimensionality reduction
EMBEDDING_DIMENSIONS = 1536

# Pinecone imports
try:
    from pinecone import Pinecone, ServerlessSpec
    PINECONE_AVAILABLE = True
except ImportError:
    PINECONE_AVAILABLE = False
    print("Warning: pinecone-client not installed. Run: pip install pinecone-client")


@dataclass
class PineconeConfig:
    """Configuration for Pinecone connection"""
    api_key: str
    environment: str = "us-east-1"  # AWS region for serverless
    index_name: str = "knowledgevault"
    dimension: int = EMBEDDING_DIMENSIONS
    metric: str = "cosine"
    cloud: str = "aws"


class PineconeVectorStore:
    """
    Production-ready vector store using Pinecone for multi-tenant RAG.

    Isolation Strategy (3 layers):
    1. Namespace: Each tenant gets their own namespace (primary isolation)
    2. Metadata: tenant_id stored in every vector (secondary filter)
    3. Application: All queries require tenant_id validation

    Deduplication:
    - Vector ID = hash(document_id + chunk_index)
    - Upsert (not insert) handles updates automatically
    """

    BATCH_SIZE = 100  # Vectors per upsert batch
    MAX_RETRIES = 3
    RETRY_DELAY = 1  # seconds

    def __init__(self, config: Optional[PineconeConfig] = None):
        if not PINECONE_AVAILABLE:
            raise ImportError("pinecone-client not installed")

        # Load config from environment if not provided
        if config is None:
            config = PineconeConfig(
                api_key=os.getenv("PINECONE_API_KEY", ""),
                index_name=os.getenv("PINECONE_INDEX", "knowledgevault")
            )

        if not config.api_key:
            raise ValueError("PINECONE_API_KEY is required")

        self.config = config
        self.pc = Pinecone(api_key=config.api_key)

        # Initialize OpenAI client for embeddings
        self.openai = get_openai_client()

        # Initialize or get index
        self.index = self._init_index()
        print(f"[PineconeVectorStore] Initialized with index={config.index_name}, dimension={config.dimension}")

    def _init_index(self):
        """Initialize Pinecone index, creating if needed"""
        existing_indexes = [idx.name for idx in self.pc.list_indexes()]

        if self.config.index_name not in existing_indexes:
            print(f"[PineconeVectorStore] Creating index: {self.config.index_name}")
            self.pc.create_index(
                name=self.config.index_name,
                dimension=self.config.dimension,
                metric=self.config.metric,
                spec=ServerlessSpec(
                    cloud=self.config.cloud,
                    region=self.config.environment
                )
            )
            # Wait for index to be ready
            time.sleep(5)

        return self.pc.Index(self.config.index_name)

    # Max chars for embedding (text-embedding-3-large has 8191 token limit ≈ 32K chars)
    # With 2000 char chunks, we should never hit this
    MAX_EMBEDDING_CHARS = 30000

    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for single text"""
        if len(text) > self.MAX_EMBEDDING_CHARS:
            print(f"[PineconeVectorStore] WARNING: Text truncated from {len(text)} to {self.MAX_EMBEDDING_CHARS} chars")
            text = text[:self.MAX_EMBEDDING_CHARS]

        response = self.openai.create_embedding(
            text=text,
            dimensions=EMBEDDING_DIMENSIONS
        )
        return response.data[0].embedding

    def _get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for multiple texts efficiently"""
        if not texts:
            return []

        # Safety truncation with warning (should not trigger with proper chunking)
        processed = []
        for t in texts:
            if t and len(t) > self.MAX_EMBEDDING_CHARS:
                print(f"[PineconeVectorStore] WARNING: Batch text truncated from {len(t)} to {self.MAX_EMBEDDING_CHARS} chars")
                processed.append(t[:self.MAX_EMBEDDING_CHARS])
            else:
                processed.append(t if t else "")

        # For batch embeddings, we need to call the API directly for each text
        # since our wrapper doesn't support batch yet
        embeddings = []
        for text in processed:
            response = self.openai.create_embedding(
                text=text,
                dimensions=EMBEDDING_DIMENSIONS
            )
            embeddings.append(response.data[0].embedding)
        return embeddings

    def _generate_vector_id(self, doc_id: str, chunk_idx: int = 0) -> str:
        """
        Generate deterministic vector ID for deduplication.
        Same doc_id + chunk_idx always produces same vector_id.
        """
        content = f"{doc_id}_{chunk_idx}"
        return hashlib.md5(content.encode()).hexdigest()

    def _chunk_text(
        self,
        text: str,
        chunk_size: int = 2000,
        overlap: int = 400
    ) -> List[Tuple[str, int]]:
        """
        Split text into overlapping chunks with smart sentence-aware splitting.

        Args:
            text: Text to chunk
            chunk_size: Target size per chunk (default 2000 chars for better context)
            overlap: Overlap between chunks (default 400 chars for continuity)

        Returns:
            List of (chunk_text, chunk_index) tuples
        """
        if not text:
            return []

        chunks = []
        start = 0
        chunk_idx = 0
        prev_start = -1  # Track previous start to prevent infinite loops

        # Sentence boundary patterns (ordered by preference)
        sentence_endings = [
            '\n\n',  # Paragraph break (highest priority)
            '.\n',   # Sentence + newline
            '!\n',   # Exclamation + newline
            '?\n',   # Question + newline
            '. ',    # Period + space
            '! ',    # Exclamation + space
            '? ',    # Question + space
            '.\t',   # Period + tab
            '\n',    # Single newline
            '; ',    # Semicolon (fallback)
        ]

        while start < len(text):
            # Prevent infinite loop
            if start == prev_start:
                start += chunk_size // 2  # Force progress
                if start >= len(text):
                    break
            prev_start = start

            end = min(start + chunk_size, len(text))
            chunk = text[start:end]

            # If not at end of text, find best sentence boundary
            actual_end = end
            if end < len(text):
                best_break = -1

                # Try each boundary type in order of preference
                for boundary in sentence_endings:
                    pos = chunk.rfind(boundary)
                    # Only use if it's in the latter half of the chunk
                    if pos > chunk_size * 0.5:
                        best_break = pos + len(boundary)
                        break

                # Use the boundary if found
                if best_break > 0:
                    chunk = chunk[:best_break]
                    actual_end = start + best_break

            # Add chunk if it has content
            stripped = chunk.strip()
            if stripped:
                chunks.append((stripped, chunk_idx))
                chunk_idx += 1

            # Move start position (with overlap, but ensure forward progress)
            next_start = actual_end - overlap
            if next_start <= start:
                next_start = actual_end  # Force forward progress
            start = next_start

        return chunks

    def embed_and_upsert_documents(
        self,
        documents: List[Dict],
        tenant_id: str,
        namespace: Optional[str] = None,
        chunk_size: int = 2000,
        chunk_overlap: int = 400,
        show_progress: bool = True
    ) -> Dict:
        """
        Chunk, embed, and upsert documents to Pinecone.

        Args:
            documents: List of dicts with 'id', 'content', 'title', and optional 'metadata'
            tenant_id: Tenant ID for isolation (REQUIRED)
            namespace: Optional namespace override (defaults to tenant_id)
            chunk_size: Characters per chunk
            chunk_overlap: Overlap between chunks
            show_progress: Print progress updates

        Returns:
            Stats about the operation
        """
        if not tenant_id:
            raise ValueError("tenant_id is required for multi-tenant isolation")

        # Use tenant_id as namespace if not specified
        ns = namespace or tenant_id

        total_docs = len(documents)
        total_chunks = 0
        upserted = 0
        errors = []

        print(f"[PineconeVectorStore] Processing {total_docs} documents for tenant {tenant_id}")

        # Prepare all chunks first
        all_chunks = []
        for doc in documents:
            doc_id = str(doc.get('id', ''))
            content = doc.get('content', '')
            title = doc.get('title', '')
            metadata = doc.get('metadata', {})

            if not content:
                continue

            # Chunk the document
            chunks = self._chunk_text(content, chunk_size, chunk_overlap)

            for chunk_text, chunk_idx in chunks:
                all_chunks.append({
                    'doc_id': doc_id,
                    'chunk_idx': chunk_idx,
                    'content': chunk_text,
                    'title': title,
                    'metadata': metadata,
                    'tenant_id': tenant_id  # Always include tenant_id
                })

        total_chunks = len(all_chunks)
        print(f"[PineconeVectorStore] Created {total_chunks} chunks from {total_docs} documents")

        # Process in batches
        for i in range(0, total_chunks, self.BATCH_SIZE):
            batch = all_chunks[i:i + self.BATCH_SIZE]

            for retry in range(self.MAX_RETRIES):
                try:
                    # Get embeddings for batch
                    texts = [chunk['content'] for chunk in batch]
                    embeddings = self._get_embeddings_batch(texts)

                    # Prepare vectors
                    vectors = []
                    for chunk, embedding in zip(batch, embeddings):
                        vector_id = self._generate_vector_id(chunk['doc_id'], chunk['chunk_idx'])

                        # Prepare metadata (Pinecone has 40KB limit per vector)
                        metadata = {
                            'doc_id': chunk['doc_id'],
                            'chunk_idx': chunk['chunk_idx'],
                            'tenant_id': chunk['tenant_id'],  # Critical for isolation
                            'title': chunk['title'][:200] if chunk['title'] else '',
                            'content_preview': chunk['content'][:500],  # For display
                        }

                        # Add custom metadata (with size limits)
                        for k, v in chunk.get('metadata', {}).items():
                            if isinstance(v, (str, int, float, bool)) and len(str(v)) < 500:
                                metadata[k] = v

                        vectors.append({
                            'id': vector_id,
                            'values': embedding,
                            'metadata': metadata
                        })

                    # Upsert to Pinecone (handles duplicates automatically)
                    self.index.upsert(vectors=vectors, namespace=ns)
                    upserted += len(vectors)

                    if show_progress:
                        print(f"[PineconeVectorStore] Upserted {upserted}/{total_chunks} chunks...")

                    break  # Success, exit retry loop

                except Exception as e:
                    if retry < self.MAX_RETRIES - 1:
                        print(f"[PineconeVectorStore] Retry {retry + 1} after error: {e}")
                        time.sleep(self.RETRY_DELAY * (retry + 1))
                    else:
                        errors.append({'batch': i, 'error': str(e)})
                        print(f"[PineconeVectorStore] Failed batch {i}: {e}")

        result = {
            'success': len(errors) == 0,
            'total_documents': total_docs,
            'total_chunks': total_chunks,
            'upserted': upserted,
            'errors': errors,
            'namespace': ns,
            'tenant_id': tenant_id
        }

        print(f"[PineconeVectorStore] Complete: {upserted}/{total_chunks} chunks upserted")
        return result

    def search(
        self,
        query: str,
        tenant_id: str,
        namespace: Optional[str] = None,
        top_k: int = 10,
        filter: Optional[Dict] = None,
        include_metadata: bool = True
    ) -> List[Dict]:
        """
        Search for similar documents with tenant isolation.

        Args:
            query: Search query text
            tenant_id: Tenant ID (REQUIRED for isolation)
            namespace: Optional namespace override
            top_k: Number of results
            filter: Additional metadata filter
            include_metadata: Include metadata in results

        Returns:
            List of matching documents with scores
        """
        if not tenant_id:
            raise ValueError("tenant_id is required for multi-tenant isolation")

        ns = namespace or tenant_id

        # Get query embedding
        query_embedding = self._get_embedding(query)

        # Build filter with tenant_id (defense in depth)
        combined_filter = {'tenant_id': {'$eq': tenant_id}}
        if filter:
            combined_filter = {'$and': [combined_filter, filter]}

        # Search Pinecone
        results = self.index.query(
            vector=query_embedding,
            namespace=ns,
            top_k=top_k,
            filter=combined_filter,
            include_metadata=include_metadata
        )

        # Format results
        formatted = []
        for match in results.matches:
            formatted.append({
                'id': match.id,
                'score': match.score,
                'doc_id': match.metadata.get('doc_id', ''),
                'chunk_idx': match.metadata.get('chunk_idx', 0),
                'title': match.metadata.get('title', ''),
                'content': match.metadata.get('content_preview', ''),
                'metadata': {k: v for k, v in match.metadata.items()
                           if k not in ['doc_id', 'chunk_idx', 'content_preview', 'tenant_id', 'title']}
            })

        return formatted

    def delete_tenant_data(self, tenant_id: str, namespace: Optional[str] = None) -> bool:
        """Delete all vectors for a tenant (for account deletion)"""
        ns = namespace or tenant_id
        try:
            self.index.delete(delete_all=True, namespace=ns)
            print(f"[PineconeVectorStore] Deleted all data for tenant {tenant_id}")
            return True
        except Exception as e:
            print(f"[PineconeVectorStore] Error deleting tenant data: {e}")
            return False

    def delete_documents(
        self,
        doc_ids: List[str],
        tenant_id: str,
        namespace: Optional[str] = None,
        max_chunks_per_doc: int = 100
    ) -> bool:
        """Delete specific documents by ID"""
        ns = namespace or tenant_id
        try:
            # Generate vector IDs for all possible chunks
            vector_ids = []
            for doc_id in doc_ids:
                for i in range(max_chunks_per_doc):
                    vector_ids.append(self._generate_vector_id(doc_id, i))

            # Delete in batches (Pinecone has limits)
            batch_size = 1000
            for i in range(0, len(vector_ids), batch_size):
                batch = vector_ids[i:i + batch_size]
                self.index.delete(ids=batch, namespace=ns)

            print(f"[PineconeVectorStore] Deleted {len(doc_ids)} documents for tenant {tenant_id}")
            return True
        except Exception as e:
            print(f"[PineconeVectorStore] Error deleting documents: {e}")
            return False

    def get_stats(self, tenant_id: Optional[str] = None) -> Dict:
        """Get index statistics, optionally filtered by tenant"""
        stats = self.index.describe_index_stats()

        if tenant_id:
            ns_stats = stats.namespaces.get(tenant_id, {})
            return {
                'tenant_id': tenant_id,
                'namespace': tenant_id,
                'vector_count': getattr(ns_stats, 'vector_count', 0)
            }

        return {
            'total_vectors': stats.total_vector_count,
            'dimension': stats.dimension,
            'namespaces': {k: v.vector_count for k, v in stats.namespaces.items()}
        }


class HybridPineconeStore(PineconeVectorStore):
    """
    Extended Pinecone store with hybrid search capabilities.
    Combines dense (semantic) and sparse (keyword) retrieval.
    """

    def __init__(self, config: Optional[PineconeConfig] = None):
        super().__init__(config)
        self.sparse_weight = 0.3
        self.dense_weight = 0.7

    def hybrid_search(
        self,
        query: str,
        tenant_id: str,
        namespace: Optional[str] = None,
        top_k: int = 10,
        filter: Optional[Dict] = None,
        sparse_weight: Optional[float] = None,
        dense_weight: Optional[float] = None
    ) -> List[Dict]:
        """
        Hybrid search combining semantic and keyword matching.

        Uses keyword boosting on top of semantic search results.
        """
        sw = sparse_weight or self.sparse_weight
        dw = dense_weight or self.dense_weight

        # Get semantic results (fetch more for reranking)
        semantic_results = self.search(query, tenant_id, namespace, top_k * 2, filter)

        # Boost results that contain query keywords
        query_terms = set(query.lower().split())

        for result in semantic_results:
            content_lower = result.get('content', '').lower()
            title_lower = result.get('title', '').lower()

            # Count keyword matches in content and title
            content_matches = sum(1 for term in query_terms if term in content_lower)
            title_matches = sum(1 for term in query_terms if term in title_lower)

            # Title matches weighted higher
            keyword_boost = min((content_matches * 0.05) + (title_matches * 0.15), 0.3)

            # Combine scores
            result['semantic_score'] = result['score']
            result['keyword_boost'] = keyword_boost
            result['score'] = (dw * result['score']) + (sw * keyword_boost)

        # Re-sort by combined score
        semantic_results.sort(key=lambda x: x['score'], reverse=True)

        return semantic_results[:top_k]


# Singleton instance for easy access
_vector_store_instance: Optional[PineconeVectorStore] = None


def get_vector_store() -> PineconeVectorStore:
    """Get or create singleton PineconeVectorStore instance"""
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = PineconeVectorStore()
    return _vector_store_instance


def get_hybrid_store() -> HybridPineconeStore:
    """Get or create HybridPineconeStore instance"""
    return HybridPineconeStore()
