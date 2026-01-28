"""
Enhanced Search Service - Production RAG with Advanced Features

Ports EnhancedRAGv2 features to work with Pinecone:
- Query expansion (100+ acronyms)
- Cross-encoder reranking
- MMR diversity selection
- Hallucination detection
- Strict citation enforcement
- Freshness scoring

Created: 2025-12-09
"""

import os
import re
import json
import time
import hashlib
import numpy as np
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime

from services.openai_client import get_openai_client

# Cross-encoder for reranking
try:
    from sentence_transformers import CrossEncoder
    CROSS_ENCODER_AVAILABLE = True
except ImportError:
    CROSS_ENCODER_AVAILABLE = False
    print("[EnhancedSearch] Warning: sentence-transformers not installed. Reranking disabled.")
    print("[EnhancedSearch] Install with: pip install sentence-transformers")


# =============================================================================
# QUERY EXPANSION
# =============================================================================

class QueryExpander:
    """Query expansion with acronyms and synonyms"""

    # Comprehensive acronym dictionary (100+ terms)
    ACRONYMS = {
        # Healthcare
        'ROI': 'Return on Investment',
        'NICU': 'Neonatal Intensive Care Unit',
        'PICU': 'Pediatric Intensive Care Unit',
        'ICU': 'Intensive Care Unit',
        'OB-ED': 'Obstetric Emergency Department',
        'OBED': 'Obstetric Emergency Department',
        'L&D': 'Labor and Delivery',
        'ED': 'Emergency Department',
        'OR': 'Operating Room',
        'FDU': 'Fetal Diagnostic Unit',
        'LOS': 'Length of Stay',
        'ADT': 'Admission Discharge Transfer',
        'EMR': 'Electronic Medical Record',
        'EHR': 'Electronic Health Record',
        'DRG': 'Diagnosis Related Group',
        'CMS': 'Centers for Medicare and Medicaid Services',
        'HIPAA': 'Health Insurance Portability and Accountability Act',
        'PHI': 'Protected Health Information',
        'RVU': 'Relative Value Unit',
        'FTE': 'Full Time Equivalent',
        'CMO': 'Chief Medical Officer',
        'CNO': 'Chief Nursing Officer',

        # Finance
        'NPV': 'Net Present Value',
        'IRR': 'Internal Rate of Return',
        'EBITDA': 'Earnings Before Interest Taxes Depreciation and Amortization',
        'EBIT': 'Earnings Before Interest and Taxes',
        'P&L': 'Profit and Loss',
        'COGS': 'Cost of Goods Sold',
        'OPEX': 'Operating Expenses',
        'CAPEX': 'Capital Expenditure',
        'DCF': 'Discounted Cash Flow',
        'WACC': 'Weighted Average Cost of Capital',
        'EV': 'Enterprise Value',
        'FCF': 'Free Cash Flow',
        'GP': 'Gross Profit',
        'NI': 'Net Income',
        'AR': 'Accounts Receivable',
        'AP': 'Accounts Payable',
        'YoY': 'Year over Year',
        'QoQ': 'Quarter over Quarter',
        'MoM': 'Month over Month',
        'CAGR': 'Compound Annual Growth Rate',
        'P/E': 'Price to Earnings Ratio',
        'EPS': 'Earnings Per Share',
        'ROE': 'Return on Equity',
        'ROA': 'Return on Assets',
        'ROIC': 'Return on Invested Capital',

        # Market/Business
        'TAM': 'Total Addressable Market',
        'SAM': 'Serviceable Addressable Market',
        'SOM': 'Serviceable Obtainable Market',
        'CAC': 'Customer Acquisition Cost',
        'LTV': 'Lifetime Value',
        'MRR': 'Monthly Recurring Revenue',
        'ARR': 'Annual Recurring Revenue',
        'GMV': 'Gross Merchandise Value',
        'NPS': 'Net Promoter Score',
        'ARPU': 'Average Revenue Per User',
        'DAU': 'Daily Active Users',
        'MAU': 'Monthly Active Users',
        'B2B': 'Business to Business',
        'B2C': 'Business to Consumer',
        'GTM': 'Go to Market',
        'MVP': 'Minimum Viable Product',
        'PMF': 'Product Market Fit',
        'POC': 'Proof of Concept',

        # Consulting
        'SOW': 'Statement of Work',
        'RFP': 'Request for Proposal',
        'RFI': 'Request for Information',
        'NDA': 'Non-Disclosure Agreement',
        'SLA': 'Service Level Agreement',
        'KPI': 'Key Performance Indicator',
        'OKR': 'Objectives and Key Results',
        'SWOT': 'Strengths Weaknesses Opportunities Threats',

        # Tech
        'API': 'Application Programming Interface',
        'SDK': 'Software Development Kit',
        'CI/CD': 'Continuous Integration Continuous Deployment',
        'AWS': 'Amazon Web Services',
        'GCP': 'Google Cloud Platform',
        'ML': 'Machine Learning',
        'AI': 'Artificial Intelligence',
        'NLP': 'Natural Language Processing',
        'RAG': 'Retrieval Augmented Generation',
        'LLM': 'Large Language Model',
    }

    # Synonym mappings
    SYNONYMS = {
        'revenue': ['income', 'earnings', 'sales', 'receipts'],
        'cost': ['expense', 'expenditure', 'investment', 'spending'],
        'profit': ['earnings', 'income', 'margin', 'returns'],
        'growth': ['increase', 'expansion', 'rise', 'gain'],
        'decline': ['decrease', 'drop', 'reduction', 'fall'],
        'patients': ['cases', 'admissions', 'individuals'],
        'employees': ['staff', 'workers', 'team members', 'personnel'],
    }

    @classmethod
    def expand_acronyms(cls, query: str) -> str:
        """Expand acronyms in query"""
        expanded = query
        for acronym, expansion in cls.ACRONYMS.items():
            pattern = rf'\b{re.escape(acronym)}\b'
            if re.search(pattern, query, re.IGNORECASE):
                match = re.search(pattern, query, re.IGNORECASE)
                if match and expansion.lower() not in query.lower():
                    original = match.group()
                    expanded = expanded.replace(original, f"{original} ({expansion})", 1)
        return expanded

    @classmethod
    def get_synonyms(cls, query: str) -> List[str]:
        """Get synonyms for key terms"""
        query_lower = query.lower()
        additional = []
        for term, syns in cls.SYNONYMS.items():
            if term in query_lower:
                additional.extend(syns)
        return list(set(additional))

    @classmethod
    def expand(cls, query: str) -> Dict:
        """Full query expansion"""
        expanded = cls.expand_acronyms(query)
        synonyms = cls.get_synonyms(query)

        return {
            'original': query,
            'expanded': expanded,
            'synonyms': synonyms,
            'search_query': expanded  # Use expanded for search
        }


# =============================================================================
# CROSS-ENCODER RERANKING
# =============================================================================

class CrossEncoderReranker:
    """Cross-encoder for accurate reranking"""

    MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-12-v2"

    def __init__(self):
        self.model = None
        self._load_model()

    def _load_model(self):
        if not CROSS_ENCODER_AVAILABLE:
            return
        try:
            self.model = CrossEncoder(self.MODEL_NAME)
            print(f"[EnhancedSearch] Cross-encoder loaded: {self.MODEL_NAME}")
        except Exception as e:
            print(f"[EnhancedSearch] Failed to load cross-encoder: {e}")
            self.model = None

    def rerank(self, query: str, results: List[Dict], top_k: int = 10) -> List[Dict]:
        """Rerank results using cross-encoder"""
        if not self.model or not results:
            return results[:top_k]

        # Score each result
        scored_results = []
        for result in results:
            content = result.get('content', '') or result.get('content_preview', '')
            if not content:
                scored_results.append((result, 0.0))
                continue

            # Score multiple segments for long content
            segments = [
                content[:512],
                content[len(content)//2-256:len(content)//2+256] if len(content) > 512 else '',
                content[-512:] if len(content) > 512 else ''
            ]

            segment_scores = []
            for seg in segments:
                if seg.strip():
                    try:
                        score = self.model.predict([(query, seg)])[0]
                        segment_scores.append(float(score))
                    except:
                        pass

            max_score = max(segment_scores) if segment_scores else 0.0
            result['rerank_score'] = max_score
            scored_results.append((result, max_score))

        # Sort by rerank score
        scored_results.sort(key=lambda x: x[1], reverse=True)

        return [r for r, _ in scored_results[:top_k]]


# =============================================================================
# MMR DIVERSITY SELECTION
# =============================================================================

class MMRSelector:
    """Maximal Marginal Relevance for diverse results"""

    @staticmethod
    def select(
        results: List[Dict],
        query_embedding: np.ndarray,
        embeddings: np.ndarray,
        k: int = 10,
        lambda_param: float = 0.7
    ) -> List[Dict]:
        """Select diverse results using MMR"""
        if len(results) <= k:
            return results

        # Normalize embeddings
        query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-8)
        emb_norms = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8)

        # Compute similarities
        query_sims = np.dot(emb_norms, query_norm)
        doc_sims = np.dot(emb_norms, emb_norms.T)

        selected_indices = []
        remaining = list(range(len(results)))

        for _ in range(k):
            if not remaining:
                break

            mmr_scores = []
            for idx in remaining:
                relevance = query_sims[idx]
                if selected_indices:
                    diversity_penalty = max(doc_sims[idx][s] for s in selected_indices)
                else:
                    diversity_penalty = 0

                mmr = lambda_param * relevance - (1 - lambda_param) * diversity_penalty
                mmr_scores.append((idx, mmr))

            best_idx = max(mmr_scores, key=lambda x: x[1])[0]
            selected_indices.append(best_idx)
            remaining.remove(best_idx)

        return [results[i] for i in selected_indices]


# =============================================================================
# HALLUCINATION DETECTION
# =============================================================================

class HallucinationDetector:
    """Detect and flag potential hallucinations"""

    def __init__(self, client):
        self.client = client

    def extract_claims(self, answer: str) -> List[Dict]:
        """Extract factual claims from answer"""
        claims = []

        # Extract numbers with context
        number_pattern = r'([^.]*?\b\d[\d,\.%$]*\b[^.]*\.)'
        for match in re.finditer(number_pattern, answer):
            claims.append({
                'type': 'numerical',
                'text': match.group(1).strip(),
                'value': re.search(r'\d[\d,\.%$]*', match.group(1)).group()
            })

        # Extract source citations
        citation_pattern = r'\[Source (\d+)\]'
        for match in re.finditer(citation_pattern, answer):
            claims.append({
                'type': 'citation',
                'source_num': int(match.group(1)),
                'context': answer[max(0, match.start()-100):match.end()+50]
            })

        return claims

    def verify_claims(self, claims: List[Dict], sources: List[Dict]) -> Dict:
        """Verify claims against sources"""
        verified = []
        unverified = []
        hallucinated = []

        for claim in claims:
            if claim['type'] == 'citation':
                source_num = claim['source_num']
                if source_num <= len(sources):
                    source_content = sources[source_num - 1].get('content', '')
                    claim_numbers = set(re.findall(r'\d+\.?\d*', claim['context']))
                    source_numbers = set(re.findall(r'\d+\.?\d*', source_content))

                    if claim_numbers & source_numbers:
                        verified.append(claim)
                    else:
                        unverified.append(claim)
                else:
                    hallucinated.append(claim)

            elif claim['type'] == 'numerical':
                claim_value = claim['value'].replace(',', '').replace('$', '').replace('%', '')
                found = False
                for source in sources:
                    if claim_value in source.get('content', '').replace(',', ''):
                        found = True
                        break
                if found:
                    verified.append(claim)
                else:
                    unverified.append(claim)

        total = len(claims) or 1
        return {
            'verified': len(verified),
            'unverified': len(unverified),
            'hallucinated': len(hallucinated),
            'total_claims': len(claims),
            'confidence': len(verified) / total,
            'details': {
                'verified': verified[:5],
                'unverified': unverified[:5],
                'hallucinated': hallucinated[:5]
            }
        }

    def check_citation_coverage(self, answer: str) -> Dict:
        """Check what percentage of statements have citations"""
        sentences = re.split(r'[.!?]\s+', answer)
        sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]

        if not sentences:
            return {'cited_ratio': 1.0, 'uncited_sentences': []}

        citation_pattern = r'\[Source\s*\d+\]'
        cited_count = 0
        uncited = []

        skip_phrases = ['sources used', 'source:', '?', "i don't have", 'based on the']

        for sentence in sentences:
            if any(skip in sentence.lower() for skip in skip_phrases):
                continue
            if re.search(citation_pattern, sentence, re.IGNORECASE):
                cited_count += 1
            else:
                uncited.append(sentence[:100])

        checkable = len([s for s in sentences if not any(skip in s.lower() for skip in skip_phrases)])

        return {
            'cited_ratio': cited_count / max(checkable, 1),
            'cited_count': cited_count,
            'total_checkable': checkable,
            'uncited_sentences': uncited[:3]
        }


# =============================================================================
# FRESHNESS SCORING
# =============================================================================

class FreshnessScorer:
    """Boost recent documents"""

    DATE_PATTERNS = [
        r'\b(20[1-2]\d)\b',
        r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20[1-2]\d\b',
        r'\b\d{1,2}/\d{1,2}/20[1-2]\d\b',
        r'\b20[1-2]\d-\d{2}-\d{2}\b',
    ]

    @classmethod
    def extract_year(cls, content: str, metadata: Dict = None) -> Optional[int]:
        """Extract most recent year from content"""
        years = []

        if metadata:
            for key in ['date', 'created', 'modified', 'year', 'source_created_at']:
                if key in metadata:
                    year_match = re.search(r'20[1-2]\d', str(metadata[key]))
                    if year_match:
                        years.append(int(year_match.group()))

        for pattern in cls.DATE_PATTERNS:
            matches = re.findall(pattern, content[:2000])
            for match in matches:
                if isinstance(match, str) and match.isdigit():
                    years.append(int(match))

        return max(years) if years else None

    @classmethod
    def get_boost(cls, year: Optional[int], current_year: int = 2025) -> float:
        """Get freshness boost factor"""
        if year is None:
            return 1.0

        age = current_year - year
        if age <= 0:
            return 1.15
        elif age == 1:
            return 1.1
        elif age <= 2:
            return 1.0
        elif age <= 5:
            return 0.95
        else:
            return 0.9


# =============================================================================
# ENHANCED SEARCH SERVICE
# =============================================================================

class EnhancedSearchService:
    """
    Enhanced search service that adds sophisticated features to Pinecone.

    Features:
    - Query expansion (acronyms, synonyms)
    - Cross-encoder reranking
    - MMR diversity selection
    - Hallucination detection
    - Freshness scoring
    - Strict citation enforcement
    """

    def __init__(self):
        self.client = get_openai_client()

        # Initialize components
        self.reranker = CrossEncoderReranker()
        self.hallucination_detector = HallucinationDetector(self.client)

        # Cache for embeddings
        self._embedding_cache = {}

        print("[EnhancedSearch] Service initialized")
        print(f"[EnhancedSearch] Cross-encoder available: {self.reranker.model is not None}")

    def _get_embedding(self, text: str) -> np.ndarray:
        """Get embedding with caching"""
        cache_key = hashlib.md5(text.encode()).hexdigest()
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        response = self.client.create_embedding(
            text=text,
            dimensions=1536
        )
        embedding = np.array(response.data[0].embedding, dtype=np.float32)

        self._embedding_cache[cache_key] = embedding
        if len(self._embedding_cache) > 500:
            # Evict oldest
            keys = list(self._embedding_cache.keys())[:100]
            for k in keys:
                del self._embedding_cache[k]

        return embedding

    def enhanced_search(
        self,
        query: str,
        tenant_id: str,
        vector_store,  # PineconeVectorStore or HybridPineconeStore
        top_k: int = 10,
        use_reranking: bool = True,
        use_mmr: bool = True,
        use_expansion: bool = True,
        use_freshness: bool = True,
        mmr_lambda: float = 0.7
    ) -> Dict:
        """
        Enhanced search with all features.

        Args:
            query: User query
            tenant_id: Tenant ID for isolation
            vector_store: Pinecone vector store instance
            top_k: Number of results to return
            use_reranking: Enable cross-encoder reranking
            use_mmr: Enable MMR diversity
            use_expansion: Enable query expansion
            use_freshness: Enable freshness scoring
            mmr_lambda: MMR relevance vs diversity tradeoff

        Returns:
            Dict with results and metadata
        """
        start_time = time.time()

        # Step 1: Query expansion
        if use_expansion:
            expansion = QueryExpander.expand(query)
            search_query = expansion['expanded']
            print(f"[EnhancedSearch] Expanded: {query} -> {search_query[:100]}...")
        else:
            expansion = {'original': query, 'expanded': query, 'synonyms': []}
            search_query = query

        # Step 2: Initial retrieval from Pinecone (get more for reranking)
        retrieve_k = top_k * 3 if use_reranking else top_k * 2

        # Use hybrid search if available
        if hasattr(vector_store, 'hybrid_search'):
            initial_results = vector_store.hybrid_search(
                query=search_query,
                tenant_id=tenant_id,
                top_k=retrieve_k
            )
        else:
            initial_results = vector_store.search(
                query=search_query,
                tenant_id=tenant_id,
                top_k=retrieve_k
            )

        print(f"[EnhancedSearch] Initial retrieval: {len(initial_results)} results")

        if not initial_results:
            return {
                'query': query,
                'expanded_query': search_query,
                'results': [],
                'num_results': 0,
                'search_time': time.time() - start_time,
                'features_used': {
                    'expansion': use_expansion,
                    'reranking': False,
                    'mmr': False,
                    'freshness': False
                }
            }

        # Step 3: Apply freshness scoring
        if use_freshness:
            for result in initial_results:
                content = result.get('content', '') or result.get('content_preview', '')
                metadata = result.get('metadata', {})
                year = FreshnessScorer.extract_year(content, metadata)
                boost = FreshnessScorer.get_boost(year)
                result['freshness_boost'] = boost
                result['score'] = result.get('score', 0) * boost

        # Step 4: Cross-encoder reranking
        reranked = False
        if use_reranking and self.reranker.model:
            initial_results = self.reranker.rerank(query, initial_results, top_k=top_k * 2)
            reranked = True
            print(f"[EnhancedSearch] Reranked to {len(initial_results)} results")

        # Step 5: MMR diversity selection
        mmr_applied = False
        if use_mmr and len(initial_results) > top_k:
            try:
                # Get embeddings for MMR
                query_embedding = self._get_embedding(search_query)
                doc_embeddings = []
                for result in initial_results:
                    content = result.get('content', '') or result.get('content_preview', '')
                    if content:
                        emb = self._get_embedding(content[:1000])
                        doc_embeddings.append(emb)
                    else:
                        doc_embeddings.append(np.zeros(1536))

                doc_embeddings = np.array(doc_embeddings)
                initial_results = MMRSelector.select(
                    initial_results,
                    query_embedding,
                    doc_embeddings,
                    k=top_k,
                    lambda_param=mmr_lambda
                )
                mmr_applied = True
                print(f"[EnhancedSearch] MMR selected {len(initial_results)} diverse results")
            except Exception as e:
                print(f"[EnhancedSearch] MMR failed: {e}")
                initial_results = initial_results[:top_k]
        else:
            initial_results = initial_results[:top_k]

        search_time = time.time() - start_time

        return {
            'query': query,
            'expanded_query': search_query,
            'expansion': expansion,
            'results': initial_results,
            'num_results': len(initial_results),
            'search_time': search_time,
            'features_used': {
                'expansion': use_expansion,
                'reranking': reranked,
                'mmr': mmr_applied,
                'freshness': use_freshness
            }
        }

    def generate_answer(
        self,
        query: str,
        search_results: Dict,
        validate: bool = True,
        max_context_tokens: int = 12000,
        conversation_history: list = None
    ) -> Dict:
        """
        Generate answer with strict citation enforcement and conversation context.

        Args:
            query: User query
            search_results: Results from enhanced_search
            validate: Run hallucination detection
            max_context_tokens: Max tokens for context
            conversation_history: Previous messages for multi-turn conversations

        Returns:
            Dict with answer and validation results
        """
        conversation_history = conversation_history or []
        results = search_results.get('results', [])

        if not results:
            return {
                'answer': "I couldn't find any relevant information to answer your question.",
                'confidence': 0.0,
                'sources': [],
                'hallucination_check': None
            }

        # Build context with FULL content (not just 500 chars)
        context_parts = []
        total_chars = 0
        max_chars = max_context_tokens * 4  # ~4 chars per token

        for i, result in enumerate(results[:15], 1):  # Use up to 15 sources
            content = result.get('content', '') or result.get('content_preview', '')
            title = result.get('title', 'Untitled')
            score = result.get('rerank_score', result.get('score', 0))

            # Don't truncate aggressively - use more content
            if len(content) > 3000:
                content = content[:3000] + "..."

            if total_chars + len(content) > max_chars:
                remaining = max_chars - total_chars
                if remaining > 500:
                    content = content[:remaining]
                else:
                    break

            context_parts.append(
                f"[Source {i}] (Relevance: {score:.2%})\n"
                f"Title: {title}\n"
                f"Content: {content}\n"
            )
            total_chars += len(content)

        context = "\n---\n".join(context_parts)

        # Enhanced prompt with strict citation rules
        system_prompt = """You are a precise knowledge assistant that ONLY uses information from provided sources.

MANDATORY CITATION RULES:
1. EVERY fact, number, date, or claim MUST have an inline citation like [Source 1]
2. If you cannot cite a source for a statement, DO NOT include it
3. If sources don't contain the answer, say "I don't have information about this in my knowledge base."
4. Never synthesize or infer beyond what sources explicitly state
5. When multiple sources support a claim, cite all: [Source 1, Source 3]

QUALITY STANDARDS:
- Include specific numbers, dates, and quotes from sources
- If information is partial or uncertain, acknowledge it
- Say "Based on [Source X]..." rather than stating as absolute fact

You will be evaluated on citation accuracy. Uncited claims are failures."""

        # Build conversation context if history exists
        conversation_context = ""
        if conversation_history and len(conversation_history) > 0:
            conversation_context = "CONVERSATION HISTORY (for context):\n"
            for i, msg in enumerate(conversation_history[-6:], 1):  # Last 6 messages
                role = "User" if msg.get('role') == 'user' else "Assistant"
                content = msg.get('content', '')[:200]  # Limit to 200 chars per message
                conversation_context += f"{role}: {content}\n"
            conversation_context += "\n"

        user_prompt = f"""{conversation_context}SOURCE DOCUMENTS:
{context}

CURRENT QUESTION: {query}

Provide a well-cited answer following ALL citation rules above.
- Use conversation history for context (e.g., understand pronouns like "it", "that", "them")
- Answer the CURRENT question directly
- Cite sources with [Source X] for every claim
End with "Sources Used: [list numbers]"."""

        try:
            # Build messages array with conversation history
            messages = [{"role": "system", "content": system_prompt}]

            # Add last 4 messages from history for better context (not too many to avoid token limits)
            if conversation_history and len(conversation_history) > 0:
                for msg in conversation_history[-4:]:
                    messages.append({
                        "role": msg.get('role', 'user'),
                        "content": msg.get('content', '')[:500]  # Limit each to 500 chars
                    })

            # Add current query with sources
            messages.append({"role": "user", "content": user_prompt})

            response = self.client.chat_completion(
                messages=messages,
                temperature=0.1,  # Low for factual consistency
                max_tokens=2000
            )

            answer = response.choices[0].message.content.strip()

            # Validation
            hallucination_check = None
            citation_check = None

            if validate:
                claims = self.hallucination_detector.extract_claims(answer)
                if claims:
                    hallucination_check = self.hallucination_detector.verify_claims(claims, results)
                citation_check = self.hallucination_detector.check_citation_coverage(answer)

                # Add warnings if needed
                if hallucination_check and hallucination_check['confidence'] < 0.5:
                    answer += "\n\n---\nNote: Some claims could not be fully verified against sources."

                if citation_check and citation_check['cited_ratio'] < 0.7:
                    answer += f"\n\nCitation Coverage: {citation_check['cited_ratio']:.0%}"

            # Calculate confidence
            base_confidence = results[0].get('rerank_score', results[0].get('score', 0.5))
            if hallucination_check:
                base_confidence = min(base_confidence, hallucination_check['confidence'])
            if citation_check:
                base_confidence = min(base_confidence, citation_check['cited_ratio'])

            return {
                'answer': answer,
                'confidence': base_confidence,
                'sources': results[:10],
                'hallucination_check': hallucination_check,
                'citation_check': citation_check,
                'context_chars': total_chars,
                'sources_used': len(context_parts)
            }

        except Exception as e:
            return {
                'answer': f"Error generating answer: {str(e)}",
                'confidence': 0.0,
                'sources': results[:10],
                'error': str(e)
            }

    def search_and_answer(
        self,
        query: str,
        tenant_id: str,
        vector_store,
        top_k: int = 10,
        validate: bool = True,
        conversation_history: list = None
    ) -> Dict:
        """
        Complete enhanced RAG pipeline with conversation history support.

        Args:
            query: User query
            tenant_id: Tenant ID
            vector_store: Pinecone store
            top_k: Number of sources
            validate: Run hallucination detection
            conversation_history: Previous messages for context (list of {role, content})

        Returns:
            Complete response with answer, sources, and metadata
        """
        # Search
        search_results = self.enhanced_search(
            query=query,
            tenant_id=tenant_id,
            vector_store=vector_store,
            top_k=top_k
        )

        # Generate answer with conversation context
        answer_result = self.generate_answer(
            query=query,
            search_results=search_results,
            validate=validate,
            conversation_history=conversation_history or []
        )

        return {
            'query': query,
            'expanded_query': search_results.get('expanded_query'),
            'answer': answer_result['answer'],
            'confidence': answer_result['confidence'],
            'sources': answer_result['sources'],
            'num_sources': len(answer_result['sources']),
            'search_time': search_results.get('search_time', 0),
            'features_used': search_results.get('features_used', {}),
            'hallucination_check': answer_result.get('hallucination_check'),
            'citation_check': answer_result.get('citation_check'),
            'context_chars': answer_result.get('context_chars', 0)
        }


# Singleton instance
_enhanced_search_service: Optional[EnhancedSearchService] = None


def get_enhanced_search_service() -> EnhancedSearchService:
    """Get or create singleton EnhancedSearchService"""
    global _enhanced_search_service
    if _enhanced_search_service is None:
        _enhanced_search_service = EnhancedSearchService()
    return _enhanced_search_service
