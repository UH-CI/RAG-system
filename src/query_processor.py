"""
Multi-step Query Processor for Course RAG System
Implements reasoning -> searching -> answering pipeline
"""

import json
import re
import requests
import google.generativeai as genai
from typing import List, Dict, Any, Optional
from pathlib import Path

# Handle both relative and absolute imports
try:
    from .settings import settings
except ImportError:
    from settings import settings

import time


def _extract_json_from_response(text: str) -> Optional[Dict[str, Any]]:
    """Extracts a JSON object from a string, even if it's embedded in markdown."""
    # Clean the text first - remove any leading/trailing whitespace
    text = text.strip()
    
    # Handle case where response starts with ``` (markdown code block)
    if text.startswith('```'):
        # Remove the opening ``` and any language identifier
        text = re.sub(r'^```\w*\s*', '', text)
        # Remove the closing ``` if present
        text = re.sub(r'\s*```$', '', text)
    
    # Find the JSON block using a regex (for ```json blocks)
    match = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        json_str = match.group(1)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse extracted JSON from markdown: {e}")
            print(f"Raw JSON string: {json_str}")
            return None
    
    # Try to find JSON object in the text (for cases without markdown)
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse extracted JSON object: {e}")
            print(f"Raw JSON string: {json_str}")
            return None
    
    # If no JSON object found, try to parse the whole string
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse text as JSON: {e}")
        print(f"Raw text: {text[:200]}...")  # Show first 200 chars for debugging
        return None


class QueryProcessor:
    """Advanced query processor with multi-step reasoning"""
    
    def __init__(self, collection_managers: Dict[str, Any], config: Dict[str, Any]):
        self.collection_managers = collection_managers
        self.config = config
        self.collection_names = config["collections"]
        
        # Initialize Gemini model (fallback)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        
        # LLaMA API configuration
        self.llama_api_key = "bfa9578e-8707-4f32-a07c-4de1ffcd1a77"
        self.llama_url = "https://tejas.tacc.utexas.edu/v1/c31853e6-0a58-4483-9e92-e7c32b021d44/chat/completions"
        self.llama_model = "Meta-Llama-3.1-405B-Instruct"
    
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
    
    def call_llama_api(self, messages: List[Dict[str, str]]) -> str:
        """
        Calls the LLaMA chat API with given messages.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content' keys
            
        Returns:
            str: The response content from the API
        """
        headers = {
            "Authorization": f"Bearer {self.llama_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "stream": False,
            "model": self.llama_model,
            "messages": messages
        }
        
        try:
            response = requests.post(
                self.llama_url, 
                headers=headers, 
                data=json.dumps(payload),
                timeout=60
            )
            response.raise_for_status()
            
            response_data = response.json()
            
            # Extract the content from the response
            if (response_data.get("choices") and 
                len(response_data["choices"]) > 0 and 
                response_data["choices"][0].get("message")):
                
                return response_data["choices"][0]["message"]["content"]
            else:
                print(f"❌ Unexpected LLaMA API response format: {response_data}")
                return "Error: Unexpected response format from LLaMA API"
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Error calling LLaMA API: {e}")
            return f"Error: Failed to call LLaMA API - {str(e)}"
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing LLaMA API response: {e}")
            return "Error: Failed to parse LLaMA API response"
    
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
    
    def reasoning_step(self, user_query: str, conversation_history: Optional[List[str]] = None) -> Dict[str, Any]:
        """Step 1: Analyze user query and determine search strategy"""
        
        collection_context = self.get_collection_context()
        
        # Add conversation context if available
        conversation_context = ""
        if conversation_history and len(conversation_history) > 0:
            recent_history = conversation_history[-4:]  # Only use last 4 messages to keep context manageable
            conversation_context = f"""
CONVERSATION HISTORY (for context):
{chr(10).join(f"- {msg}" for msg in recent_history)}

"""
        
        # Prepare messages for LLaMA API
        messages = [
            {
                "role": "system",
                "content": """You are an intelligent query analyzer for a document database system. Your task is to deconstruct a user's query into a structured search plan.

Based on the user's query and the available data, provide a structured response with the following components:

1. **INTENT**: Briefly describe what the user is trying to accomplish.
2. **HYPOTHETICAL_ANSWER**: Generate a concise, hypothetical answer to the user's query. This answer should be a short paragraph that sounds like a plausible response, even if you don't know the exact details. This will be used to find semantically similar documents.
3. **KEYWORDS**: Provide exactly TWO specific keywords or key phrases for a keyword-based search. These should be distinct and likely to appear in relevant documents.
4. **TARGET_COLLECTIONS**: Identify the most relevant collections to search from the provided list.
5. **CONFIDENCE**: Rate your confidence in this plan (high/medium/low).

Respond in JSON format:
{
    "intent": "brief description of user intent",
    "hypothetical_answer": "A short, plausible answer to the user's query.",
    "keywords": ["keyword1", "keyword2"],
    "target_collections": ["collection1", "collection2"],
    "confidence": "high/medium/low"
}"""
            }
        ]
        
        # Add conversation context if available
        if conversation_context:
            messages.append({
                "role": "user",
                "content": f"Previous conversation context:\n{conversation_context}"
            })
        
        # Add the main query with context
        user_message = f"""CONTEXT ON AVAILABLE DATA:
{collection_context}

USER QUERY: "{user_query}"

Available collections: {', '.join(self.collection_names)}"""
        
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        try:
            # Try LLaMA API first
            response_text = self.call_llama_api(messages)
            
            # Debug: Print the raw response for troubleshooting
            print(f"🔍 LLaMA API raw response: {response_text[:500]}...")
            
            # Try to parse JSON response
            reasoning_result = _extract_json_from_response(response_text)
            
            # Check if LLaMA API returned an error or failed to parse
            if not reasoning_result or response_text.startswith("Error:"):
                print(f"⚠️ LLaMA API failed for reasoning, falling back to Gemini")
                print(f"Response text: {response_text[:200]}...")
                # Fallback to Gemini
                reasoning_prompt = f"""You are an intelligent query analyzer for a document database system. Your task is to deconstruct a user's query into a structured search plan.

CONTEXT ON AVAILABLE DATA:
{collection_context}

{conversation_context}USER QUERY: "{user_query}"

Based on the user's query and the available data, provide a structured response with the following components:

1.  **INTENT**: Briefly describe what the user is trying to accomplish.
2.  **HYPOTHETICAL_ANSWER**: Generate a concise, hypothetical answer to the user's query. This answer should be a short paragraph that sounds like a plausible response, even if you don't know the exact details. This will be used to find semantically similar documents.
3.  **KEYWORDS**: Provide exactly TWO specific keywords or key phrases for a keyword-based search. These should be distinct and likely to appear in relevant documents.
4.  **TARGET_COLLECTIONS**: Identify the most relevant collections to search from this list: {', '.join(self.collection_names)}.
5.  **CONFIDENCE**: Rate your confidence in this plan (high/medium/low).

Respond in JSON format:
{{
    "intent": "brief description of user intent",
    "hypothetical_answer": "A short, plausible answer to the user's query.",
    "keywords": ["keyword1", "keyword2"],
    "target_collections": ["collection1", "collection2"],
    "confidence": "high/medium/low"
}}
"""
                response = self.model.generate_content(reasoning_prompt)
                reasoning_result = _extract_json_from_response(response.text)

            if reasoning_result:
                # Validate collections exist
                valid_collections = [c for c in reasoning_result.get("target_collections", []) 
                                   if c in self.collection_names]
                
                if not valid_collections:
                    valid_collections = self.collection_names  # Use all if none valid
                
                reasoning_result["target_collections"] = valid_collections
                
                print(f"🧠 Reasoning Step")
                # Add a print statement to display the generated reasoning
                print(json.dumps(reasoning_result, indent=2))
                
                return reasoning_result
            else:
                print(f"❌ Failed to parse reasoning response as JSON: {response.text}")
                # Fallback
                return {
                    "intent": "general search",
                    "query_type": "document_search",
                    "target_collections": self.collection_names,
                    "search_terms": [user_query],
                    "search_strategy": "basic keyword search",
                    "output_format": "informational",
                    "confidence": "low"
                }
                
        except Exception as e:
            print(f"❌ Error in reasoning step: {e}")
            # Fallback
            return {
                "intent": "general search",
                "query_type": "document_search",
                "target_collections": self.collection_names,
                "search_terms": [user_query],
                "search_strategy": "basic keyword search",
                "output_format": "informational",
                "confidence": "low"
            }
    
    def searching_step(self, reasoning_result: Dict[str, Any], threshold: float, k: int) -> List[Dict[str, Any]]:
        """
        Step 2: Execute hybrid search based on reasoning results.
        - 2/3 of k are retrieved via keyword search.
        - 1/3 of k are retrieved via dense vector search.
        """
        target_collections = reasoning_result.get("target_collections", self.collection_names)
        keywords = reasoning_result.get("keywords", [])
        hypothetical_answer = reasoning_result.get("hypothetical_answer", "")

        print(f"🔍 Hybrid Searching Step:")
        print(f"   Collections: {target_collections}")
        print(f"   Keywords: {keywords}")
        print(f"   Hypothetical Answer: {hypothetical_answer[:80]}...")
        print(f"   Threshold: {threshold}, K: {k}")

        # Allocate K between keyword and dense search
        k_keyword = (k * 2) // 3
        k_dense = k - k_keyword
        
        all_results = []

        # --- Keyword Search (Sparse) ---
        if keywords:
            for collection_name in target_collections:
                try:
                    manager = self.collection_managers.get(collection_name)
                    if manager:
                        keyword_results = manager.keyword_search(keywords, num_results=k_keyword)
                        for res in keyword_results:
                            res["metadata"]["search_method"] = "keyword"
                        all_results.extend(keyword_results)
                        print(f"   Keyword search in '{collection_name}' found {len(keyword_results)} results.")
                except Exception as e:
                    print(f"   Error during keyword search in {collection_name}: {e}")

        # --- Dense Search (Semantic) ---
        if hypothetical_answer:
            for collection_name in target_collections:
                try:
                    manager = self.collection_managers.get(collection_name)
                    if manager:
                        dense_results = manager.search_similar_chunks(hypothetical_answer, num_results=k_dense)
                        # Filter by threshold
                        for res in dense_results:
                            if res.get("score", 0.0) >= threshold:
                                res["metadata"]["search_method"] = "dense"
                                all_results.append(res)
                        print(f"   Dense search in '{collection_name}' found {len(dense_results)} results above threshold.")
                except Exception as e:
                    print(f"   Error during dense search in {collection_name}: {e}")

        # --- Deduplicate and Sort ---
        seen_ids = set()
        unique_results = []
        for result in all_results:
            # Use a unique identifier from metadata if available, otherwise use content
            doc_id = result["metadata"].get("id") or result.get("content")
            if doc_id not in seen_ids:
                seen_ids.add(doc_id)
                unique_results.append(result)
        
        # Sort by score (higher is better). Keyword results have a baseline score.
        unique_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        print(f"   Found {len(all_results)} total results, {len(unique_results)} unique after deduplication.")
        
        return unique_results[:k]
    
    def answering_step(self, user_query: str, reasoning_result: Dict[str, Any], 
                      search_results: List[Dict[str, Any]],conversation_history: Optional[List[str]] = None) -> Dict[str, Any]:
        """Step 3: Generate a direct answer based on the retrieved documents."""
        
        if not search_results:
            return {
                "response": "I'm sorry, but I couldn't find any relevant documents to answer your question. Please try asking the question differently or being more specific.",
                "sources": [],
                "reasoning": reasoning_result
            }
        
        # Prepare context from search results
        context_parts = []
        sources = []

        for i, result in enumerate(search_results):
            context_parts.append(f"{result['metadata']['title']} (Source: {result['metadata'].get('collection', 'unknown')}, \n {result['metadata']}:\n Description: {result['content']}\n---")
            sources.append({
                "content": result["content"],
                "metadata": {k: v for k, v in result["metadata"].items() if k != 'search_method'},
                "score": result.get("score"),
                "collection": result["metadata"].get("collection", "unknown"),
                "source_identifier": result["metadata"].get("source_identifier")
            })
        
        context = "\n".join(context_parts)
                # Add conversation context if available
        conversation_context = ""
        if conversation_history and len(conversation_history) > 0:
            recent_history = conversation_history[-4:]  # Only use last 4 messages to keep context manageable

            print(f"🔍 Conversation history: {json.dumps(recent_history, indent=2, ensure_ascii=False)}")
            conversation_context = f"""
CONVERSATION HISTORY (for context):
{chr(10).join(f"- {msg}" for msg in recent_history)}

"""
        # Prepare messages for LLaMA API
        messages = [
            {
                "role": "system", 
                "content": """You are a helpful assistant. Your task is to answer the user's question based *only* on the provided documents.

Note that these papers are published in the Science Gateways conference.
You are provided with the titles and context. The user knows this. 
You are basically a retriever of the papers and can answer questions about the papers.

INSTRUCTIONS:
1. Carefully read the user's question and the retrieved documents.
2. Formulate a clear and concise answer using only the information found in the documents.
3. If the documents do not contain the information needed to answer the question, you MUST state that clearly. Do not use any outside knowledge.
4. If you cannot answer the question, still try to be informative as best as you can.
5. Be concise and to the point.
Answer the question as if you are talking to the user.
They do not know you have access to the documents -- and they don't need to know.
Treat it as a real conversation.
At maximum, use 1 paragraph to answer the question.
If the question is just asking for a list of documents, just describe the documents.
Answer the question as best as you can. Do not say "I do not know" or "I do not have access to the data"."""
            }
        ]
        
        # Add conversation history if available
        if conversation_context:
            messages.append({
                "role": "user",
                "content": f"Previous conversation context:\n{conversation_context}"
            })
        
        # Add the main query with retrieved documents
        user_message = f"""USER QUESTION:
"{user_query}"

RETRIEVED DOCUMENTS:
---
{context}
---"""
        
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        try:
            # Try LLaMA API first
            response_text = self.call_llama_api(messages)
            
            # Check if LLaMA API returned an error
            if response_text.startswith("Error:"):
                print(f"⚠️ LLaMA API failed, falling back to Gemini: {response_text}")
                # Fallback to Gemini
                answer_prompt = f"""You are a helpful assistant. Your task is to answer the user's question based *only* on the provided documents.

{conversation_context}

USER QUESTION:
"{user_query}"

RETRIEVED DOCUMENTS:
---
{context}
---
Note that these papers are published in the Science Gateways conference.
You are provided with the titles and context. The user knows this. 
You are basically a retriever of the papers and can answer questions about the papers

INSTRUCTIONS:
1.  Carefully read the user's question and the retrieved documents.
2.  Formulate a clear and concise answer using only the information found in the documents.
3.  If the documents do not contain the information needed to answer the question, you MUST state that clearly. Do not use any outside knowledge.
4.  If you cannot answer the question, still try to be informative as best as you can.
5.  Be concise and to the point.
Answer the question as if you are talking to the user.
They do not know you have access to the documents -- and they don't need to know.
Treat it as a real conversation.
At maximum, use 1 paragraph to answer the question.
If the question is just asking for a list of documents, just describe the documents.
Answer the question as best as you can. Do not say "I do not know" or "I do not have access to the data".
"""
                response = self.model.generate_content(answer_prompt)
                response_text = response.text
            
            return {
                "response": response_text,
                "sources": sources,
                "reasoning": reasoning_result
            }
            
        except Exception as e:
            print(f"❌ Error generating answer: {e}")
            return {
                "response": f"I found relevant documents but encountered an error while generating the final response: {str(e)}",
                "sources": sources,
                "reasoning": reasoning_result
            }
    
    def process_query(self, user_query: str, threshold: float, k: int, conversation_history: Optional[List[str]] = None) -> Dict[str, Any]:
        """Main method: Execute the complete query processing pipeline with threshold filtering"""
        
        print(f"🚀 Processing query: '{user_query}' with threshold: {threshold}")
        
        try:
            print(f"🚀 Conversation history: {json.dumps(conversation_history, indent=2, ensure_ascii=False)}")
            start_time = time.time()
            print(f"🚀 Starting query processing at {start_time}")
            # Step 1: Reasoning
            reasoning_result = self.reasoning_step(user_query, conversation_history)
            reasoning_time = time.time() - start_time
            print(f"Reasoning time: {reasoning_time:.2f} seconds")
            
            start_time = time.time()
            print(f"🚀 Starting search at {start_time}")
            
            # Step 2: Searching with threshold
            search_results = self.searching_step(reasoning_result, threshold, k)
            search_time = time.time() - start_time
            print(f"Search time: {search_time:.2f} seconds")
            
            start_time = time.time()
            print(f"🚀 Starting answering at {start_time}")
            
            # Step 3: Answering
            final_result = self.answering_step(user_query, reasoning_result, search_results, conversation_history)
            answering_time = time.time() - start_time
            print(f"Answering time: {answering_time:.2f} seconds")
            
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