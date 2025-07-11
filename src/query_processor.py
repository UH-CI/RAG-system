"""
Multi-step Query Processor for Course RAG System
Implements reasoning -> searching -> answering pipeline
"""

import json
import google.generativeai as genai
from typing import List, Dict, Any, Optional
from pathlib import Path

# Handle both relative and absolute imports
try:
    from .settings import settings
except ImportError:
    from settings import settings


class QueryProcessor:
    """Advanced query processor with multi-step reasoning"""
    
    def __init__(self, collection_managers: Dict[str, Any], config: Dict[str, Any]):
        self.collection_managers = collection_managers
        self.config = config
        self.collection_names = config["collections"]
        
        # Initialize Gemini model
        self.model = genai.GenerativeModel('gemini-1.5-flash')
    
    def get_collection_sample(self, collection_name: str) -> Dict[str, Any]:
        """Get a sample document from a collection for context"""
        try:
            if collection_name not in self.collection_managers:
                return {}
                
            manager = self.collection_managers[collection_name]
            collection = manager.collection
            
            # Get one document as sample
            results = collection.get(limit=1, include=['metadatas'])
            
            if results and results['metadatas'] and len(results['metadatas']) > 0:
                metadata = results['metadatas'][0]
                
                # Remove system metadata for cleaner example
                clean_metadata = {k: v for k, v in metadata.items() 
                                if k not in ['id', 'collection', 'embedded_fields']}
                
                return clean_metadata
                
        except Exception as e:
            print(f"Error getting sample from {collection_name}: {e}")
            
        return {}
    
    def get_collection_context(self) -> str:
        """Generate context about available collections and their structure"""
        context_parts = []
        
        context_parts.append("Available Collections:")
        
        for collection_name in self.collection_names:
            # Get ingestion config for this collection
            ingestion_config = None
            for config_item in self.config.get("ingestion_configs", []):
                if config_item.get("collection_name") == collection_name:
                    ingestion_config = config_item
                    break
            
            if ingestion_config:
                embedded_fields = ingestion_config.get("contents_to_embed", [])
                context_parts.append(f"\n{collection_name.upper()} Collection:")
                context_parts.append(f"  - Searchable fields: {', '.join(embedded_fields)}")
                
                # Get sample document
                sample = self.get_collection_sample(collection_name)
                if sample:
                    context_parts.append(f"  - Sample document structure: {json.dumps(sample, indent=4)}")
                else:
                    context_parts.append(f"  - No sample documents available")
        
        return "\n".join(context_parts)
    
    def reasoning_step(self, user_query: str) -> Dict[str, Any]:
        """Step 1: Analyze user query and determine search strategy"""
        
        collection_context = self.get_collection_context()
        
        reasoning_prompt = f"""You are an intelligent query analyzer for a university course and program database. 

CONTEXT:
{collection_context}

USER QUERY: "{user_query}"

Analyze the user's query and provide a structured response with:

1. INTENT: What is the user trying to accomplish? (e.g., "find courses", "compare programs", "get requirements")

2. TARGET_COLLECTIONS: Which collections should be searched? Choose from: {', '.join(self.collection_names)}

3. SEARCH_TERMS: Generate 3-5 specific search terms or phrases that would help find relevant documents. Think about:
   - Key concepts from the query
   - Synonyms and related terms
   - Academic terminology that might appear in course/program descriptions

4. SEARCH_STRATEGY: Brief explanation of how to approach this search

Respond in JSON format:
{{
    "intent": "brief description of user intent",
    "target_collections": ["collection1", "collection2"],
    "search_terms": ["term1", "term2", "term3"],
    "search_strategy": "explanation of search approach",
    "confidence": "high/medium/low"
}}
"""
        
        try:
            response = self.model.generate_content(reasoning_prompt)
            
            # Try to parse JSON response
            try:
                reasoning_result = json.loads(response.text)
                
                # Validate collections exist
                valid_collections = [c for c in reasoning_result.get("target_collections", []) 
                                   if c in self.collection_names]
                
                if not valid_collections:
                    valid_collections = self.collection_names  # Use all if none valid
                
                reasoning_result["target_collections"] = valid_collections
                
                print(f"🧠 Reasoning Step Results:")
                print(f"   Intent: {reasoning_result.get('intent', 'Unknown')}")
                print(f"   Collections: {valid_collections}")
                print(f"   Search terms: {reasoning_result.get('search_terms', [])}")
                print(f"   Confidence: {reasoning_result.get('confidence', 'unknown')}")
                
                return reasoning_result
                
            except json.JSONDecodeError:
                print(f"❌ Failed to parse reasoning response as JSON: {response.text}")
                # Fallback
                return {
                    "intent": "general search",
                    "target_collections": self.collection_names,
                    "search_terms": [user_query],
                    "search_strategy": "basic keyword search",
                    "confidence": "low"
                }
                
        except Exception as e:
            print(f"❌ Error in reasoning step: {e}")
            # Fallback
            return {
                "intent": "general search",
                "target_collections": self.collection_names,
                "search_terms": [user_query],
                "search_strategy": "basic keyword search",
                "confidence": "low"
            }
    
    def searching_step(self, reasoning_result: Dict[str, Any], threshold: float = 0.5) -> List[Dict[str, Any]]:
        """Step 2: Execute searches based on reasoning results with similarity threshold filtering"""
        
        target_collections = reasoning_result.get("target_collections", self.collection_names)
        search_terms = reasoning_result.get("search_terms", [])
        
        all_results = []
        
        print(f"🔍 Searching Step:")
        print(f"   Collections: {target_collections}")
        print(f"   Terms: {search_terms}")
        print(f"   Threshold: {threshold}")
        
        # Search with each term across target collections
        # Use a high num_results to get more candidates for threshold filtering
        max_candidates = 50  # Get more results to filter by threshold
        
        for search_term in search_terms:
            for collection_name in target_collections:
                try:
                    if collection_name in self.collection_managers:
                        manager = self.collection_managers[collection_name]
                        results = manager.search_similar_chunks(search_term, max_candidates)
                        
                        # Filter results by threshold
                        filtered_results = []
                        for result in results:
                            score = result.get("score", 0.0)
                            if score >= threshold:
                                # Add search context to each result
                                result["metadata"]["collection"] = collection_name
                                result["metadata"]["search_term"] = search_term
                                result["metadata"]["reasoning_intent"] = reasoning_result.get("intent", "unknown")
                                filtered_results.append(result)
                        
                        all_results.extend(filtered_results)
                        print(f"   {collection_name} with '{search_term}': {len(results)} total, {len(filtered_results)} above threshold")
                            
                except Exception as e:
                    print(f"Error searching {collection_name} with term '{search_term}': {e}")
                    continue
        
        # Remove duplicates based on document ID and sort by score
        seen_ids = set()
        unique_results = []
        
        for result in all_results:
            doc_id = result["metadata"].get("id", "")
            if doc_id and doc_id not in seen_ids:
                seen_ids.add(doc_id)
                unique_results.append(result)
        
        # Sort by score (higher is better)
        if unique_results and "score" in unique_results[0]:
            unique_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        print(f"   Found {len(all_results)} total results, {len(unique_results)} unique above threshold")
        
        return unique_results
    
    def answering_step(self, user_query: str, reasoning_result: Dict[str, Any], 
                      search_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Step 3: Generate comprehensive answer based on retrieved documents"""
        
        if not search_results:
            return {
                "response": "I couldn't find any relevant documents to answer your query. Please try rephrasing your question or being more specific.",
                "sources": [],
                "reasoning": reasoning_result,
                "total_documents_found": 0
            }
        
        # Prepare context from search results
        context_parts = []
        sources = []
        
        for i, result in enumerate(search_results):
            context_parts.append(f"Document {i+1}:")
            context_parts.append(f"Content: {result['content']}")
            context_parts.append(f"Collection: {result['metadata'].get('collection', 'unknown')}")
            context_parts.append("---")
            
            # Prepare source info for response
            sources.append({
                "content": result["content"][:300] + "..." if len(result["content"]) > 300 else result["content"],
                "metadata": {k: v for k, v in result["metadata"].items() 
                           if k not in ['search_term', 'reasoning_intent']},  # Clean up metadata
                "score": result.get("score"),
                "collection": result["metadata"].get("collection", "unknown")
            })
        
        context = "\n".join(context_parts)
        
        # Generate comprehensive answer
        answer_prompt = f"""You are an expert advisor for university courses and programs. Based on the retrieved documents, provide a comprehensive and helpful answer to the user's query.

USER QUERY: "{user_query}"

SEARCH INTENT: {reasoning_result.get('intent', 'Unknown')}

RETRIEVED DOCUMENTS:
{context}

Instructions:
1. Provide a direct, helpful answer to the user's question
2. Reference specific information from the documents when possible
3. If comparing options, organize the information clearly
4. If the documents don't fully answer the question, mention what information is available and what might be missing
5. Be conversational but informative
6. Use bullet points or numbered lists when appropriate for readability

Answer:"""
        
        try:
            response = self.model.generate_content(answer_prompt)
            
            return {
                "response": response.text,
                "sources": sources,
                "reasoning": {
                    "intent": reasoning_result.get("intent"),
                    "search_terms": reasoning_result.get("search_terms"),
                    "collections_searched": reasoning_result.get("target_collections"),
                    "confidence": reasoning_result.get("confidence")
                },
                "total_documents_found": len(search_results)
            }
            
        except Exception as e:
            print(f"❌ Error generating answer: {e}")
            return {
                "response": f"I found relevant documents but encountered an error generating the response: {str(e)}",
                "sources": sources,
                "reasoning": reasoning_result,
                "total_documents_found": len(search_results)
            }
    
    def process_query(self, user_query: str, threshold: float = 0.5) -> Dict[str, Any]:
        """Main method: Execute the complete query processing pipeline with threshold filtering"""
        
        print(f"🚀 Processing query: '{user_query}' with threshold: {threshold}")
        
        try:
            # Step 1: Reasoning
            reasoning_result = self.reasoning_step(user_query)
            
            # Step 2: Searching with threshold
            search_results = self.searching_step(reasoning_result, threshold)
            
            # Step 3: Answering
            final_result = self.answering_step(user_query, reasoning_result, search_results)
            
            print(f"✅ Query processing complete - {len(search_results)} documents above threshold")
            
            return final_result
            
        except Exception as e:
            print(f"❌ Error in query processing pipeline: {e}")
            return {
                "response": f"I encountered an error while processing your query: {str(e)}",
                "sources": [],
                "reasoning": {"error": str(e)},
                "total_documents_found": 0
            } 