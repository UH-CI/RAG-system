"""
LangGraph-based Agentic RAG System
Uses tools to search vector databases and build context before answering
"""

import json
import asyncio
from typing import Dict, List, Any, Optional, TypedDict, Annotated
from pathlib import Path
import time
import uuid
import logging

# LangGraph and LangChain imports
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

# Handle both relative and absolute imports
try:
    from .settings import settings
except ImportError:
    from settings import settings


class AgentState(TypedDict):
    """State for the RAG agent"""
    messages: Annotated[List[BaseMessage], add_messages]
    query: str
    reasoning: Dict[str, Any]
    search_results: List[Dict[str, Any]]
    context: str
    answer: str
    sources: List[Dict[str, Any]]
    collections_searched: List[str]
    search_terms_used: List[str]
    confidence: str
    # Iterative search enhancements
    search_iterations: int
    max_iterations: int
    needs_refinement: bool
    refinement_strategy: Dict[str, Any]
    search_history: List[Dict[str, Any]]
    result_quality_scores: Dict[str, float]
    # Web search results
    web_results: List[Dict[str, Any]]
    # Multi-step reasoning with subquestions
    subquestions: List[Dict[str, Any]]
    hypothetical_answers: List[Dict[str, Any]]
    subquestion_results: List[Dict[str, Any]]
    subquestion_answers: List[Dict[str, Any]]
    final_synthesis_context: str
    parallel_processing_enabled: bool
    # Primary collection support for single PDF analysis
    primary_collection: Optional[str]
    primary_document_text: Optional[str]
    context_collections: List[str]


class LangGraphRAGAgent:
    """LangGraph-based RAG agent with tool usage"""
    
    def __init__(self, collection_managers: Dict[str, Any], config: Dict[str, Any]):
        self.collection_managers = collection_managers
        self.config = config
        self.collection_names = config["collections"]
        
        # Initialize the LLM
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0.3,  # Increased from 0.1 to encourage longer, more comprehensive responses
            max_tokens=25000  # Increased for comprehensive fiscal notes with primary document context
        )
        
        # Create tools
        self.tools = self._create_tools()
        
        # Create the graph
        self.graph = self._create_graph()
    
    def _fetch_primary_document_text(self, primary_collection: str) -> Optional[str]:
        """
        Fetch the primary document text from the chunked_text directory.
        
        Args:
            primary_collection: Name of the primary collection
            
        Returns:
            Combined text from all chunks in the primary document, or None if not found
        """
        try:
            import os
            import json
            
            # Path to the chunked text collection
            collection_path = os.path.join("documents", "chunked_text", primary_collection)
            
            if not os.path.exists(collection_path):
                logging.warning(f"Primary collection path not found: {collection_path}")
                return None
            
            # Find JSON files (excluding metadata files)
            json_files = [f for f in os.listdir(collection_path) 
                         if f.endswith('.json') and not f.endswith('_metadata.json')]
            
            if not json_files:
                logging.warning(f"No document files found in primary collection: {primary_collection}")
                return None
            
            combined_text = []
            
            for json_file in json_files:
                file_path = os.path.join(collection_path, json_file)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Extract text from chunks
                    if isinstance(data, list):
                        for chunk in data:
                            if isinstance(chunk, dict) and 'text' in chunk:
                                combined_text.append(chunk['text'])
                    elif isinstance(data, dict) and 'text' in data:
                        combined_text.append(data['text'])
                        
                except Exception as e:
                    logging.error(f"Error reading file {json_file}: {e}")
                    continue
            
            if combined_text:
                full_text = "\n\n".join(combined_text)
                logging.info(f"Successfully loaded primary document text: {len(full_text)} characters from {len(json_files)} files")
                return full_text
            else:
                logging.warning(f"No text content found in primary collection: {primary_collection}")
                return None
                
        except Exception as e:
            logging.error(f"Error fetching primary document text: {e}")
            return None
    
    def _create_tools(self) -> List:
        """Create tools for the agent to use"""
        
        @tool
        def search_collection(collection_name: str, query: str, num_results: int = 50) -> str:
            """
            Search a specific collection for documents related to the query.
            
            Args:
                collection_name: Name of the collection to search (budget, text, fiscal)
                query: Search query or term
                num_results: Number of results to return
            
            Returns:
                JSON string containing search results
            """
            if collection_name not in self.collection_managers:
                return json.dumps({"error": f"Collection {collection_name} not found"})
            
            try:
                manager = self.collection_managers[collection_name]
                results = manager.search_similar_chunks(query, num_results)
                
                # Format results for the agent
                formatted_results = []
                for result in results:
                    # Ensure metadata includes collection name for proper source attribution
                    metadata = result.get("metadata", {})
                    metadata["collection"] = collection_name
                    
                    formatted_results.append({
                        "content": result["content"],
                        "metadata": metadata,
                        "score": result.get("score", 0.0),
                        "collection": collection_name  # Keep for backwards compatibility
                    })
                
                return json.dumps({
                    "collection": collection_name,
                    "query": query,
                    "results_count": len(formatted_results),
                    "results": formatted_results
                })
                
            except Exception as e:
                return json.dumps({"error": f"Error searching {collection_name}: {str(e)}"})
        
        @tool
        def get_collection_info(collection_name: str) -> str:
            """
            Get information about a collection including sample documents and structure.
            
            Args:
                collection_name: Name of the collection
            
            Returns:
                JSON string with collection information
            """
            if collection_name not in self.collection_managers:
                return json.dumps({"error": f"Collection {collection_name} not found"})
            
            try:
                # Get ingestion config
                ingestion_config = None
                for config_item in self.config.get("ingestion_configs", []):
                    if config_item.get("collection_name") == collection_name:
                        ingestion_config = config_item
                        break
                
                # Get sample document
                manager = self.collection_managers[collection_name]
                collection = manager.collection
                results = collection.get(limit=1, include=['metadatas'])
                
                sample_metadata = {}
                if results and results['metadatas'] and len(results['metadatas']) > 0:
                    metadata = results['metadatas'][0]
                    sample_metadata = {k: v for k, v in metadata.items() 
                                     if k not in ['id', 'collection', 'embedded_fields']}
                
                return json.dumps({
                    "collection_name": collection_name,
                    "embedded_fields": ingestion_config.get("contents_to_embed", []) if ingestion_config else [],
                    "source_file": ingestion_config.get("source_file", "unknown") if ingestion_config else "unknown",
                    "sample_metadata": sample_metadata
                })
                
            except Exception as e:
                return json.dumps({"error": f"Error getting info for {collection_name}: {str(e)}"})
        
        @tool
        def search_across_collections(query: str, collections: List[str] = None, num_results: int = 50) -> str:
            """
            Search across multiple collections simultaneously.
            
            Args:
                query: Search query
                collections: List of collection names to search (optional, defaults to all)
                num_results: Total number of results to return
            
            Returns:
                JSON string containing aggregated search results
            """
            search_collections = collections if collections else self.collection_names
            all_results = []
            
            for collection_name in search_collections:
                if collection_name not in self.collection_managers:
                    continue
                    
                try:
                    manager = self.collection_managers[collection_name]
                    # Get more results per collection
                    results_per_collection = max(15, num_results // len(search_collections))
                    results = manager.search_similar_chunks(query, results_per_collection)
                    
                    for result in results:
                        result["metadata"]["collection"] = collection_name
                        all_results.append(result)
                        
                except Exception as e:
                    continue
            
            # Sort by score and limit results
            if all_results and "score" in all_results[0]:
                all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
            
            all_results = all_results[:num_results]
            
            # Format for agent
            formatted_results = []
            for result in all_results:
                formatted_results.append({
                    "content": result["content"],
                    "metadata": result.get("metadata", {}),
                    "score": result.get("score", 0.0),
                    "collection": result["metadata"].get("collection", "unknown")
                })
            
            return json.dumps({
                "query": query,
                "collections_searched": search_collections,
                "total_results": len(formatted_results),
                "results": formatted_results
            })
        
        @tool
        def search_web(query: str, num_results: int = 5) -> str:
            """
            Search the web for current information related to the query.
            
            Args:
                query: Search query for web search
                num_results: Number of web results to return (default: 5, max: 10)
            
            Returns:
                JSON string containing web search results with titles, snippets, and URLs
            """
            try:
                import requests
                from urllib.parse import quote
                import time
                from bs4 import BeautifulSoup
                
                # Limit results to reasonable range
                num_results = min(max(1, num_results), 10)
                
                print(f"🌐 Searching web for: '{query}' (requesting {num_results} results)")
                
                # Format query for search
                encoded_query = quote(query)
                results = []
                
                # Approach 1: Try Bing Search (more reliable than DuckDuckGo)
                try:
                    # Use Bing's search suggestions API which is more accessible
                    bing_url = f"https://www.bing.com/search?q={encoded_query}&count={num_results}"
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }
                    
                    response = requests.get(bing_url, headers=headers, timeout=15)
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Extract search results from Bing
                        search_results = soup.find_all('li', class_='b_algo')
                        
                        for result in search_results[:num_results]:
                            try:
                                # Extract title
                                title_elem = result.find('h2')
                                title = title_elem.get_text().strip() if title_elem else "No title"
                                
                                # Extract URL
                                link_elem = title_elem.find('a') if title_elem else None
                                url = link_elem.get('href', '') if link_elem else ''
                                
                                # Extract snippet
                                snippet_elem = result.find('p') or result.find('div', class_='b_caption')
                                snippet = snippet_elem.get_text().strip()[:500] if snippet_elem else "No description available"
                                
                                if title and url:
                                    results.append({
                                        "title": title,
                                        "snippet": snippet,
                                        "url": url,
                                        "source": "Bing Search"
                                    })
                            except Exception as e:
                                continue
                        
                        if results:
                            print(f"   ✅ Bing search found {len(results)} results")
                    else:
                        print(f"   ⚠️ Bing returned status {response.status_code}")
                        
                except Exception as e:
                    print(f"   ⚠️ Bing search failed: {e}")
                
                # Approach 2: Try Google Custom Search (if Bing fails)
                if len(results) < num_results:
                    try:
                        # Use Google's search with careful scraping
                        google_url = f"https://www.google.com/search?q={encoded_query}&num={num_results}"
                        headers = {
                            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                        }
                        
                        response = requests.get(google_url, headers=headers, timeout=15)
                        
                        if response.status_code == 200:
                            soup = BeautifulSoup(response.text, 'html.parser')
                            
                            # Extract search results from Google
                            search_results = soup.find_all('div', class_='g')
                            
                            for result in search_results[:num_results-len(results)]:
                                try:
                                    # Extract title
                                    title_elem = result.find('h3')
                                    title = title_elem.get_text().strip() if title_elem else "No title"
                                    
                                    # Extract URL
                                    link_elem = result.find('a')
                                    url = link_elem.get('href', '') if link_elem else ''
                                    
                                    # Extract snippet
                                    snippet_elem = result.find('span', class_='aCOpRe') or result.find('div', class_='VwiC3b')
                                    snippet = snippet_elem.get_text().strip()[:500] if snippet_elem else "No description available"
                                    
                                    if title and url and url.startswith('http'):
                                        results.append({
                                            "title": title,
                                            "snippet": snippet,
                                            "url": url,
                                            "source": "Google Search"
                                        })
                                except Exception as e:
                                    continue
                            
                            if len(results) > len([r for r in results if r["source"] == "Bing Search"]):
                                print(f"   ✅ Google search found {len(results) - len([r for r in results if r['source'] == 'Bing Search'])} additional results")
                        else:
                            print(f"   ⚠️ Google returned status {response.status_code}")
                            
                    except Exception as e:
                        print(f"   ⚠️ Google search failed: {e}")
                
                # Approach 3: Try Wikipedia search (reliable fallback)
                if len(results) < num_results:
                    try:
                        # Search Wikipedia for general topics
                        wiki_search_url = f"https://en.wikipedia.org/api/rest_v1/page/search/{encoded_query}"
                        wiki_response = requests.get(wiki_search_url, timeout=10, headers={'User-Agent': 'RAG-System/1.0'})
                        
                        if wiki_response.status_code == 200:
                            wiki_data = wiki_response.json()
                            
                            for page in wiki_data.get("pages", [])[:num_results-len(results)]:
                                if page.get("extract") and len(page.get("extract", "")) > 50:
                                    results.append({
                                        "title": f"Wikipedia: {page.get('title', 'Unknown')}",
                                        "snippet": page.get("extract", "")[:500],
                                        "url": f"https://en.wikipedia.org/wiki/{quote(page.get('key', page.get('title', '')))}",
                                        "source": "Wikipedia"
                                    })
                            
                            if len(results) > len([r for r in results if r["source"] in ["Bing Search", "Google Search"]]):
                                print(f"   ✅ Wikipedia found {len([r for r in results if r['source'] == 'Wikipedia'])} results")
                    
                    except Exception as e:
                        print(f"   ⚠️ Wikipedia search failed: {e}")
                
                # Approach 4: Try government and educational sources for Hawaii-related queries
                if len(results) < num_results and any(word in query.lower() for word in ["hawaii", "hawaiian", "honolulu", "education", "budget", "university"]):
                    try:
                        # Search specific Hawaii government sources
                        hawaii_sources = [
                            ("hawaii.gov", "Official State of Hawaii"),
                            ("hawaiistatelegislature.gov", "Hawaii State Legislature"),
                            ("hawaii.edu", "University of Hawaii System"),
                            ("hawaiipublicschools.org", "Hawaii Department of Education")
                        ]
                        
                        for domain, source_name in hawaii_sources[:num_results-len(results)]:
                            try:
                                # Try to get relevant information from these sources
                                search_url = f"https://www.google.com/search?q=site:{domain}+{encoded_query}"
                                response = requests.get(search_url, headers={'User-Agent': 'Mozilla/5.0 (compatible; RAG-System/1.0)'}, timeout=10)
                                
                                if response.status_code == 200:
                                    results.append({
                                        "title": f"{source_name} - {query}",
                                        "snippet": f"Search results for '{query}' from {source_name}. This official source may contain relevant information about Hawaii government, education, or budget matters.",
                                        "url": f"https://{domain}",
                                        "source": f"Hawaii Official Source ({source_name})"
                                    })
                                    break  # Just add one official source
                            except:
                                continue
                                
                    except Exception as e:
                        print(f"   ⚠️ Hawaii sources search failed: {e}")
                
                # If we have results, return them
                if results:
                    final_results = results[:num_results]
                    return json.dumps({
                        "query": query,
                        "source": "Web Search (Multiple Engines)",
                        "results_count": len(final_results),
                        "results": final_results,
                        "search_timestamp": time.time(),
                        "engines_used": list(set([r["source"] for r in final_results]))
                    })
                
                # Approach 5: Provide intelligent suggestions and search guidance
                print(f"   ℹ️ External search engines unavailable, providing search guidance")
                
                # Generate intelligent suggestions based on query content
                search_suggestions = []
                query_lower = query.lower()
                
                if any(word in query_lower for word in ["hawaii", "hawaiian", "honolulu"]):
                    search_suggestions.extend([
                        "hawaii.gov - Official State of Hawaii website",
                        "hawaiistatelegislature.gov - Hawaii State Legislature",
                        "hawaiipublicschools.org - Hawaii Department of Education"
                    ])
                
                if any(word in query_lower for word in ["budget", "funding", "fiscal", "appropriation"]):
                    search_suggestions.extend([
                        "budget.hawaii.gov - Hawaii State Budget",
                        "dbedt.hawaii.gov - Hawaii Department of Business Development",
                        "capitol.hawaii.gov - Hawaii State Capitol"
                    ])
                
                if any(word in query_lower for word in ["education", "school", "university", "student"]):
                    search_suggestions.extend([
                        "hawaiipublicschools.org - Hawaii DOE",
                        "hawaii.edu - University of Hawaii System",
                        "hawaiiteachercorps.org - Hawaii Teacher Corps"
                    ])
                
                # Remove duplicates and limit
                search_suggestions = list(dict.fromkeys(search_suggestions))[:5]
                
                fallback_result = {
                    "query": query,
                    "source": "Web Search Guidance",
                    "results_count": 1,
                    "results": [{
                        "title": "Web Search Guidance",
                        "snippet": f"For current information about '{query}', consider searching these authoritative sources: {', '.join(search_suggestions[:3])}. You can also search Google, Bing, or other search engines with specific terms related to Hawaii government, education policy, or budget information.",
                        "url": "https://www.google.com/search?q=" + encoded_query,
                        "source": "Search Guidance",
                        "suggested_sites": search_suggestions
                    }],
                    "search_timestamp": time.time(),
                    "note": "External search engines temporarily unavailable - search guidance provided"
                }
                
                print(f"   💡 Provided search guidance with {len(search_suggestions)} suggested sources")
                return json.dumps(fallback_result)
                
            except ImportError as e:
                missing_lib = "beautifulsoup4" if "bs4" in str(e) else "requests"
                return json.dumps({
                    "error": f"Web search requires '{missing_lib}' library. Install with: pip install {missing_lib}",
                    "query": query,
                    "installation_note": f"Run 'pip install {missing_lib}' to enable web search functionality"
                })
            except Exception as e:
                print(f"   ❌ Web search error: {e}")
                return json.dumps({
                    "error": f"Web search encountered an error: {str(e)}",
                    "query": query,
                    "fallback_suggestion": f"For current information about '{query}', try searching government websites or recent news sources manually.",
                    "suggested_search_url": f"https://www.google.com/search?q={quote(query)}"
                })
        
        return [search_collection, get_collection_info, search_across_collections, search_web]
    
    def _create_graph(self) -> StateGraph:
        """Create the LangGraph workflow with iterative capabilities"""
        
        # Create workflow
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("fetch_primary_document", self.fetch_primary_document)
        workflow.add_node("analyze_query", self.analyze_query)
        workflow.add_node("decompose_query", self.decompose_query)
        workflow.add_node("generate_hypothetical_answers", self.generate_hypothetical_answers)
        workflow.add_node("parallel_subquestion_search", self.parallel_subquestion_search)
        workflow.add_node("answer_subquestions", self.answer_subquestions)
        workflow.add_node("synthesize_final_answer", self.synthesize_final_answer)
        workflow.add_node("search_documents", self.search_documents)
        workflow.add_node("evaluate_results", self.evaluate_results)
        workflow.add_node("refine_search", self.refine_search)
        workflow.add_node("generate_answer", self.generate_answer)
        
        # Define conditional routing functions
        def should_refine(state: AgentState) -> str:
            """Determine if we should refine search or generate answer"""
            if state.get("needs_refinement", False):
                return "refine_search"
            else:
                return "generate_answer"
        
        def should_use_subquestions(state: AgentState) -> str:
            """Determine if we should use subquestion decomposition"""
            reasoning = state.get("reasoning", {})
            query_type = reasoning.get("query_type", "informational")
            
            # Use subquestion decomposition for complex queries
            complex_types = ["fiscal_note", "budget_analysis", "policy_analysis"]
            if query_type in complex_types or len(state["query"].split()) > 10:
                return "decompose_query"
            else:
                return "search_documents"
        
        # Add edges with conditional routing
        workflow.set_entry_point("fetch_primary_document")
        workflow.add_edge("fetch_primary_document", "analyze_query")
        workflow.add_conditional_edges("analyze_query", should_use_subquestions)
        
        # Subquestion decomposition path
        workflow.add_edge("decompose_query", "generate_hypothetical_answers")
        workflow.add_edge("generate_hypothetical_answers", "parallel_subquestion_search")
        workflow.add_edge("parallel_subquestion_search", "answer_subquestions")
        workflow.add_edge("answer_subquestions", "synthesize_final_answer")
        
        # Traditional path
        workflow.add_edge("search_documents", "evaluate_results")
        workflow.add_conditional_edges("evaluate_results", should_refine)
        workflow.add_edge("refine_search", "evaluate_results")
        workflow.add_edge("generate_answer", END)
        workflow.add_edge("synthesize_final_answer", END)
        
        return workflow.compile()
    
    def fetch_primary_document(self, state: AgentState) -> AgentState:
        """
        Fetch the primary document text if a primary collection is specified.
        This allows the agent to focus on the uploaded PDF content.
        """
        primary_collection = state.get("primary_collection")
        
        if primary_collection:
            logging.info(f"Fetching primary document text from collection: {primary_collection}")
            primary_text = self._fetch_primary_document_text(primary_collection)
            
            if primary_text:
                state["primary_document_text"] = primary_text
                logging.info(f"Successfully loaded primary document: {len(primary_text)} characters")
            else:
                logging.warning(f"Could not load primary document from collection: {primary_collection}")
                state["primary_document_text"] = None
        else:
            state["primary_document_text"] = None
            logging.debug("No primary collection specified")
        
        return state
    
    def decompose_query(self, state: AgentState) -> AgentState:
        """Decompose the user query into 5 strategic subquestions for enhanced reasoning"""
        
        query = state["query"]
        reasoning = state["reasoning"]
        query_type = reasoning.get("query_type", "informational")
        primary_document_text = state.get("primary_document_text")
        
        print(f"🧩 Decomposing query into subquestions for enhanced reasoning")
        
        # Build context section with primary document if available
        context_section = "CONTEXT: This is for a Hawaii government/education RAG system with budget, fiscal, and policy documents."
        
        if primary_document_text:
            # Intelligently truncate primary document for prompt to fit context limits
            max_doc_chars = 15000  # Leave room for other prompt content and response
            if len(primary_document_text) > max_doc_chars:
                # Take first 10k chars and last 5k chars to preserve beginning and end
                truncated_text = primary_document_text[:10000] + "\n\n[... MIDDLE CONTENT TRUNCATED FOR CONTEXT LIMITS ...]\n\n" + primary_document_text[-5000:]
                print(f"📄 Truncated primary document: {len(primary_document_text)} → {len(truncated_text)} characters")
            else:
                truncated_text = primary_document_text
                print(f"📄 Including full primary document context ({len(primary_document_text)} characters)")
            
            context_section += f"\n\nPRIMARY DOCUMENT CONTENT (focus your analysis on this document):\n{truncated_text}"
        
        decomposition_prompt = f"""You are an expert query analyst. Break down this complex query into exactly 5 strategic subquestions that will help gather comprehensive information to answer the main question.

MAIN QUERY: "{query}"
QUERY TYPE: {query_type}
{context_section}

Create 5 subquestions that:
1. Cover different aspects of the main query
2. Are specific enough to retrieve relevant documents
3. Build upon each other logically
4. Include both factual and analytical components
5. Consider current context and historical background

For fiscal/budget queries, include subquestions about:
- Current budget allocations
- Historical trends
- Policy implications
- Implementation details
- Stakeholder impacts

Return your response as a JSON array with this structure:
[
  {{
    "id": 1,
    "question": "What is the current budget allocation for [specific area]?",
    "purpose": "Establish baseline financial information",
    "search_focus": "budget_documents"
  }},
  ...
]

Make each subquestion clear, specific, and designed to retrieve different types of relevant information."""

        try:
            response = self.llm.invoke([HumanMessage(content=decomposition_prompt)])
            content = response.content.strip()
            
            # Clean and parse JSON
            if content.startswith('```json'):
                content = content[7:]
            if content.endswith('```'):
                content = content[:-3]
            content = content.strip()
            
            import json
            subquestions = json.loads(content)
            
            # Validate and ensure we have exactly 5 subquestions
            if not isinstance(subquestions, list) or len(subquestions) != 5:
                raise ValueError("Must have exactly 5 subquestions")
            
            # Add metadata to each subquestion
            for i, sq in enumerate(subquestions):
                sq["id"] = i + 1
                sq["status"] = "pending"
                sq["search_results"] = []
                sq["answer"] = ""
            
            state["subquestions"] = subquestions
            state["parallel_processing_enabled"] = True
            
            print(f"   ✅ Created {len(subquestions)} subquestions:")
            for sq in subquestions:
                print(f"      {sq['id']}. {sq['question']}")
            
            state["messages"].append(AIMessage(content=f"Query decomposed into {len(subquestions)} strategic subquestions"))
            
        except Exception as e:
            print(f"   ❌ Error decomposing query: {e}")
            # Fallback to simple decomposition
            fallback_subquestions = [
                {
                    "id": 1,
                    "question": f"What is the main topic and scope of {query}?",
                    "purpose": "Establish context and scope",
                    "search_focus": "general",
                    "status": "pending",
                    "search_results": [],
                    "answer": ""
                },
                {
                    "id": 2,
                    "question": f"What are the current policies or regulations related to {query}?",
                    "purpose": "Identify relevant policies",
                    "search_focus": "policy_documents",
                    "status": "pending",
                    "search_results": [],
                    "answer": ""
                },
                {
                    "id": 3,
                    "question": f"What budget or financial information is available for {query}?",
                    "purpose": "Gather financial context",
                    "search_focus": "budget_documents",
                    "status": "pending",
                    "search_results": [],
                    "answer": ""
                },
                {
                    "id": 4,
                    "question": f"What are the implementation details or operational aspects of {query}?",
                    "purpose": "Understand implementation",
                    "search_focus": "operational_documents",
                    "status": "pending",
                    "search_results": [],
                    "answer": ""
                },
                {
                    "id": 5,
                    "question": f"What are the impacts or outcomes related to {query}?",
                    "purpose": "Assess impacts and outcomes",
                    "search_focus": "impact_analysis",
                    "status": "pending",
                    "search_results": [],
                    "answer": ""
                }
            ]
            
            state["subquestions"] = fallback_subquestions
            state["parallel_processing_enabled"] = True
            
            print(f"   ⚠️ Used fallback decomposition with {len(fallback_subquestions)} subquestions")
            state["messages"].append(AIMessage(content=f"Query decomposed using fallback method into {len(fallback_subquestions)} subquestions"))
        
        return state
    
    def generate_hypothetical_answers(self, state: AgentState) -> AgentState:
        """Generate hypothetical answers for each subquestion to guide document retrieval"""
        
        subquestions = state["subquestions"]
        query = state["query"]
        
        print(f"🤔 Generating hypothetical answers for {len(subquestions)} subquestions")
        
        hypothetical_answers = []
        
        for sq in subquestions:
            hypothesis_prompt = f"""You are an expert analyst. Generate a detailed hypothetical answer for this subquestion that will help guide document retrieval.

MAIN QUERY: "{query}"
{state['primary_document_text'] and f"PRIMARY DOCUMENT: {state['primary_document_text']}" or ""}
SUBQUESTION: "{sq['question']}"
PURPOSE: {sq['purpose']}
SEARCH FOCUS: {sq['search_focus']}

Generate a comprehensive hypothetical answer that:
1. Addresses the specific subquestion thoroughly
2. Includes relevant keywords and terminology for document search
3. Mentions specific types of documents or data sources that would contain this information
4. Considers Hawaii government/education context
5. Includes potential numerical data, policy names, or specific details

This hypothetical answer will be used to:
- Create better search queries for vector similarity search
- Generate keyword searches for hybrid retrieval
- Guide the retrieval of the most relevant documents

Make the hypothetical answer a single sentence."""

            try:
                response = self.llm.invoke([HumanMessage(content=hypothesis_prompt)])
                hypothetical_answer = response.content.strip()
                
                # Extract keywords from hypothetical answer for search
                keyword_prompt = hypothetical_answer
                
                keyword_response = self.llm.invoke([HumanMessage(content=keyword_prompt)])
                search_keywords = [k.strip() for k in keyword_response.content.split(',')]
                
                hypothetical_data = {
                    "subquestion_id": sq["id"],
                    "question": sq["question"],
                    "hypothetical_answer": hypothetical_answer,
                    "search_keywords": search_keywords,
                    "status": "generated"
                }
                
                hypothetical_answers.append(hypothetical_data)
                
                print(f"   ✅ Generated hypothesis for Q{sq['id']}: {len(hypothetical_answer)} chars")
                
            except Exception as e:
                print(f"   ❌ Error generating hypothesis for Q{sq['id']}: {e}")
                # Fallback hypothesis
                fallback_hypothesis = {
                    "subquestion_id": sq["id"],
                    "question": sq["question"],
                    "hypothetical_answer": f"This question relates to {sq['search_focus']} and would typically be answered using Hawaii government documents, budget reports, or policy documents that contain relevant information about {sq['question'].lower()}.",
                    "search_keywords": [sq['search_focus'], "Hawaii", "government", "policy", "budget"],
                    "status": "fallback"
                }
                hypothetical_answers.append(fallback_hypothesis)
        
        state["hypothetical_answers"] = hypothetical_answers
        state["messages"].append(AIMessage(content=f"Generated hypothetical answers for {len(hypothetical_answers)} subquestions"))
        
        return state
    
    def parallel_subquestion_search(self, state: AgentState) -> AgentState:
        """Perform parallel hybrid search for each subquestion using hypothetical answers"""
        
        hypothetical_answers = state["hypothetical_answers"]
        tools = self.tools
        
        print(f"🔍 Performing parallel hybrid search for {len(hypothetical_answers)} subquestions")
        
        import concurrent.futures
        
        def search_for_subquestion(hyp_answer):
            """Perform hybrid search for a single subquestion"""
            subq_id = hyp_answer["subquestion_id"]
            question = hyp_answer["question"]
            keywords = hyp_answer["search_keywords"]
            hypothesis = hyp_answer["hypothetical_answer"]
            
            search_results = []
            
            try:
                # Get available collections from self.collection_names
                available_collections = getattr(self, 'collection_names', ['budget', 'text', 'fiscal'])
                
                # 1. Vector search using hypothetical answer across collections
                vector_query = f"{question} {hypothesis}"
                for collection in available_collections:
                    try:
                        results = self.collection_managers[collection].search_similar_chunks(vector_query, 50)
                        for result in results:
                            result["collection"] = collection
                            result["subquestion_id"] = subq_id
                            search_results.append(result)
                    except Exception as e:
                        print(f"      ⚠️ Search failed for {collection}: {e}")
                        try:
                            keyword_results = tools[0].invoke({
                                "collection_name": collection,
                                "query": keyword,
                                "num_results": 10
                            })
                            if isinstance(keyword_results, str):
                                keyword_data = json.loads(keyword_results)
                                if "results" in keyword_data and keyword_data["results"]:
                                    for result in keyword_data["results"]:  # Increased from 1 to 3 per keyword per collection
                                        result["search_type"] = "keyword"
                                        result["keyword_used"] = keyword
                                        result["subquestion_id"] = subq_id
                                        result["collection_searched"] = collection
                                        search_results.append(result)
                                    print(f"      🔑 Keyword '{keyword}' in {collection}: {len(keyword_data['results'])} results")
                        except Exception as e:
                            print(f"      ⚠️ Keyword search failed for '{keyword}' in {collection}: {e}")
                
                # 3. Cross-collection search for comprehensive coverage
                try:
                    cross_results = tools[2].invoke({
                        "query": question,
                        "collections": available_collections,
                        "num_results": 0
                    })
                    if isinstance(cross_results, str):
                        cross_data = json.loads(cross_results)
                        if "results" in cross_data and cross_data["results"]:
                            for result in cross_data["results"]:
                                result["search_type"] = "cross_collection"
                                result["subquestion_id"] = subq_id
                                search_results.append(result)
                            print(f"      🌐 Cross-collection search: {len(cross_data['results'])} results")
                except Exception as e:
                    print(f"      ⚠️ Cross-collection search failed: {e}")
                
                # Remove duplicates based on content similarity
                unique_results = []
                seen_content = set()
                
                for result in search_results:
                    content_key = result.get("content", "") 
                    if content_key not in seen_content:
                        seen_content.add(content_key)
                        unique_results.append(result)
                
                # Sort by relevance score if available
                unique_results.sort(key=lambda x: x.get("score", 0), reverse=True)
                
                print(f"      ✅ Q{subq_id}: Found {len(unique_results)} unique results")
                
                return {
                    "subquestion_id": subq_id,
                    "question": question,
                    "search_results": unique_results,  
                    "search_summary": {
                        "total_results": len(unique_results),
                        "vector_results": len([r for r in unique_results if r.get("search_type") == "vector"]),
                        "keyword_results": len([r for r in unique_results if r.get("search_type") == "keyword"]),
                        "cross_collection_results": len([r for r in unique_results if r.get("search_type") == "cross_collection"])
                    }
                }
                
            except Exception as e:
                print(f"      ❌ Search failed for Q{subq_id}: {e}")
                return {
                    "subquestion_id": subq_id,
                    "question": question,
                    "search_results": [],
                    "error": str(e)
                }
        
        # Perform parallel searches
        subquestion_results = []
        
        if state.get("parallel_processing_enabled", True):
            # Use ThreadPoolExecutor for parallel processing
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                future_to_subq = {executor.submit(search_for_subquestion, hyp): hyp for hyp in hypothetical_answers}
                
                for future in concurrent.futures.as_completed(future_to_subq):
                    try:
                        result = future.result(timeout=30)  # 30 second timeout per search
                        subquestion_results.append(result)
                    except Exception as e:
                        hyp = future_to_subq[future]
                        print(f"      ❌ Parallel search failed for Q{hyp['subquestion_id']}: {e}")
                        subquestion_results.append({
                            "subquestion_id": hyp["subquestion_id"],
                            "question": hyp["question"],
                            "search_results": [],
                            "error": str(e)
                        })
        else:
            # Sequential processing fallback
            for hyp in hypothetical_answers:
                result = search_for_subquestion(hyp)
                subquestion_results.append(result)
        
        # Sort results by subquestion ID
        subquestion_results.sort(key=lambda x: x["subquestion_id"])
        
        state["subquestion_results"] = subquestion_results
        
        total_docs_found = sum(len(sr.get("search_results", [])) for sr in subquestion_results)
        print(f"   ✅ Parallel search completed: {total_docs_found} total documents found across {len(subquestion_results)} subquestions")
        
        state["messages"].append(AIMessage(content=f"Completed parallel hybrid search for {len(subquestion_results)} subquestions, found {total_docs_found} relevant documents"))
        
        return state
    
    def analyze_query(self, state: AgentState) -> AgentState:
        """Analyze the user query to determine search strategy"""
        
        # Get collection information
        collection_info = {}
        for collection_name in self.collection_names:
            try:
                # Get ingestion config
                ingestion_config = None
                for config_item in self.config.get("ingestion_configs", []):
                    if config_item.get("collection_name") == collection_name:
                        ingestion_config = config_item
                        break
                
                collection_info[collection_name] = {
                    "embedded_fields": ingestion_config.get("contents_to_embed", []) if ingestion_config else [],
                    "source_file": ingestion_config.get("source_file", "unknown") if ingestion_config else "unknown",
                    "description": ingestion_config.get("description", "No description available") if ingestion_config else "No description available"
                }
            except Exception as e:
                collection_info[collection_name] = {"error": str(e)}
        
        analysis_prompt = f"""Analyze this user query and create a search strategy.

AVAILABLE COLLECTIONS WITH DESCRIPTIONS:
{json.dumps(collection_info, indent=2)}

USER QUERY: "{state['query']}"

Based on the query and the detailed descriptions of available collections, determine:

1. INTENT: What is the user trying to accomplish?
2. QUERY_TYPE: Classify as one of:
   - "budget_analysis": Questions about budget items, appropriations, spending
   - "fiscal_note": Creating or understanding fiscal notes
   - "text_search": General text-based document search
   - "comparative_analysis": Comparing different items or programs
   - "informational": General information requests

3. TARGET_COLLECTIONS: Which collections are most relevant based on their descriptions and content? Choose from: {', '.join(self.collection_names)}
4. SEARCH_STRATEGY: How should we approach searching?
5. SEARCH_TERMS: 3-5 specific terms or phrases to search for
6. OUTPUT_FORMAT: What type of response would be most helpful?

IMPORTANT: Use the collection descriptions to understand what type of content each collection contains. Select collections that best match the user's query intent and information needs.

CRITICAL: You MUST respond with ONLY valid JSON. Do not include any other text, explanations, or markdown formatting. 
Your response must start with {{ and end with }}.

{{
    "intent": "description of user intent",
    "query_type": "one of the types above",
    "target_collections": ["collection1", "collection2"],
    "search_strategy": "explanation of approach",
    "search_terms": ["term1", "term2", "term3"],
    "output_format": "informational",
    "confidence": "high"
}}"""

        # Try multiple times with different approaches
        for attempt in range(3):
            try:
                print(f"🧠 Query Analysis attempt {attempt + 1}/3")
                
                if attempt == 0:
                    # First attempt: normal prompt
                    messages = [
                        SystemMessage(content="You are a query analyzer. Respond ONLY with valid JSON. No explanations, no markdown, just JSON."),
                        HumanMessage(content=analysis_prompt)
                    ]
                elif attempt == 1:
                    # Second attempt: more explicit
                    messages = [
                        SystemMessage(content="Respond with valid JSON only. Start with { and end with }."),
                        HumanMessage(content=f"Analyze query: '{state['query']}'. Return JSON with intent, query_type, target_collections, search_strategy, search_terms, output_format, confidence.")
                    ]
                else:
                    # Third attempt: minimal
                    messages = [
                        SystemMessage(content="JSON only response required."),
                        HumanMessage(content=f"Query: '{state['query']}' - Return: {{\"intent\":\"search intent\",\"query_type\":\"informational\",\"target_collections\":{json.dumps(self.collection_names)},\"search_strategy\":\"broad search\",\"search_terms\":[\"{state['query']}\"],\"output_format\":\"informational\",\"confidence\":\"medium\"}}")
                    ]
                
                response = self.llm.invoke(messages)
                content = response.content.strip()
                                
                # Clean up the response
                if content.startswith('```json'):
                    content = content[7:]
                if content.endswith('```'):
                    content = content[:-3]
                
                content = content.strip()
                
                # Try to find JSON in the response
                if not content.startswith('{'):
                    # Look for JSON within the text
                    import re
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        content = json_match.group(0)
                    else:
                        raise ValueError("No JSON found in response")
                
                # Parse JSON
                reasoning_result = json.loads(content)
                
                # Validate required fields
                required_fields = ["intent", "query_type", "target_collections", "search_strategy", "search_terms", "output_format", "confidence"]
                for field in required_fields:
                    if field not in reasoning_result:
                        reasoning_result[field] = "unknown" if field != "target_collections" else self.collection_names
                
                # Validate collections
                valid_collections = [c for c in reasoning_result.get("target_collections", []) 
                                   if c in self.collection_names]
                if not valid_collections:
                    valid_collections = self.collection_names
                
                reasoning_result["target_collections"] = valid_collections
                
                print(f"✅ Query Analysis successful:")
                print(f"   Intent: {reasoning_result.get('intent', 'Unknown')}")
                print(f"   Type: {reasoning_result.get('query_type', 'Unknown')}")
                print(f"   Collections: {valid_collections}")
                print(f"   Strategy: {reasoning_result.get('search_strategy', 'Unknown')}")
                
                state["reasoning"] = reasoning_result
                state["messages"].append(AIMessage(content=f"Analysis complete: {reasoning_result['intent']}"))
                
                return state
                
            except json.JSONDecodeError as e:
                print(f"   ❌ JSON parsing error (attempt {attempt + 1}): {e}")
                if attempt == 2:  # Last attempt
                    break
                continue
            except Exception as e:
                print(f"   ❌ Error in analysis (attempt {attempt + 1}): {e}")
                if attempt == 2:  # Last attempt
                    break
                continue
        
        # All attempts failed - use generalized fallback
        print(f"❌ All analysis attempts failed, using generalized fallback strategy")

        # Generalized fallback - search all collections with basic strategy
        state["reasoning"] = {
            "intent": f"search for information about: {state['query']}",
            "query_type": "informational",
            "target_collections": self.collection_names,  # Search all collections when uncertain
            "search_strategy": "comprehensive search across all available collections",
            "search_terms": [state["query"]] + state["query"].split()[:3],
            "output_format": "informational",
            "confidence": "low"
        }
        state["messages"].append(AIMessage(content="Analysis failed, using comprehensive search across all collections"))
        
        return state
    
    def search_documents(self, state: AgentState) -> AgentState:
        """Use tools to search for relevant documents"""
        
        reasoning = state["reasoning"]
        target_collections = reasoning.get("target_collections", self.collection_names)
        search_terms = reasoning.get("search_terms", [state["query"]])
        
        # Create tool-using LLM
        llm_with_tools = self.llm.bind_tools(self.tools)
        
        search_prompt = f"""Use the available tools to search for information relevant to this query.

QUERY: "{state['query']}"
ANALYSIS: {json.dumps(reasoning, indent=2)}

TARGET COLLECTIONS: {target_collections}
SEARCH TERMS: {search_terms}

SEARCH STRATEGY - Use tools strategically and COMPREHENSIVELY:

1. **FIRST**: Use search_across_collections with num_results=200 to get a broad overview across all relevant collections
2. **THEN**: For each target collection, use search_collection with num_results=150-200 for focused searches
3. **OPTIONAL**: Use get_collection_info if you need to understand collection structure
4. **WEB SEARCH**: Use search_web when you need:
   - Current/recent information not in documents
   - Verification of facts or figures
   - Background context on current events
   - Information about recent policy changes or implementations
   - Comparative data from other jurisdictions

CRITICAL INSTRUCTIONS:
- Always use HIGH num_results values (150-200) for local document searches to gather comprehensive context
- Search thoroughly in local documents first - the user needs detailed information from available data
- Use multiple search terms if helpful for local searches
- Use web search strategically for current information, verification, or additional context
- Don't limit yourself to small result sets for local searches - more data = better analysis

EXAMPLE TOOL CALLS:
- search_across_collections(query="{state['query']}", num_results=200)
- search_collection(collection_name="budget", query="specific term", num_results=200)
- search_collection(collection_name="fiscal", query="another term", num_results=150)
- search_web(query="current Hawaii education policy 2024", num_results=3)

WEB SEARCH GUIDELINES:
- Use for current events, recent policy changes, or verification
- Keep web queries focused and specific
- Limit to 5-10 web results to avoid information overload
- Use web search to supplement, not replace, local document searches
- Examples of good web search queries:
  * "Hawaii education budget 2024 recent changes"
  * "current Hawaii fiscal policy updates"
  * "Hawaii state budget implementation 2024"

Focus on finding ALL relevant documents that will help answer the user's question.
Be thorough and comprehensive in your searching."""

        try:
            # Let the LLM decide which tools to use
            messages = [
                SystemMessage(content="You are a research assistant. Use the available tools to search for relevant information. Be thorough in your searching."),
                HumanMessage(content=search_prompt)
            ]
            
            response = llm_with_tools.invoke(messages)
            
            # Execute any tool calls
            search_results = []
            collections_searched = []
            search_terms_used = []
            web_results = []
            
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    
                    print(f"🔍 Executing tool: {tool_name} with args: {tool_args}")
                    
                    # Find and execute the tool
                    for tool in self.tools:
                        if tool.name == tool_name:
                            try:
                                result = tool.invoke(tool_args)
                                tool_data = json.loads(result)
                                
                                if tool_name == "search_web":
                                    # Handle web search results separately
                                    if "results" in tool_data and tool_data["results"]:
                                        web_results.extend(tool_data["results"])
                                        print(f"   ✅ Web search found {len(tool_data.get('results', []))} results")
                                    elif "error" in tool_data:
                                        print(f"   ⚠️ Web search error: {tool_data['error']}")
                                else:
                                    # Handle collection search results
                                    if "results" in tool_data:
                                        search_results.extend(tool_data["results"])
                                    
                                    if "collection" in tool_data:
                                        collections_searched.append(tool_data["collection"])
                                    
                                    if "collections_searched" in tool_data:
                                        collections_searched.extend(tool_data["collections_searched"])
                                    
                                    if "query" in tool_data:
                                        search_terms_used.append(tool_data["query"])
                                    
                                    print(f"   ✅ Tool {tool_name} found {len(tool_data.get('results', []))} results")
                                
                            except Exception as e:
                                print(f"   ❌ Error executing tool {tool_name}: {e}")
                            break
            
            # Remove duplicates and sort by score
            seen_ids = set()
            unique_results = []
            
            for result in search_results:
                result_id = result.get("metadata", {}).get("id", "")
                content_hash = hash(result.get("content", ""))
                unique_key = f"{result_id}_{content_hash}"
                
                if unique_key not in seen_ids:
                    seen_ids.add(unique_key)
                    unique_results.append(result)
            
            # Sort by score
            if unique_results and "score" in unique_results:
                unique_results.sort(key=lambda x: x.get("score", 0), reverse=True)
            
            # Fallback search if we don't have enough results
            min_expected_results = 30
            if len(unique_results) < min_expected_results:
                print(f"⚠️  Only {len(unique_results)} results found, performing fallback comprehensive search...")
                
                # Direct search across all target collections
                fallback_results = []
                for collection_name in target_collections:
                    if collection_name in self.collection_managers:
                        try:
                            manager = self.collection_managers[collection_name]
                            # Use the main query and search terms
                            for search_term in [state["query"]] + search_terms[:3]:
                                results = manager.search_similar_chunks(search_term, 50)
                                for result in results:
                                    result["metadata"]["collection"] = collection_name
                                    fallback_results.append(result)
                        except Exception as e:
                            print(f"   ❌ Fallback search error for {collection_name}: {e}")
                            continue
                
                # Merge fallback results with existing ones
                all_combined_results = unique_results + fallback_results
                
                # Remove duplicates again
                seen_ids = set()
                final_unique_results = []
                
                for result in all_combined_results:
                    result_id = result.get("metadata", {}).get("id", "")
                    content_hash = hash(result.get("content", ""))
                    unique_key = f"{result_id}_{content_hash}"
                    
                    if unique_key not in seen_ids:
                        seen_ids.add(unique_key)
                        final_unique_results.append(result)
                
                # Sort final results
                if final_unique_results and "score" in final_unique_results[0]:
                    final_unique_results.sort(key=lambda x: x.get("score", 0), reverse=True)
                
                unique_results = final_unique_results
                print(f"   ✅ Fallback search added {len(unique_results) - len(search_results)} more results")
            
            state["search_results"] = unique_results
            state["collections_searched"] = list(set(collections_searched))
            state["search_terms_used"] = list(set(search_terms_used))
            state["web_results"] = web_results # Add web results to state
            
            print(f"📊 Search completed: {len(unique_results)} unique results from {len(set(collections_searched))} collections")
            
            state["messages"].append(AIMessage(content=f"Search completed: Found {len(unique_results)} relevant documents"))
            
        except Exception as e:
            print(f"❌ Error in document search: {e}")
            state["search_results"] = []
            state["collections_searched"] = []
            state["search_terms_used"] = []
            state["web_results"] = [] # Ensure web_results is empty on error
            state["messages"].append(AIMessage(content=f"Search failed: {str(e)}"))
        
        return state
    
    def generate_answer(self, state: AgentState) -> AgentState:
        """Generate the final answer based on search results"""
        
        reasoning = state["reasoning"]
        search_results = state["search_results"]
        web_results = state.get("web_results", [])
        query_type = reasoning.get("query_type", "informational")
        output_format = reasoning.get("output_format", "informational")
        
        # Build context from search results
        context_parts = []
        sources = []
        
        # Categorize documents by collection
        budget_items = []
        fiscal_guidance = []
        text_documents = []
        
        print(f"📝 Building context from {len(search_results)} collection results and {len(web_results)} web results")
        
        for i, result in enumerate(search_results):  
            collection = result.get("collection", "unknown")
            content = result.get("content", "")
            metadata = result.get("metadata", {})
            
            if collection == "budget":
                budget_items.append(result)
            elif collection == "fiscal":
                fiscal_guidance.append(result)
            elif collection == "text":
                text_documents.append(result)
            
            # Add to context with better source attribution
            source_id = result.get("metadata", {}).get("source_file", "unknown")
            doc_title = result.get("metadata", {}).get("title", "")
            
            # Create a more descriptive source label
            if doc_title:
                source_label = f"[{collection.upper()}: {doc_title}]"
            elif source_id and source_id != "unknown":
                source_label = f"[{collection.upper()}: {source_id}]"
            else:
                source_label = f"[{collection.upper()} Document]"
            
            # For budget items, include comprehensive metadata in context
            if collection == "budget":
                # Build detailed budget item representation
                budget_context = f"{source_label}\nCONTENT: {content}\n"
                
                # Add key financial and program information
                budget_context += "BUDGET ITEM DETAILS:\n"
                
                # Program information
                program = metadata.get("program", "N/A")
                program_id = metadata.get("program_id", "N/A") 
                agency = metadata.get("expending_agency_expanded", metadata.get("expending_agency", "N/A"))
                budget_context += f"  Program: {program}\n"
                budget_context += f"  Program ID: {program_id}\n"
                budget_context += f"  Agency: {agency}\n"
                
                # Financial information
                fy_2025_amount = metadata.get("fiscal_year_2025_2026_amount", "N/A")
                fy_2026_amount = metadata.get("fiscal_year_2026_2027_amount", "N/A")
                if fy_2025_amount != "N/A" and isinstance(fy_2025_amount, (int, float)):
                    budget_context += f"  FY 2025-2026 Amount: ${fy_2025_amount:,}\n"
                else:
                    budget_context += f"  FY 2025-2026 Amount: {fy_2025_amount}\n"
                    
                if fy_2026_amount != "N/A" and isinstance(fy_2026_amount, (int, float)):
                    budget_context += f"  FY 2026-2027 Amount: ${fy_2026_amount:,}\n"
                else:
                    budget_context += f"  FY 2026-2027 Amount: {fy_2026_amount}\n"
                
                # Appropriation details
                approp_2025 = metadata.get("appropriations_mof_2025_2026_expanded", metadata.get("appropriations_mof_2025_2026", "N/A"))
                approp_2026 = metadata.get("appropriations_mof_2026_2027_expanded", metadata.get("appropriations_mof_2026_2027", "N/A"))
                budget_context += f"  Appropriation Type 2025-2026: {approp_2025}\n"
                budget_context += f"  Appropriation Type 2026-2027: {approp_2026}\n"
                
                # Document details
                document_name = metadata.get("document_name", "N/A")
                page_number = metadata.get("page_number", "N/A")
                budget_context += f"  Document: {document_name}\n"
                budget_context += f"  Page: {page_number}\n"
                
                context_parts.append(budget_context)
            else:
                # For non-budget items, use simpler format but still include relevant metadata
                item_context = f"{source_label}\nCONTENT: {content}\n"
                
                # Add any relevant metadata for non-budget items
                if metadata:
                    item_context += "METADATA:\n"
                    # Include key metadata fields but exclude system fields
                    exclude_fields = {'id', 'collection', 'embedded_fields', 'search_term', 'reasoning_intent'}
                    for key, value in metadata.items():
                        if key not in exclude_fields and value not in [None, "", "unknown"]:
                            item_context += f"  {key}: {value}\n"
                
                context_parts.append(item_context)
            
            # Prepare source for response
            sources.append({
                "content": content,
                "metadata": {k: v for k, v in result.get("metadata", {}).items() 
                           if k not in ['search_term', 'reasoning_intent']},
                "score": result.get("score"),
                "collection": collection
            })
        
        # Add web search results to context
        for i, result in enumerate(web_results): # Limit web results to 10 for context
            source_label = f"[WEB: {result.get('title', 'Unknown Source')}]"
            item_context = f"{source_label}\nCONTENT: {result.get('snippet', result.get('content', ''))}\n"
            item_context += f"URL: {result.get('url', 'N/A')}\n"
            context_parts.append(item_context)
            sources.append({
                "content": result.get('snippet', result.get('content', '')),
                "metadata": {"source": "Web", "url": result.get('url', 'N/A')},
                "score": 1.0, # Web results are typically high relevance
                "collection": "web"
            })
        
        context = "\n\n".join(context_parts)
        
        # Choose appropriate prompt based on query type
        if query_type == "fiscal_note" and output_format == "template" and budget_items:
            answer_prompt = f"""You are a fiscal analyst creating comprehensive fiscal notes from budget data following standard fiscal note format and requirements.

USER QUERY: "{state['query']}"
QUERY TYPE: {query_type}
COLLECTIONS SEARCHED: {state['collections_searched']}
SEARCH TERMS USED: {state['search_terms_used']}
WEB RESULTS FOUND: {len(web_results)} current information sources

DOCUMENT ANALYSIS:
- Budget Items: {len(budget_items)} documents
- Fiscal Guidance: {len(fiscal_guidance)} documents  
- Text Documents: {len(text_documents)} documents
- Web Sources: {len(web_results)} current information sources

RETRIEVED CONTEXT WITH DETAILED BUDGET INFORMATION:
{context}

IMPORTANT: The budget items above include complete metadata with specific dollar amounts, program details, agencies, and appropriation types. Use this detailed financial information to create a comprehensive fiscal note. Web sources provide current context and verification information.

Create a comprehensive fiscal note using the available budget data with the following required sections and format:

## FISCAL NOTE STRUCTURE

### 1. BILL STATUS
Denote the last committee or floor action for which the fiscal note was prepared or updated. Indicate if this is a preliminary fiscal note, fiscal note on demand, or prepared for specific amendments (SEBEC, interim committee, JBC bill).

### 2. SUMMARY OF FISCAL IMPACT
Include checked boxes indicating the type of fiscal impact:
☐ State Revenue Impact
☐ State Expenditure Impact  
☐ Local Government Impact
☐ School District Impact
☐ Statutory Public Entity Impact
☐ No Fiscal Impact

Provide narrative text describing the bill, its impacts to state and local governments, and whether impacts are one-time or ongoing.

### 3. APPROPRIATION SUMMARY
Indicate the appropriation that the bill requires. Do not include centrally appropriated costs. State "No appropriation is required" if none is needed.

### 4. FISCAL NOTE STATUS
Indicate what version of the bill the fiscal note was prepared for and any special circumstances.

### 5. STATE FISCAL IMPACT TABLE
Create a table covering generally two fiscal years (may include more as applicable). Include:

**Revenue/Expenditures/Transfers:**
- Cash Funds and/or General Fund as applicable
- Specific fund names for Capital Construction Fund, Highway Users Tax Fund, and State Education Fund when relevant

**Centrally Appropriated:**
- Employee insurance and supplemental retirement payments
- Indirect costs and leased space (department-dependent)
- Note: These costs are appropriated through annual budget process, not included in bill's appropriation requirement

**TABOR Refund:**
- During TABOR refund periods, indicate how revenue affects projected TABOR refund obligation

**Total FTE:**
- New position changes required by the bill

### 6. DETAILED ANALYSIS SECTIONS

**Summary of Legislation:**
Provide comprehensive overview of the proposed legislation and its key provisions.

**Background:**
Include relevant context and historical information.

**Assumptions:**
Detail key assumptions used in fiscal impact calculations.

**Comparable Crime:** (if applicable)
Analysis of similar legislation or precedents.

**State Revenue:**
Detailed analysis of revenue impacts with specific dollar amounts and timing.

**State Transfers:**
Analysis of any fund transfers between state accounts.

**State Expenditures:**
Comprehensive breakdown of expenditure impacts by department and program.

**Local Government Impact:**
Analysis of fiscal impacts on counties, municipalities, and other local entities.

**School District Impact:**
Specific analysis of impacts on K-12 education funding and operations.

**Statutory Public Entity Impact:**
Analysis of impacts on special districts and statutory entities.

**Technical Note:**
Any technical considerations or methodological notes.

**State Appropriations:**
Detailed breakdown of required appropriations by fund source and department.

**Departmental Differences:**
Note any differences in estimates between departments or agencies.

**State and Local Government Contacts:**
List relevant agency contacts and their roles.

## FORMATTING REQUIREMENTS:

- Use professional fiscal note formatting with clear section headers
- Include specific dollar amounts from budget data with fiscal year breakdowns
- Reference exact program names, IDs, and agency information from the data
- Provide clear methodology explanations for all estimates
- Use descriptive source citations: "Budget Document [filename]" for internal documents, "Current Web Source: [Title]" for web information
- Ensure all financial data is substantiated by the provided budget information
- Include both one-time and ongoing cost implications
- Address implementation timeline and phasing if applicable

## DATA UTILIZATION:
- Use exact dollar amounts for FY 2025-2026 and FY 2026-2027 from budget items
- Reference specific program names and IDs from the data
- Include agency information and organizational structure details
- Incorporate appropriation types and funding sources
- Utilize current information from web sources for contemporary context and verification

Format as a professional fiscal note with substantive analysis using the specific financial data provided. Ensure all sections are comprehensive and based on available data."""

        elif query_type == "budget_analysis":
            answer_prompt = f"""You are a budget analyst providing detailed analysis from available data.

USER QUERY: "{state['query']}"
ANALYSIS CONTEXT: {json.dumps(reasoning, indent=2)}
SEARCH SUMMARY: Found {len(search_results)} documents across {len(state['collections_searched'])} collections
WEB INFORMATION: {len(web_results)} current web sources found

RETRIEVED DOCUMENTS WITH COMPLETE BUDGET DETAILS:
{context}

IMPORTANT: The budget items above include complete metadata with specific dollar amounts, program details, agencies, and appropriation types. Use this detailed information in your analysis. Web sources provide current context and verification.

Provide a comprehensive budget analysis focusing on actionable insights:

1. **KEY FINDINGS** - Highlight significant patterns, trends, and notable budget items with specific dollar amounts
2. **PROGRAM ANALYSIS** - Detail relevant programs with their IDs, funding amounts, and agency information
3. **FINANCIAL OVERVIEW** - Present the actual fiscal year amounts, funding sources, and appropriation types
4. **STRATEGIC INSIGHTS** - Analyze funding patterns, compare amounts across programs, and identify opportunities
5. **CURRENT CONTEXT** - Integrate web-sourced information about recent developments or policy changes
6. **RECOMMENDATIONS** - Suggest actions based on the specific financial data and current information

ANALYTICAL APPROACH: Use the complete budget item details provided, including:
- Specific dollar amounts for FY 2025-2026 and FY 2026-2027
- Program names and IDs 
- Agency information (expending agencies)
- Appropriation types (general funds, special funds, federal funds, etc.)
- Document sources and page references
- Current information from web sources for contemporary context

Present findings with specific dollar figures, program names, and agency details. Focus on what the financial data reveals about budget priorities, funding levels, and resource allocation patterns."""

        else:
            # General informational response
            answer_prompt = f"""You are a knowledgeable assistant providing comprehensive information from available sources.

USER QUERY: "{state['query']}"
INTENT: {reasoning.get('intent', 'Unknown')}
DOCUMENTS FOUND: {len(search_results)} across collections: {', '.join(state['collections_searched'])}
WEB SOURCES: {len(web_results)} current information sources

CONTEXT FROM RETRIEVED DOCUMENTS:
{context}

Provide a thorough and helpful response that maximizes the value of available information:

1. **DIRECT RESPONSE** - Address the user's question with available facts and details
2. **DETAILED INFORMATION** - Elaborate on relevant topics using specific data from sources
3. **CONTEXTUAL INSIGHTS** - Provide background and explanatory information that adds value
4. **CURRENT PERSPECTIVE** - Incorporate any relevant current information from web sources
5. **PRACTICAL APPLICATIONS** - Explain how this information can be used or applied
6. **COMPREHENSIVE COVERAGE** - Draw connections between different pieces of information

APPROACH: Work with all available information to provide the most complete and useful response possible. Use specific details, figures, program names, and other concrete information when available. Build understanding by connecting related concepts and providing context. Focus on delivering maximum value and actionable insights.

When referencing sources, be descriptive and user-friendly. Refer to "budget documents", "fiscal guidance", or "policy documents" for internal sources, and "current web information" or "recent sources" for web-based information. Avoid technical collection labels.

Be thorough, informative, and focus on providing practical value from the available information."""

        try:
            response = self.llm.invoke([HumanMessage(content=answer_prompt)])
            answer = response.content
            
            state["answer"] = answer
            state["context"] = context
            state["sources"] = sources
            state["confidence"] = reasoning.get("confidence", "medium")
            
            state["messages"].append(AIMessage(content=answer))
            
            print(f"✅ Answer generated successfully ({len(answer)} characters)")
            
        except Exception as e:
            print(f"❌ Error generating answer: {e}")
            state["answer"] = f"I apologize, but I encountered an error while generating the response: {str(e)}"
            state["context"] = context
            state["sources"] = sources
            state["confidence"] = "low"
            state["messages"].append(AIMessage(content=state["answer"]))
        
        return state
    
    def evaluate_results(self, state: AgentState) -> AgentState:
        """Evaluate search results quality and determine if refinement is needed"""
        
        search_results = state["search_results"]
        reasoning = state["reasoning"]
        query_type = reasoning.get("query_type", "informational")
        search_iterations = state["search_iterations"]
        max_iterations = state["max_iterations"]
        
        print(f"📊 Evaluating search results (iteration {search_iterations + 1}/{max_iterations})")
        
        # Record current search in history
        current_search = {
            "iteration": search_iterations + 1,
            "collections_searched": state["collections_searched"],
            "search_terms_used": state["search_terms_used"],
            "results_count": len(search_results),
            "reasoning": reasoning
        }
        state["search_history"].append(current_search)
        
        # Initialize quality scores
        quality_scores = {
            "completeness": 0.0,
            "relevance": 0.0,
            "coverage": 0.0,
            "financial_data": 0.0,
            "context_richness": 0.0
        }
        
        # Analyze result quality
        if not search_results:
            print("   ❌ No search results found - need refinement")
            state["needs_refinement"] = True
            state["refinement_strategy"] = {
                "reason": "no_results",
                "action": "broaden_search",
                "target_collections": ["budget", "text", "fiscal"],
                "search_terms": [state["query"]] + state["query"].split()
            }
            state["result_quality_scores"] = quality_scores
            return state
        
        # Categorize results by collection
        budget_items = [r for r in search_results if r.get("collection") == "budget"]
        fiscal_items = [r for r in search_results if r.get("collection") == "fiscal"]
        text_items = [r for r in search_results if r.get("collection") == "text"]
        
        # Calculate quality metrics
        total_results = len(search_results)
        
        # Completeness: Do we have enough results?
        min_expected = 30 if query_type == "budget_analysis" else 20
        quality_scores["completeness"] = min(1.0, total_results / min_expected)
        
        # Coverage: Are we searching the right collections for this query type?
        collections_searched = set(state["collections_searched"])
        if query_type == "budget_analysis":
            expected_collections = {"budget"}
            base_coverage = len(collections_searched & expected_collections) / len(expected_collections)
            # Bonus for cross-collection context in budget analysis
            if fiscal_items or text_items:
                quality_scores["coverage"] = min(1.0, base_coverage + 0.3)
            else:
                quality_scores["coverage"] = base_coverage
        else:
            expected_collections = set(reasoning.get("target_collections", ["budget", "text", "fiscal"]))
            quality_scores["coverage"] = len(collections_searched & expected_collections) / max(1, len(expected_collections))
        
        # Financial data quality (for budget queries)
        if query_type in ["budget_analysis", "fiscal_note"] and budget_items:
            financial_data_count = 0
            for item in budget_items:
                metadata = item.get("metadata", {})
                # Check for specific financial fields with actual values
                has_valid_amounts = False
                for field in ["fiscal_year_2025_2026_amount", "fiscal_year_2026_2027_amount"]:
                    value = metadata.get(field)
                    if value not in [None, "", "unknown"] and str(value).lower() != "unknown":
                        try:
                            # Check if it's a valid number
                            float(str(value).replace(',', '').replace('$', ''))
                            has_valid_amounts = True
                            break
                        except (ValueError, TypeError):
                            continue
                
                if has_valid_amounts:
                    financial_data_count += 1
            
            quality_scores["financial_data"] = financial_data_count / len(budget_items) if budget_items else 0.0
        else:
            quality_scores["financial_data"] = 1.0  # Not applicable for non-budget queries
        
        # Relevance: Average score of results
        if search_results:
            scores = [r.get("score", 0.0) for r in search_results]
            top_scores = sorted(scores, reverse=True)[:min(20, len(scores))]
            quality_scores["relevance"] = sum(top_scores) / len(top_scores)
        
        # Context richness: Do we have diverse information types?
        available_collections = set(["budget", "fiscal", "text"])
        present_collections = set([r.get("collection") for r in search_results])
        
        base_richness = len(present_collections & available_collections) / len(available_collections)
        
        if len(present_collections) > 1:
            collection_counts = {}
            for result in search_results:
                coll = result.get("collection", "unknown")
                collection_counts[coll] = collection_counts.get(coll, 0) + 1
            
            max_count = max(collection_counts.values()) if collection_counts else 0
            distribution_bonus = 0.2 if max_count < total_results * 0.8 else 0
            quality_scores["context_richness"] = min(1.0, base_richness + distribution_bonus)
        else:
            quality_scores["context_richness"] = base_richness
        
        # Overall quality assessment
        overall_quality = sum(quality_scores.values()) / len(quality_scores)
        state["result_quality_scores"] = quality_scores
        
        print(f"   📈 Quality Scores (Target: >0.8 for each):")
        print(f"      Completeness: {quality_scores['completeness']:.3f}")
        print(f"      Coverage: {quality_scores['coverage']:.3f}")
        print(f"      Financial Data: {quality_scores['financial_data']:.3f}")
        print(f"      Relevance: {quality_scores['relevance']:.3f}")
        print(f"      Context Richness: {quality_scores['context_richness']:.3f}")
        print(f"      Overall: {overall_quality:.3f}")
        
        # Determine if refinement is needed
        refinement_needed = False
        refinement_strategy = {}
        
        # Check if we've reached max iterations
        if search_iterations >= max_iterations - 1:
            print(f"   🛑 Reached maximum iterations ({max_iterations}) - proceeding with current results")
            state["needs_refinement"] = False
            return state
        
        # Check quality scores
        failing_metrics = []
        for metric, score in quality_scores.items():
            if score <= 0.8:
                failing_metrics.append(f"{metric}({score:.3f})")
        
        if failing_metrics:
            refinement_needed = True
            print(f"   🔄 Refinement needed - metrics below 0.8: {', '.join(failing_metrics)}")
            
            # Determine refinement strategy
            lowest_metric = min(quality_scores.items(), key=lambda x: x[1])
            lowest_metric_name, lowest_score = lowest_metric
            
            if lowest_metric_name == "completeness":
                refinement_strategy = {
                    "reason": f"insufficient_results (completeness: {lowest_score:.3f})",
                    "action": "expand_search",
                    "target_collections": ["budget", "text", "fiscal"],
                    "search_terms": state["search_terms_used"] + [
                        state["query"],
                        f"{state['query']} program",
                        f"{state['query']} policy"
                    ],
                    "num_results": 400
                }
            else:
                refinement_strategy = {
                    "reason": f"general_improvement ({lowest_metric_name}: {lowest_score:.3f})",
                    "action": "comprehensive_search",
                    "target_collections": ["budget", "text", "fiscal"],
                    "search_terms": [
                        state["query"],
                        f"{state['query']} detailed",
                        f"{state['query']} comprehensive"
                    ],
                    "num_results": 350
                }
        else:
            print(f"   ✅ All quality metrics above 0.8 - proceeding to answer generation")
        
        state["needs_refinement"] = refinement_needed
        state["refinement_strategy"] = refinement_strategy
        
        return state
    
    def refine_search(self, state: AgentState) -> AgentState:
        """Execute refined search based on evaluation results"""
        
        refinement_strategy = state["refinement_strategy"]
        search_iterations = state["search_iterations"]
        
        print(f"🔍 Executing refinement search (iteration {search_iterations + 2})")
        print(f"   Strategy: {refinement_strategy.get('action', 'unknown')}")
        print(f"   Reason: {refinement_strategy.get('reason', 'unknown')}")
        
        # Update iteration counter
        state["search_iterations"] += 1
        
        # Create tool-using LLM
        llm_with_tools = self.llm.bind_tools(self.tools)
        
        # Build refined search prompt
        target_collections = refinement_strategy.get("target_collections", ["budget"])
        search_terms = refinement_strategy.get("search_terms", [state["query"]])
        num_results = refinement_strategy.get("num_results", 200)
        action = refinement_strategy.get("action", "expand_search")
        
        refined_search_prompt = f"""You are conducting a REFINED search based on previous results analysis.

ORIGINAL QUERY: "{state['query']}"
ITERATION: {state['search_iterations'] + 1}

REFINEMENT STRATEGY:
- Reason: {refinement_strategy.get('reason', 'improve_results')}
- Action: {action}
- Target Collections: {target_collections}
- Search Terms: {search_terms}
- Target Results: {num_results}

Execute strategic searches using the available tools to gather the missing or improved information.
Focus on addressing the specific gaps identified in the previous search results."""

        try:
            messages = [
                SystemMessage(content="You are a research assistant conducting a refined search to improve results quality. Use tools strategically to address specific information gaps."),
                HumanMessage(content=refined_search_prompt)
            ]
            
            response = llm_with_tools.invoke(messages)
            
            # Execute any tool calls and merge with existing results
            new_search_results = []
            collections_searched = []
            search_terms_used = []
            
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    
                    print(f"   🔧 Executing refined tool: {tool_name} with args: {tool_args}")
                    
                    # Find and execute the tool
                    for tool in self.tools:
                        if tool.name == tool_name:
                            try:
                                result = tool.invoke(tool_args)
                                tool_data = json.loads(result)
                                
                                if "results" in tool_data:
                                    new_search_results.extend(tool_data["results"])
                                
                                if "collection" in tool_data:
                                    collections_searched.append(tool_data["collection"])
                                
                                if "collections_searched" in tool_data:
                                    collections_searched.extend(tool_data["collections_searched"])
                                
                                if "query" in tool_data:
                                    search_terms_used.append(tool_data["query"])
                                
                                print(f"      ✅ Refined tool {tool_name} found {len(tool_data.get('results', []))} new results")
                                
                            except Exception as e:
                                print(f"      ❌ Error executing refined tool {tool_name}: {e}")
                            break
            
            # Merge new results with existing ones
            all_results = state["search_results"] + new_search_results
            
            # Remove duplicates
            seen_ids = set()
            unique_results = []
            
            for result in all_results:
                result_id = result.get("metadata", {}).get("id", "")
                content_hash = hash(result.get("content", ""))
                unique_key = f"{result_id}_{content_hash}"
                
                if unique_key not in seen_ids:
                    seen_ids.add(unique_key)
                    unique_results.append(result)
            
            # Sort by score
            if unique_results and "score" in unique_results[0]:
                unique_results.sort(key=lambda x: x.get("score", 0), reverse=True)
            
            # Update state with merged results
            state["search_results"] = unique_results
            state["collections_searched"].extend(collections_searched)
            state["search_terms_used"].extend(search_terms_used)
            
            # Remove duplicates from metadata lists
            state["collections_searched"] = list(set(state["collections_searched"]))
            state["search_terms_used"] = list(set(state["search_terms_used"]))
            
            print(f"   📊 Refinement completed: {len(new_search_results)} new results, {len(unique_results)} total unique results")
            
            state["messages"].append(AIMessage(content=f"Refined search completed: Found {len(new_search_results)} additional results"))
            
        except Exception as e:
            print(f"   ❌ Error in refined search: {e}")
            state["messages"].append(AIMessage(content=f"Refined search failed: {str(e)}"))
        
        return state
    
    def answer_subquestions(self, state: AgentState) -> AgentState:
        """Generate answers for each subquestion using their retrieved documents"""
        
        subquestion_results = state["subquestion_results"]
        query = state["query"]
        
        print(f"💡 Generating answers for {len(subquestion_results)} subquestions")
        
        subquestion_answers = []
        
        for sq_result in subquestion_results:
            subq_id = sq_result["subquestion_id"]
            question = sq_result["question"]
            search_results = sq_result.get("search_results", [])
            
            if not search_results:
                # No documents found, provide a basic response
                answer = {
                    "subquestion_id": subq_id,
                    "question": question,
                    "answer": f"No relevant documents were found to answer this specific subquestion: {question}",
                    "confidence": "low",
                    "sources": [],
                    "key_findings": []
                }
                subquestion_answers.append(answer)
                print(f"      ⚠️ Q{subq_id}: No documents found")
                continue
            
            # Prepare context from search results
            context_parts = []
            sources = []
            
            for i, result in enumerate(search_results[:50]):
                content = result.get("content", "")
                if content:  # Only include sources with actual content
                    source_info = {
                        "content": content,
                        "metadata": {
                            "collection": result.get("collection", "Unknown"),
                            "document": result.get("document", f"Document_{i+1}"),
                            "search_type": result.get("search_type", "subquestion_search")
                        },
                        "score": result.get("score", 0)
                    }
                    sources.append(source_info)
                    context_parts.append(f"[Source {i+1}: {source_info['metadata']['document']}]\n{content}")
            
            context = "\n\n".join(context_parts)
            
            # Generate answer using LLM
            answer_prompt = f"""You are an expert analyst answering a specific subquestion as part of a larger analysis.

MAIN QUERY: "{query}"
SUBQUESTION: "{question}"

CONTEXT FROM RETRIEVED DOCUMENTS:
{context}

Based on the provided documents, answer the subquestion comprehensively. Your response should:

1. **Direct Answer**: Provide a clear, direct answer to the subquestion
2. **Key Findings**: Highlight 3-5 key findings from the documents
3. **Specific Details**: Include relevant numbers, dates, policies, or specific information
4. **Source Attribution**: Reference which documents support your points
5. **Confidence Assessment**: Indicate how well the documents answer the question

Format as:

**Answer:** [Direct answer to the subquestion]

**Key Findings:**
- [Finding 1 with source reference]
- [Finding 2 with source reference]
- [Finding 3 with source reference]

**Specific Details:**
[Include relevant numbers, policies, dates, or other specific information]

**Confidence:** [High/Medium/Low] - [Brief explanation of confidence level]

Focus specifically on this subquestion and provide actionable insights that will contribute to answering the main query."""

            try:
                response = self.llm.invoke([HumanMessage(content=answer_prompt)])
                answer_content = response.content.strip()
                
                # Extract key findings from the answer
                key_findings = []
                if "**Key Findings:**" in answer_content:
                    findings_section = answer_content.split("**Key Findings:**")[1].split("**")[0]
                    for line in findings_section.split('\n'):
                        line = line.strip()
                        if line.startswith('- '):
                            key_findings.append(line[2:])
                
                # Extract confidence level
                confidence = "medium"
                if "**Confidence:**" in answer_content:
                    conf_section = answer_content.split("**Confidence:**")[1].split("**")[0].strip()
                    if conf_section.lower().startswith("high"):
                        confidence = "high"
                    elif conf_section.lower().startswith("low"):
                        confidence = "low"
                
                answer = {
                    "subquestion_id": subq_id,
                    "question": question,
                    "answer": answer_content,
                    "confidence": confidence,
                    "sources": sources,
                    "key_findings": key_findings,
                    "documents_used": len(search_results)
                }
                
                subquestion_answers.append(answer)
                print(f"      ✅ Q{subq_id}: Generated answer ({len(answer_content)} chars, {confidence} confidence)")
                
            except Exception as e:
                print(f"      ❌ Error generating answer for Q{subq_id}: {e}")
                # Fallback answer
                fallback_answer = {
                    "subquestion_id": subq_id,
                    "question": question,
                    "answer": f"Based on the available documents, this subquestion relates to {question.lower()}. However, there was an error in generating a comprehensive answer.",
                    "confidence": "low",
                    "sources": sources,
                    "key_findings": [],
                    "error": str(e)
                }
                subquestion_answers.append(fallback_answer)
        
        state["subquestion_answers"] = subquestion_answers
        
        total_findings = sum(len(ans.get("key_findings", [])) for ans in subquestion_answers)
        print(f"   ✅ Generated answers for {len(subquestion_answers)} subquestions with {total_findings} total key findings")
        
        state["messages"].append(AIMessage(content=f"Generated comprehensive answers for {len(subquestion_answers)} subquestions"))
        
        return state
    
    def synthesize_final_answer(self, state: AgentState) -> AgentState:
        """Synthesize all subquestion answers into a comprehensive final response with additional vector search"""
        
        subquestion_answers = state["subquestion_answers"]
        query = state["query"]
        reasoning = state["reasoning"]
        primary_document_text = state.get("primary_document_text")
        
        print(f"🎯 Synthesizing final answer from {len(subquestion_answers)} subquestion answers")
        if primary_document_text:
            print(f"📄 Including primary document context in final synthesis")
        
        # 1. Perform one final vector search using insights from all subquestions
        print("   🔍 Performing final comprehensive vector search...")
        
        # Create a comprehensive search query from all subquestion insights
        all_key_findings = []
        all_sources = []
        
        for ans in subquestion_answers:
            all_key_findings.extend(ans.get("key_findings", []))
            all_sources.extend(ans.get("sources", []))
        
        # Create enhanced search query
        key_terms = " ".join(all_key_findings[:10])  # Top 10 key findings
        final_search_query = f"{query} {key_terms}"
        
        final_search_results = []
        try:
            # Perform final vector search across available collections
            tools = self.tools
            available_collections = getattr(self, 'collection_names', ['budget', 'text', 'fiscal'])
            
            # Try searching across collections for final synthesis
            for collection in available_collections:  # Search top 2 collections
                try:
                    final_results = tools[0].invoke({
                        "collection_name": collection,
                        "query": final_search_query,
                        "num_results": 50
                    })
                    
                    if isinstance(final_results, str):
                        import json
                        final_data = json.loads(final_results)
                        if "results" in final_data and final_data["results"]:
                            for result in final_data["results"]:
                                result["search_type"] = "final_synthesis"
                                result["collection_searched"] = collection
                                final_search_results.append(result)
                            print(f"      ✅ Final search in {collection}: {len(final_data['results'])} documents")
                except Exception as collection_error:
                    print(f"      ⚠️ Final search failed for {collection}: {collection_error}")
            
            if final_search_results:
                print(f"      ✅ Final search found {len(final_search_results)} total additional documents")
            else:
                print(f"      ℹ️ No additional documents found in final search")
                
        except Exception as e:
            print(f"      ⚠️ Final search failed: {e}")
        
        # 2. Prepare comprehensive context for synthesis
        synthesis_context_parts = []
        
        # Add subquestion answers
        for ans in subquestion_answers:
            synthesis_context_parts.append(f"""
SUBQUESTION {ans['subquestion_id']}: {ans['question']}
ANSWER: {ans['answer']}
CONFIDENCE: {ans['confidence']}
KEY FINDINGS: {'; '.join(ans.get('key_findings', []))}
""")
        
        # Add final search results
        if final_search_results:
            synthesis_context_parts.append("\nADDITIONAL CONTEXT FROM FINAL SEARCH:")
            for i, result in enumerate(final_search_results[:50]):
                content = result.get("content", "")
                synthesis_context_parts.append(f"[Additional Source {i+1}]: {content}")
        
        synthesis_context = "\n".join(synthesis_context_parts)
        
        # DEBUG: Track context lengths with optimization
        print(f"🔍 CONTEXT LENGTH DEBUG:")
        print(f"   Synthesis context length: {len(synthesis_context)} characters")
        print(f"   Number of subquestion answers: {len(subquestion_answers)}")
        print(f"   Number of final search results: {len(final_search_results)}")
        
        # 3. Generate final comprehensive answer
        query_type = reasoning.get("query_type", "informational")
        
        if query_type == "fiscal_note":
            # Use the comprehensive fiscal note prompt
            synthesis_prompt = f"""You are a fiscal analyst creating a comprehensive fiscal note. You have analyzed this query through multiple subquestions and gathered extensive information.

MAIN QUERY: "{query}"{primary_document_text}
{synthesis_context}

Based on all the subquestion analyses and additional research, create a comprehensive fiscal note following the standard format with all required sections:

1. **BILL STATUS**
2. **SUMMARY OF FISCAL IMPACT**
3. **APPROPRIATION SUMMARY**
4. **FISCAL NOTE STATUS**
5. **STATE FISCAL IMPACT TABLE**
6. **DETAILED ANALYSIS SECTIONS**

CRITICAL INSTRUCTIONS - YOU MUST COMPLETE ALL SECTIONS:
- Synthesizes information from all subquestion answers
- Includes specific financial data and numbers where available
- References multiple sources and documents
- Provides comprehensive analysis across all aspects
- Follows professional fiscal note formatting
- Addresses any gaps or uncertainties identified in the subquestion analysis
- COMPLETE ALL 6 SECTIONS LISTED ABOVE - DO NOT STOP EARLY
- FILL OUT THE ENTIRE FISCAL IMPACT TABLE WITH ALL ROWS
- PROVIDE DETAILED ANALYSIS FOR EACH SECTION
- YOUR RESPONSE SHOULD BE AT LEAST 2000 WORDS

Format as a complete, professional fiscal note document with ALL sections fully developed."""

        else:
            # General comprehensive synthesis
            synthesis_prompt = f"""You are an expert analyst providing a comprehensive response based on multi-step analysis.

MAIN QUERY: "{query}"
QUERY TYPE: {query_type}{primary_document_text}
{synthesis_context}

Based on all the subquestion analyses and additional research, provide a comprehensive answer that:

1. **Executive Summary**: Provide a clear, direct answer to the main query
2. **Key Findings**: Synthesize the most important findings from all subquestions
3. **Detailed Analysis**: Provide in-depth analysis organized by major themes
4. **Supporting Evidence**: Reference specific documents and sources
5. **Implications**: Discuss broader implications and recommendations
6. **Confidence Assessment**: Overall confidence level and any limitations

Structure your response clearly with headers and ensure you:
- Synthesize information from all {len(subquestion_answers)} subquestion analyses
- Highlight connections and patterns across different aspects
- Address the query comprehensively from multiple angles
- Provide actionable insights and recommendations
- Note any gaps or areas requiring additional research

Make this a definitive, comprehensive response that fully addresses the user's query."""

        # DEBUG: Track full prompt and response details
        total_prompt_length = len(synthesis_prompt)
        print(f"🔍 FULL SYNTHESIS DEBUG:")
        print(f"   Total prompt length: {total_prompt_length:,} characters")
        print(f"   Primary context section length: {len(primary_document_text):,} characters" if primary_document_text else "   No primary document context")
        print(f"   Synthesis context length: {len(synthesis_context):,} characters")
        print(f"   LLM max_tokens setting: 16000")
        print(f"   Estimated tokens (chars/4): ~{total_prompt_length//4:,} tokens")
        
        # Rough token estimation (1 token ≈ 4 characters for English)
        estimated_input_tokens = total_prompt_length // 4
        if estimated_input_tokens > 30000:  # Gemini 1.5 Flash context limit is ~1M tokens
            print(f"   ⚠️  WARNING: Estimated input tokens ({estimated_input_tokens:,}) may be approaching context limits")
        
        try:
            response = self.llm.invoke([HumanMessage(content=synthesis_prompt)])
            final_answer = response.content.strip()
            
            # DEBUG: Track response details
            print(f"   ✅ LLM Response received:")
            print(f"      Response length: {len(final_answer):,} characters")
            print(f"      Response word count: ~{len(final_answer.split()):,} words")
            print(f"      Response ends with: '{final_answer[-100:]}' (last 100 chars)" if len(final_answer) > 100 else f"      Full response: '{final_answer}'")
            
            # Check if response seems truncated
            if len(final_answer) < 1000:
                print(f"   ⚠️  WARNING: Response seems unusually short ({len(final_answer)} chars)")
            if not final_answer.endswith(('.', '!', '?', '"', "'")):
                print(f"   ⚠️  WARNING: Response may be truncated (doesn't end with punctuation)")
            
            # Compile comprehensive sources
            all_unique_sources = []
            seen_docs = set()
            
            for ans in subquestion_answers:
                for source in ans.get("sources", []):
                    doc_key = source.get("document", "")
                    if doc_key and doc_key not in seen_docs:
                        seen_docs.add(doc_key)
                        all_unique_sources.append(source)
            
            # Add final search sources with proper content and metadata
            for result in final_search_results:
                content = result.get("content", "")
                doc_key = result.get("document", content[:50] if content else "unknown")  # Use content preview as fallback
                if content and doc_key not in seen_docs:
                    seen_docs.add(doc_key)
                    all_unique_sources.append({
                        "content": content,
                        "metadata": {
                            "collection": result.get("collection", "Unknown"),
                            "document": doc_key,
                            "search_type": "final_synthesis"
                        },
                        "score": result.get("score", 0)
                    })
            
            # Calculate overall confidence
            confidences = [ans.get("confidence", "medium") for ans in subquestion_answers]
            high_conf = confidences.count("high")
            low_conf = confidences.count("low")
            
            if high_conf >= len(confidences) * 0.6:
                overall_confidence = "high"
            elif low_conf >= len(confidences) * 0.4:
                overall_confidence = "low"
            else:
                overall_confidence = "medium"
            
            state["answer"] = final_answer
            state["sources"] = all_unique_sources
            state["confidence"] = overall_confidence
            state["final_synthesis_context"] = synthesis_context
            
            # Compile search terms used across all subquestions
            all_search_terms = []
            for ans in subquestion_answers:
                all_search_terms.append(ans["question"])
            state["search_terms_used"] = all_search_terms
            
            print(f"   ✅ Synthesized final answer: {len(final_answer)} chars, {overall_confidence} confidence")
            print(f"   📚 Total sources: {len(all_unique_sources)} documents")
            print(f"   🎯 Subquestion confidence breakdown: {high_conf} high, {len(confidences)-high_conf-low_conf} medium, {low_conf} low")
            
            state["messages"].append(AIMessage(content=f"Generated comprehensive final answer synthesizing {len(subquestion_answers)} subquestion analyses with {len(all_unique_sources)} total sources"))
            
        except Exception as e:
            print(f"   ❌ CRITICAL ERROR in LLM synthesis call: {type(e).__name__}: {str(e)}")
            print(f"   📊 Context when error occurred:")
            print(f"      - Prompt length: {len(synthesis_prompt):,} chars")
            print(f"      - Estimated tokens: ~{len(synthesis_prompt)//4:,}")
            print(f"      - Subquestion answers: {len(subquestion_answers)}")
            print(f"      - Final search results: {len(final_search_results)}")
            
            # More detailed error information
            import traceback
            print(f"   🔍 Full error traceback:")
            traceback.print_exc()
            
            print(f"   🔄 Falling back to concatenated subquestion answers...")
            
            # Fallback synthesis
            fallback_answer = f"""Based on the multi-step analysis of your query "{query}", I have examined {len(subquestion_answers)} key aspects:

"""
            for ans in subquestion_answers:
                fallback_answer += f"**{ans['question']}**\n{ans['answer']}\n\n"
            
            fallback_answer += f"""
**Summary**: The analysis covered multiple dimensions of your query through {len(subquestion_answers)} focused subquestions. While there was an error in the final synthesis, the individual analyses above provide comprehensive coverage of the topic.

**Sources**: Information drawn from {len(all_unique_sources)} documents across multiple collections.
"""
            
            state["answer"] = fallback_answer
            state["sources"] = all_unique_sources
            state["confidence"] = "medium"
            state["messages"].append(AIMessage(content=f"Generated fallback synthesis from {len(subquestion_answers)} subquestion analyses"))
        
        return state

    def process_query_with_single_pdf_stream(self, query: str, primary_collection: str, context_collections: list = None, threshold: float = 0.0):
        """Streaming version that yields real-time updates during subquestion processing"""
        import time
        from datetime import datetime
        
        try:
            start_time = time.time()
            
            # Yield initial status
            yield {
                "type": "status",
                "message": "Initializing multi-step reasoning...",
                "timestamp": datetime.now().isoformat(),
                "stage": "initialization"
            }
            time.sleep(0.1)  # Small delay to ensure proper streaming
            
            # Set up collections
            all_collections = [primary_collection]
            if context_collections:
                all_collections.extend(context_collections)
            
            # Initialize state with proper data structures
            initial_state = {
                "query": query,
                "collections": all_collections,
                "primary_collection": primary_collection,
                "context_collections": context_collections or [],
                "subquestions": [],
                "hypothetical_answers": [],
                "subquestion_answers": [],
                "subquestion_results": [],
                "search_results": [],
                "web_results": [],
                "answer": "",
                "reasoning": {},  # Must be dict, not string!
                "sources": [],
                "threshold": threshold,
                "messages": [],  # Add messages list for workflow compatibility
                "primary_document_text": "",  # Required by generate_hypothetical_answers
                "parallel_processing_enabled": True  # Enable parallel processing
            }
            
            # Yield subquestion generation start
            yield {
                "type": "status",
                "message": "Generating subquestions for comprehensive analysis...",
                "timestamp": datetime.now().isoformat(),
                "stage": "subquestion_generation"
            }
            time.sleep(0.1)  # Small delay to ensure proper streaming
            
            # Generate subquestions using the correct workflow method
            print("🔍 DEBUG: Starting decompose_query...")
            try:
                state = self.decompose_query(initial_state)
                print(f"🔍 DEBUG: decompose_query completed. State keys: {list(state.keys())}")
                print(f"🔍 DEBUG: subquestions type: {type(state.get('subquestions', []))}")
            except Exception as e:
                print(f"❌ DEBUG: Error in decompose_query: {e}")
                raise
            
            # Extract subquestion text for frontend display
            try:
                subquestion_texts = [sq["question"] for sq in state["subquestions"]]
                print(f"🔍 DEBUG: Extracted {len(subquestion_texts)} subquestion texts")
            except Exception as e:
                print(f"❌ DEBUG: Error extracting subquestion texts: {e}")
                print(f"❌ DEBUG: subquestions data: {state.get('subquestions', [])}")
                raise
            
            # Yield generated subquestions
            yield {
                "type": "subquestions_generated",
                "subquestions": subquestion_texts,
                "count": len(subquestion_texts),
                "timestamp": datetime.now().isoformat()
            }
            time.sleep(0.2)  # Delay to allow frontend to process subquestions
            
            # Generate hypothetical answers for all subquestions
            yield {
                "type": "status",
                "message": "Generating hypothetical answers to guide document search...",
                "timestamp": datetime.now().isoformat(),
                "stage": "hypothetical_answer"
            }
            
            print("🔍 DEBUG: Starting generate_hypothetical_answers...")
            try:
                state = self.generate_hypothetical_answers(state)
                print(f"🔍 DEBUG: generate_hypothetical_answers completed. hypothetical_answers type: {type(state.get('hypothetical_answers', []))}")
            except Exception as e:
                print(f"❌ DEBUG: Error in generate_hypothetical_answers: {e}")
                raise
            
            # Extract hypothetical answers for frontend display
            try:
                # Debug: Print the actual structure of hypothetical answers
                print(f"🔍 DEBUG: hypothetical_answers structure: {state.get('hypothetical_answers', [])}")
                
                # Handle different possible structures
                hypothetical_answer_texts = []
                for ha in state["hypothetical_answers"]:
                    if isinstance(ha, dict):
                        if "answer" in ha:
                            hypothetical_answer_texts.append(ha["answer"])
                        elif "hypothesis" in ha:
                            hypothetical_answer_texts.append(ha["hypothesis"])
                        elif "content" in ha:
                            hypothetical_answer_texts.append(ha["content"])
                        else:
                            # If it's a dict but no expected keys, convert to string
                            hypothetical_answer_texts.append(str(ha))
                    else:
                        # If it's not a dict, use as-is
                        hypothetical_answer_texts.append(str(ha))
                        
                print(f"🔍 DEBUG: Extracted {len(hypothetical_answer_texts)} hypothetical answer texts")
            except Exception as e:
                print(f"❌ DEBUG: Error extracting hypothetical answer texts: {e}")
                print(f"❌ DEBUG: hypothetical_answers data: {state.get('hypothetical_answers', [])}")
                # Fallback to empty list
                hypothetical_answer_texts = []
            
            yield {
                "type": "hypothetical_answers_generated",
                "hypothetical_answers": hypothetical_answer_texts,
                "timestamp": datetime.now().isoformat()
            }
            time.sleep(0.2)  # Delay to allow frontend to process hypothetical answers
            
            # Perform parallel search for all subquestions
            yield {
                "type": "status",
                "message": "Performing parallel document search for all subquestions...",
                "timestamp": datetime.now().isoformat(),
                "stage": "search"
            }
            time.sleep(0.1)  # Small delay to ensure proper streaming
            
            print("🔍 DEBUG: Starting parallel_subquestion_search...")
            try:
                state = self.parallel_subquestion_search(state)
                print(f"🔍 DEBUG: parallel_subquestion_search completed. subquestion_results type: {type(state.get('subquestion_results', []))}")
            except Exception as e:
                print(f"❌ DEBUG: Error in parallel_subquestion_search: {e}")
                raise
            
            # Process each subquestion with streaming updates
            for i, subquestion_data in enumerate(state["subquestions"]):
                subquestion_text = subquestion_data["question"]
                
                yield {
                    "type": "subquestion_start",
                    "subquestion": subquestion_text,
                    "index": i,
                    "total": len(state["subquestions"]),
                    "timestamp": datetime.now().isoformat()
                }
                time.sleep(0.1)  # Small delay between subquestions
                
                # Generate answer for this subquestion
                yield {
                    "type": "status",
                    "message": f"Analyzing subquestion {i+1}/{len(state['subquestions'])}: {subquestion_text[:100]}...",
                    "timestamp": datetime.now().isoformat(),
                    "stage": "answer_generation",
                    "subquestion_index": i
                }
                time.sleep(0.1)  # Small delay for status updates
            
            # Stream each subquestion answer as soon as it is generated
            subquestion_answers = []
            for i, subquestion_data in enumerate(state["subquestions"]):
                subquestion_text = subquestion_data["question"]
                
                # Prepare context for this subquestion
                search_results = []
                if i < len(state.get("subquestion_results", [])):
                    search_results = state["subquestion_results"][i].get("search_results", [])
                
                # Build primary document context
                primary_document_text = state.get("primary_document_text", "")
                prompt_context = f"PRIMARY DOCUMENT CONTEXT:\n{primary_document_text}\n\n" if primary_document_text else ""
                
                # Build context from search results
                context_parts = []
                sources = []
                for j, result in enumerate(search_results[:50]):
                    content = result.get("content", "")
                    if content:
                        source_info = {
                            "content": content,
                            "metadata": {
                                "collection": result.get("collection", "Unknown"),
                                "document": result.get("document", f"Document_{j+1}"),
                                "search_type": result.get("search_type", "subquestion_search")
                            },
                            "score": result.get("score", 0)
                        }
                        sources.append(source_info)
                        context_parts.append(f"[Source {j+1}: {source_info['metadata']['document']}]\n{content}")
                context = "\n\n".join(context_parts)
                
                # Generate answer using LLM
                answer_prompt = f"""You are an expert analyst answering a specific subquestion as part of a larger analysis.\n\n{prompt_context}MAIN QUERY: \"{query}\"\nSUBQUESTION: \"{subquestion_text}\"\n\nCONTEXT FROM RETRIEVED DOCUMENTS:\n{context}\n\nBased on the provided documents, answer the subquestion comprehensively. Your response should:\n\n1. **Direct Answer**: Provide a clear, direct answer to the subquestion\n2. **Key Findings**: Highlight 3-5 key findings from the documents\n3. **Specific Details**: Include relevant numbers, dates, policies, or specific information\n4. **Source Attribution**: Reference which documents support your points\n5. **Confidence Assessment**: Indicate how well the documents answer the question\n\nFormat as:\n\n**Answer:** [Direct answer to the subquestion]\n\n**Key Findings:**\n- [Finding 1 with source reference]\n- [Finding 2 with source reference]\n- [Finding 3 with source reference]\n\n**Specific Details:**\n[Include relevant numbers, policies, dates, or other specific information]\n\n**Confidence:** [High/Medium/Low] - [Brief explanation of confidence level]\n\nFocus specifically on this subquestion and provide actionable insights that will contribute to answering the main query."""
                try:
                    response = self.llm.invoke([HumanMessage(content=answer_prompt)])
                    answer_content = response.content.strip()
                    # No truncation: send full answer
                    confidence = "medium"
                    if "**Confidence:**" in answer_content:
                        conf_section = answer_content.split("**Confidence:**")[1].split("**")[0].strip()
                        if conf_section.lower().startswith("high"):
                            confidence = "high"
                        elif conf_section.lower().startswith("low"):
                            confidence = "low"
                    answer = {
                        "subquestion_id": i,
                        "question": subquestion_text,
                        "answer": answer_content,
                        "confidence": confidence,
                        "sources": sources,
                        "documents_used": len(search_results)
                    }
                except Exception as e:
                    answer = {
                        "subquestion_id": i,
                        "question": subquestion_text,
                        "answer": f"Error generating answer: {str(e)}",
                        "confidence": "low",
                        "sources": sources,
                        "documents_used": len(search_results)
                    }
                subquestion_answers.append(answer)
                yield {
                    "type": "subquestion_completed",
                    "subquestion": subquestion_text,
                    "answer": answer["answer"],
                    "index": i,
                    "search_results_count": len(search_results),
                    "timestamp": datetime.now().isoformat()
                }
                time.sleep(0.2)
            state["subquestion_answers"] = subquestion_answers
            
            # Final synthesis
            yield {
                "type": "status",
                "message": "Synthesizing comprehensive final answer...",
                "timestamp": datetime.now().isoformat(),
                "stage": "final_synthesis"
            }
            time.sleep(0.2)  # Delay before final synthesis
            
            # Synthesize final answer
            final_state = self.synthesize_final_answer(state)
            
            # Process sources and create final response
            processing_time = time.time() - start_time
            
            # Filter and organize sources with proper type checking
            all_sources = final_state.get("sources", [])
            
            # Ensure all sources are dictionaries
            valid_sources = []
            for s in all_sources:
                if isinstance(s, dict):
                    valid_sources.append(s)
                else:
                    print(f"Warning: Invalid source type {type(s)}: {s}")
            
            primary_sources = [s for s in valid_sources if s.get("collection") == primary_collection]
            context_sources = [s for s in valid_sources if s.get("collection") != primary_collection]
            
            # Create search summary with safe data extraction
            collections_searched = list(set([s.get("collection", "unknown") for s in valid_sources]))
            
            # Safely extract search terms
            search_terms = []
            try:
                subquestion_results = final_state.get("subquestion_results", [])
                for subq_results in subquestion_results:
                    if isinstance(subq_results, list):
                        for result in subq_results:
                            if isinstance(result, dict) and "search_terms" in result:
                                terms = result.get("search_terms", [])
                                if isinstance(terms, list):
                                    search_terms.extend(terms)
                search_terms = list(set(search_terms))
            except Exception as e:
                print(f"Warning: Error extracting search terms: {e}")
                search_terms = []
            
            # Safely build response with error handling
            response = {
                "response": final_state.get("answer", "No answer generated"),
                "sources": valid_sources,
                "reasoning": final_state.get("reasoning", "No reasoning available"),
                "primary_collection": primary_collection,
                "context_collections": context_collections,
                "processing_time": processing_time,
                "search_summary": {
                    "collections_searched": collections_searched,
                    "search_terms_used": search_terms[:20],  # Limit to top 20
                    "total_documents_found": len(valid_sources),
                    "primary_sources_count": len(primary_sources),
                    "context_sources_count": len(context_sources)
                },
                "subquestions": final_state.get("subquestions", []),
                "hypothetical_answers": final_state.get("hypothetical_answers", []),
                "subquestion_answers": final_state.get("subquestion_answers", []),
                "subquestion_results": final_state.get("subquestion_results", []),
                "final_state": {
                    "total_subquestions": len(final_state.get("subquestions", [])),
                    "total_search_results": len(final_state.get("search_results", [])),
                    "total_web_results": len(final_state.get("web_results", [])),
                    "answer_length": len(str(final_state.get("answer", ""))),
                    "reasoning_length": len(str(final_state.get("reasoning", "")))
                }
            }
            
            # Yield final completion
            yield {
                "type": "completed",
                "response": response,
                "processing_time": processing_time,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            logging.error(f"Error in streaming process_query_with_single_pdf: {str(e)}")
            logging.error(f"Full traceback: {error_traceback}")
            print(f"❌ STREAMING ERROR: {e}")
            print(f"❌ FULL TRACEBACK: {error_traceback}")
            yield {
                "type": "error",
                "message": f"Streaming error: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }