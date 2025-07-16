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


class LangGraphRAGAgent:
    """LangGraph-based RAG agent with tool usage"""
    
    def __init__(self, collection_managers: Dict[str, Any], config: Dict[str, Any]):
        self.collection_managers = collection_managers
        self.config = config
        self.collection_names = config["collections"]
        
        # Initialize the LLM
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0.1,
            max_tokens=2000
        )
        
        # Create tools
        self.tools = self._create_tools()
        
        # Create the graph
        self.graph = self._create_graph()
    
    def _create_tools(self) -> List:
        """Create tools for the agent to use"""
        
        @tool
        def search_collection(collection_name: str, query: str, num_results: int = 200) -> str:
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
                    formatted_results.append({
                        "content": result["content"],
                        "metadata": result.get("metadata", {}),
                        "score": result.get("score", 0.0),
                        "collection": collection_name
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
        def search_across_collections(query: str, collections: List[str] = None, num_results: int = 200) -> str:
            """
            Search across multiple collections simultaneously.
            
            Args:
                query: Search query
                collections: List of collection names to search (optional, defaults to all)
                num_results: Total number of results to return across all collections
            
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
                
                # Limit results to reasonable range
                num_results = min(max(1, num_results), 10)
                
                print(f"🌐 Searching web for: '{query}' (requesting {num_results} results)")
                
                # Format query for search
                encoded_query = quote(query)
                results = []
                
                # Try multiple approaches for web search
                
                # Approach 1: Try DuckDuckGo API
                try:
                    ddg_url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_html=1&skip_disambig=1"
                    response = requests.get(ddg_url, timeout=10, headers={'User-Agent': 'RAG-System/1.0'})
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        # Get instant answer if available
                        if data.get("AbstractText"):
                            results.append({
                                "title": data.get("Heading", "DuckDuckGo Instant Answer"),
                                "snippet": data.get("AbstractText", "")[:500],  # Limit snippet length
                                "url": data.get("AbstractURL", "https://duckduckgo.com"),
                                "source": "DuckDuckGo Instant Answer"
                            })
                        
                        # Get related topics
                        for topic in data.get("RelatedTopics", [])[:num_results-len(results)]:
                            if isinstance(topic, dict) and topic.get("Text"):
                                results.append({
                                    "title": topic.get("Text", "")[:100] + "..." if len(topic.get("Text", "")) > 100 else topic.get("Text", ""),
                                    "snippet": topic.get("Text", "")[:500],
                                    "url": topic.get("FirstURL", ""),
                                    "source": "DuckDuckGo Related Topic"
                                })
                        
                        if results:
                            print(f"   ✅ DuckDuckGo search found {len(results)} results")
                    else:
                        print(f"   ⚠️ DuckDuckGo returned status {response.status_code}")
                    
                except Exception as e:
                    print(f"   ⚠️ DuckDuckGo search failed: {e}")
                
                # Approach 2: Try Wikipedia search (more general topics)
                if len(results) < num_results:
                    try:
                        # Search Wikipedia for general topics
                        search_terms = query.split()[:3]  # Use first 3 words for search
                        for term in search_terms:
                            if len(results) >= num_results:
                                break
                                
                            wiki_search_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(term)}"
                            wiki_response = requests.get(wiki_search_url, timeout=10, headers={'User-Agent': 'RAG-System/1.0'})
                            
                            if wiki_response.status_code == 200:
                                wiki_data = wiki_response.json()
                                
                                if wiki_data.get("extract") and len(wiki_data.get("extract", "")) > 50:
                                    results.append({
                                        "title": f"Wikipedia: {wiki_data.get('title', term)}",
                                        "snippet": wiki_data.get("extract", "")[:500],
                                        "url": wiki_data.get("content_urls", {}).get("desktop", {}).get("page", f"https://en.wikipedia.org/wiki/{quote(term)}"),
                                        "source": "Wikipedia"
                                    })
                                    print(f"   ✅ Wikipedia found result for '{term}'")
                                    break  # Found one good result, that's enough for context
                    
                    except Exception as e:
                        print(f"   ⚠️ Wikipedia search failed: {e}")
                
                # If we have results, return them
                if results:
                    final_results = results[:num_results]
                    return json.dumps({
                        "query": query,
                        "source": "Web Search (Multiple Sources)",
                        "results_count": len(final_results),
                        "results": final_results,
                        "search_timestamp": time.time()
                    })
                
                # Approach 3: Provide intelligent suggestions and search guidance
                print(f"   ℹ️ External search APIs unavailable, providing search guidance")
                
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
                    "note": "External APIs temporarily unavailable - search guidance provided"
                }
                
                print(f"   💡 Provided search guidance with {len(search_suggestions)} suggested sources")
                return json.dumps(fallback_result)
                
            except ImportError:
                return json.dumps({
                    "error": "Web search requires 'requests' library. Install with: pip install requests",
                    "query": query,
                    "installation_note": "Run 'pip install requests' to enable web search functionality"
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
        workflow.add_node("analyze_query", self.analyze_query)
        workflow.add_node("search_documents", self.search_documents)
        workflow.add_node("evaluate_results", self.evaluate_results)
        workflow.add_node("refine_search", self.refine_search)
        workflow.add_node("generate_answer", self.generate_answer)
        
        # Define conditional routing function
        def should_refine(state: AgentState) -> str:
            """Determine if we should refine search or generate answer"""
            if state.get("needs_refinement", False):
                return "refine_search"
            else:
                return "generate_answer"
        
        # Add edges with conditional routing
        workflow.set_entry_point("analyze_query")
        workflow.add_edge("analyze_query", "search_documents")
        workflow.add_edge("search_documents", "evaluate_results")
        
        # Conditional edge: evaluate_results → refine_search OR generate_answer
        workflow.add_conditional_edges(
            "evaluate_results",
            should_refine,
            {
                "refine_search": "refine_search",
                "generate_answer": "generate_answer"
            }
        )
        
        # After refinement, go back to evaluation (creates the loop)
        workflow.add_edge("refine_search", "evaluate_results")
        
        # End after generating answer
        workflow.add_edge("generate_answer", END)
        
        return workflow.compile()
    
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
                    "source_file": ingestion_config.get("source_file", "unknown") if ingestion_config else "unknown"
                }
            except Exception as e:
                collection_info[collection_name] = {"error": str(e)}
        
        analysis_prompt = f"""Analyze this user query and create a search strategy.

AVAILABLE COLLECTIONS:
{json.dumps(collection_info, indent=2)}

USER QUERY: "{state['query']}"

Based on the query and available collections, determine:

1. INTENT: What is the user trying to accomplish?
2. QUERY_TYPE: Classify as one of:
   - "budget_analysis": Questions about budget items, appropriations, spending
   - "fiscal_note": Creating or understanding fiscal notes
   - "text_search": General text-based document search
   - "comparative_analysis": Comparing different items or programs
   - "informational": General information requests

3. TARGET_COLLECTIONS: Which collections are most relevant? Choose from: {', '.join(self.collection_names)}
4. SEARCH_STRATEGY: How should we approach searching?
5. SEARCH_TERMS: 3-5 specific terms or phrases to search for
6. OUTPUT_FORMAT: What type of response would be most helpful?

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
                
                print(f"   Raw response: {content[:100]}...")
                
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
        
        # All attempts failed - use fallback
        print(f"❌ All analysis attempts failed, using fallback strategy")
        
        # Smart fallback based on query keywords
        query_lower = state["query"].lower()
        
        if any(word in query_lower for word in ["budget", "appropriation", "funding", "cost", "expense"]):
            query_type = "budget_analysis"
            target_collections = ["budget"] if "budget" in self.collection_names else self.collection_names
        elif any(word in query_lower for word in ["fiscal", "note", "impact", "analysis"]):
            query_type = "fiscal_note"
            target_collections = ["fiscal", "budget"] if all(c in self.collection_names for c in ["fiscal", "budget"]) else self.collection_names
        else:
            query_type = "informational"
            target_collections = self.collection_names
        
        state["reasoning"] = {
            "intent": f"search for information about: {state['query']}",
            "query_type": query_type,
            "target_collections": target_collections,
            "search_strategy": "broad search with keyword matching",
            "search_terms": [state["query"]] + state["query"].split()[:3],
            "output_format": "informational",
            "confidence": "low"
        }
        state["messages"].append(AIMessage(content="Analysis failed, using keyword-based fallback strategy"))
        
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
- Limit to 3-5 web results to avoid information overload
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
            if unique_results and "score" in unique_results[0]:
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
                                results = manager.search_similar_chunks(search_term, 25)
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
        
        for i, result in enumerate(search_results[:50]):  # Increased from 20 to 50 results
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
                "content": content[:800],  # Increased from 300 to 800 chars
                "metadata": {k: v for k, v in result.get("metadata", {}).items() 
                           if k not in ['search_term', 'reasoning_intent']},
                "score": result.get("score"),
                "collection": collection
            })
        
        # Add web search results to context
        for i, result in enumerate(web_results[:10]): # Limit web results to 10 for context
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
            answer_prompt = f"""You are a fiscal analyst creating specific fiscal notes from budget data.

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

Create a comprehensive fiscal note using the available budget data. Focus on providing valuable insights and actionable information:

1. **FISCAL IMPACT SUMMARY** - Present the specific dollar amounts and financial data from the budget items
2. **AFFECTED PROGRAMS** - Detail the specific programs with their IDs, names, and responsible agencies
3. **DETAILED ANALYSIS** - Use the actual fiscal year amounts, appropriation types, and funding sources
4. **METHODOLOGY** - Explain how you derived estimates from the specific budget data provided
5. **IMPLEMENTATION INSIGHTS** - Provide practical guidance based on the financial details and program information
6. **CURRENT CONTEXT** - Incorporate any relevant current information from web sources to provide contemporary perspective

APPROACH: Use the complete budget item details provided, including:
- Exact dollar amounts for FY 2025-2026 and FY 2026-2027
- Specific program names and IDs
- Agency information and organizational structure
- Appropriation types and funding sources
- Document references for verification
- Current information from web sources for context and verification

When citing sources, use descriptive references like "Budget Document [filename]" or "Appropriations Table" for internal documents, and "Current Web Source: [Title]" for web information. Make your citations clear and professional.

Format as a professional fiscal note with clear sections and substantive analysis using the specific financial data provided."""

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
        
        # Completeness: Do we have enough results? (Stricter requirements)
        min_expected = 30 if query_type == "budget_analysis" else 20  # Increased expectations
        quality_scores["completeness"] = min(1.0, total_results / min_expected)
        
        # Coverage: Are we searching the right collections for this query type?
        collections_searched = set(state["collections_searched"])
        if query_type == "budget_analysis":
            expected_collections = {"budget"}
            base_coverage = len(collections_searched & expected_collections) / len(expected_collections)
            # Bonus for cross-collection context in budget analysis
            if fiscal_items or text_items:
                quality_scores["coverage"] = min(1.0, base_coverage + 0.3)  # Bonus for additional context
            else:
                quality_scores["coverage"] = base_coverage
        else:
            expected_collections = set(reasoning.get("target_collections", ["budget", "text", "fiscal"]))
            quality_scores["coverage"] = len(collections_searched & expected_collections) / max(1, len(expected_collections))
        
        # Financial data quality (for budget queries) - More stringent
        if query_type in ["budget_analysis", "fiscal_note"] and budget_items:
            financial_data_count = 0
            for item in budget_items:
                metadata = item.get("metadata", {})
                # Check for specific financial fields with actual values (not "unknown")
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
        
        # Relevance: Average score of results (More stringent threshold)
        if search_results:
            scores = [r.get("score", 0.0) for r in search_results]
            # Apply stricter weighting - only consider top-scoring results
            top_scores = sorted(scores, reverse=True)[:min(20, len(scores))]  # Top 20 results
            quality_scores["relevance"] = sum(top_scores) / len(top_scores)
        
        # Context richness: Do we have diverse information types and good distribution?
        available_collections = set(["budget", "fiscal", "text"])
        present_collections = set([r.get("collection") for r in search_results])
        
        # Base richness from collection diversity
        base_richness = len(present_collections & available_collections) / len(available_collections)
        
        # Bonus for good distribution of results across collections
        if len(present_collections) > 1:
            collection_counts = {}
            for result in search_results:
                coll = result.get("collection", "unknown")
                collection_counts[coll] = collection_counts.get(coll, 0) + 1
            
            # Check if we have reasonable distribution (no single collection dominates too much)
            max_count = max(collection_counts.values()) if collection_counts else 0
            distribution_bonus = 0.2 if max_count < total_results * 0.8 else 0  # Bonus if no collection has >80%
            quality_scores["context_richness"] = min(1.0, base_richness + distribution_bonus)
        else:
            quality_scores["context_richness"] = base_richness
        
        # Overall quality assessment (not used for decision, but for logging)
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
        
        # NEW STRINGENT REQUIREMENT: ALL quality scores must be > 0.8
        failing_metrics = []
        for metric, score in quality_scores.items():
            if score <= 0.8:
                failing_metrics.append(f"{metric}({score:.3f})")
        
        if failing_metrics:
            refinement_needed = True
            print(f"   🔄 Refinement needed - metrics below 0.8: {', '.join(failing_metrics)}")
            
            # Determine primary refinement strategy based on lowest score
            lowest_metric = min(quality_scores.items(), key=lambda x: x[1])
            lowest_metric_name, lowest_score = lowest_metric
            
            if lowest_metric_name == "completeness":
                # Need significantly more results
                refinement_strategy = {
                    "reason": f"insufficient_results (completeness: {lowest_score:.3f})",
                    "action": "expand_search",
                    "target_collections": ["budget", "text", "fiscal"],
                    "search_terms": state["search_terms_used"] + [
                        state["query"],
                        f"{state['query']} program",
                        f"{state['query']} policy"
                    ],
                    "num_results": 400  # Increased for better completeness
                }
                
            elif lowest_metric_name == "financial_data":
                # Need better financial data
                refinement_strategy = {
                    "reason": f"poor_financial_data (financial_data: {lowest_score:.3f})",
                    "action": "financial_focus",
                    "target_collections": ["budget"],
                    "search_terms": [
                        f"{state['query']} appropriation amount",
                        f"{state['query']} fiscal year budget",
                        f"{state['query']} funding allocation",
                        "budget amount fiscal year 2025",
                        "budget amount fiscal year 2026",
                        f"{state['query']} total cost"
                    ],
                    "num_results": 300
                }
                
            elif lowest_metric_name == "context_richness":
                # Need more diverse context
                missing_collections = []
                for coll in ["budget", "fiscal", "text"]:
                    if not any(r.get("collection") == coll for r in search_results):
                        missing_collections.append(coll)
                
                refinement_strategy = {
                    "reason": f"insufficient_context (context_richness: {lowest_score:.3f})",
                    "action": "diversify_search",
                    "target_collections": missing_collections or ["text", "fiscal"],
                    "search_terms": [
                        f"{state['query']} policy framework",
                        f"{state['query']} implementation guide",
                        f"{state['query']} fiscal analysis",
                        f"{state['query']} background",
                        "governance policy"
                    ],
                    "num_results": 250
                }
                
            elif lowest_metric_name == "relevance":
                # Need more relevant results with targeted terms
                refinement_strategy = {
                    "reason": f"low_relevance (relevance: {lowest_score:.3f})",
                    "action": "refine_terms",
                    "target_collections": state["collections_searched"] or ["budget", "text"],
                    "search_terms": [
                        # More specific and targeted terms
                        f"\"{state['query']}\"",  # Exact phrase
                        state["query"].replace(" ", " AND "),
                        *[term for term in state["query"].split() if len(term) > 3],
                        f"{state['query']} specific",
                        f"{state['query']} detailed"
                    ],
                    "num_results": 300
                }
                
            elif lowest_metric_name == "coverage":
                # Need better collection coverage
                target_collections = reasoning.get("target_collections", ["budget", "text", "fiscal"])
                missing_collections = [c for c in target_collections if c not in collections_searched]
                
                refinement_strategy = {
                    "reason": f"insufficient_coverage (coverage: {lowest_score:.3f})",
                    "action": "expand_coverage",
                    "target_collections": missing_collections or target_collections,
                    "search_terms": [
                        state["query"],
                        f"{state['query']} comprehensive",
                        f"{state['query']} overview"
                    ],
                    "num_results": 250
                }
            
            else:
                # Fallback strategy
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
        
        if refinement_needed:
            print(f"      Primary issue: {refinement_strategy.get('reason', 'unknown')}")
            print(f"      Action: {refinement_strategy.get('action', 'unknown')}")
            print(f"      Target collections: {refinement_strategy.get('target_collections', [])}")
        
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
        
        # Previous search summary
        prev_results_summary = f"Previous search found {len(state['search_results'])} results from {', '.join(state['collections_searched'])}"
        
        refined_search_prompt = f"""You are conducting a REFINED search based on previous results analysis.

ORIGINAL QUERY: "{state['query']}"
ITERATION: {state['search_iterations'] + 1}

PREVIOUS SEARCH SUMMARY:
{prev_results_summary}

REFINEMENT STRATEGY:
- Reason: {refinement_strategy.get('reason', 'improve_results')}
- Action: {action}
- Target Collections: {target_collections}
- Search Terms: {search_terms}
- Target Results: {num_results}

REFINED SEARCH INSTRUCTIONS:

{self._get_refinement_instructions(action, refinement_strategy)}

Execute strategic searches using the available tools to gather the missing or improved information.
Focus on addressing the specific gaps identified in the previous search results."""

        try:
            # Let the LLM decide which tools to use for refinement
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
    
    def _get_refinement_instructions(self, action: str, strategy: Dict[str, Any]) -> str:
        """Generate specific instructions for different refinement actions"""
        
        if action == "expand_search":
            return """
EXPAND SEARCH STRATEGY:
- Use search_across_collections with high num_results to cast a wider net
- Try multiple variations of search terms including program and policy terms
- Search all available collections for comprehensive coverage
- Focus on finding significantly more documents that match the query intent
- Use broader search terms to capture more relevant content"""

        elif action == "financial_focus":
            return """
FINANCIAL FOCUS STRATEGY:
- Use search_collection specifically on 'budget' collection with high num_results
- Search for terms like 'appropriation amount', 'fiscal year budget', 'funding allocation'
- Look for documents with specific dollar amounts and detailed financial metadata
- Prioritize budget items with complete and valid financial data (actual numbers, not 'unknown')
- Focus on finding budget entries with clear fiscal year amounts"""

        elif action == "diversify_search":
            return """
DIVERSIFY SEARCH STRATEGY:
- Search collections not yet fully explored (text, fiscal) with comprehensive terms
- Look for policy documents, implementation guidelines, background information
- Use broader contextual terms like 'policy framework', 'implementation guide'
- Build richer context around the main query topic
- Focus on getting good distribution across different document types"""

        elif action == "refine_terms":
            return """
REFINE TERMS STRATEGY:
- Use more specific, targeted search terms with exact phrase matching
- Try quoted exact phrases and AND combinations for precision
- Search for synonyms and more detailed/specific related concepts
- Focus on higher relevance scores rather than quantity
- Use specific and detailed variations of the query terms"""

        elif action == "cross_reference":
            return """
CROSS-REFERENCE STRATEGY:
- Search text and fiscal collections for policy context
- Look for implementation guidelines and background information
- Find supporting documentation that explains the budget items
- Build comprehensive understanding across document types"""

        elif action == "targeted_search":
            return """
TARGETED SEARCH STRATEGY:
- Focus on the specific budget collection with more precise terms
- Break down complex queries into individual components
- Search for specific program names and appropriation details
- Use exact matching for better relevance scores"""

        elif action == "expand_coverage":
            return """
EXPAND COVERAGE STRATEGY:
- Search the missing collections identified in the analysis
- Use comprehensive and overview-focused search terms
- Ensure all target collections are properly searched
- Focus on achieving better collection coverage and distribution
- Use broad but relevant terms to capture content from all target collections"""

        elif action == "comprehensive_search":
            return """
COMPREHENSIVE SEARCH STRATEGY:
- Perform thorough searches across all available collections
- Use detailed and comprehensive search terms
- Focus on gathering high-quality, detailed information
- Search with high num_results to ensure comprehensive coverage
- Use multiple variations of terms to capture all relevant content"""

        else:
            return """
GENERAL REFINEMENT STRATEGY:
- Use available tools strategically to improve result quality
- Focus on addressing the specific gaps identified in quality metrics
- Gather additional relevant information to support comprehensive analysis
- Use high num_results values to ensure thorough coverage"""
    
    def _save_query_debug(self, query: str, final_state: AgentState, response: Dict[str, Any]) -> str:
        """Save detailed debug information for the query to a JSON file"""
        try:
            # Create debug directory if it doesn't exist
            debug_dir = Path("debug_queries")
            debug_dir.mkdir(exist_ok=True)
            
            # Generate unique filename
            timestamp = int(time.time())
            query_id = str(uuid.uuid4())[:8]
            safe_query = "".join(c for c in query[:50] if c.isalnum() or c in (' ', '-', '_')).rstrip()
            filename = f"query_{timestamp}_{query_id}_{safe_query.replace(' ', '_')}.json"
            
            # Prepare detailed debug data
            debug_data = {
                "query_info": {
                    "original_query": query,
                    "timestamp": timestamp,
                    "query_id": query_id,
                    "processing_time": response.get("processing_time", "unknown")
                },
                "step_1_analysis": {
                    "reasoning": final_state["reasoning"],
                    "target_collections": final_state["reasoning"].get("target_collections", []),
                    "search_strategy": final_state["reasoning"].get("search_strategy", ""),
                    "search_terms": final_state["reasoning"].get("search_terms", [])
                },
                "step_2_search_iterations": {
                    "total_iterations": final_state["search_iterations"] + 1,
                    "max_iterations": final_state["max_iterations"],
                    "search_history": final_state["search_history"],
                    "final_collections_searched": final_state["collections_searched"],
                    "final_search_terms_used": final_state["search_terms_used"],
                    "total_documents_found": len(final_state["search_results"]),
                    "quality_scores": final_state["result_quality_scores"],
                    "refinement_strategy": final_state["refinement_strategy"],
                    "search_results_by_collection": {},
                    "detailed_search_results": []
                },
                "step_3_generation": {
                    "context_length": len(final_state["context"]),
                    "sources_count": len(final_state["sources"]),
                    "answer_length": len(final_state["answer"]),
                    "confidence": final_state["confidence"]
                },
                "full_context": final_state["context"],
                "final_answer": final_state["answer"],
                "sources": final_state["sources"],
                "processing_steps": [msg.content for msg in final_state["messages"] if isinstance(msg, AIMessage)]
            }
            
            # Organize search results by collection
            for result in final_state["search_results"]:
                collection = result.get("collection", "unknown")
                if collection not in debug_data["step_2_search_iterations"]["search_results_by_collection"]:
                    debug_data["step_2_search_iterations"]["search_results_by_collection"][collection] = []
                
                debug_data["step_2_search_iterations"]["search_results_by_collection"][collection].append({
                    "score": result.get("score"),
                    "content_preview": result["content"][:200] + "..." if len(result["content"]) > 200 else result["content"],
                    "content_length": len(result["content"]),
                    "metadata": result.get("metadata", {}),
                    "has_amount_data": any(key in result.get("metadata", {}) for key in ["amount", "appropriation", "budget", "funding", "cost"])
                })
                
                # Add to detailed results
                debug_data["step_2_search_iterations"]["detailed_search_results"].append({
                    "collection": collection,
                    "score": result.get("score"),
                    "full_content": result["content"],
                    "metadata": result.get("metadata", {})
                })
            
            # Save to file
            filepath = debug_dir / filename
            with open(filepath, 'w') as f:
                json.dump(debug_data, f, indent=2, default=str)
            
            print(f"💾 Debug file saved: {filepath}")
            return str(filepath)
            
        except Exception as e:
            print(f"❌ Error saving debug file: {e}")
            return ""
    
    def process_query(self, query: str, threshold: float = 0.5) -> Dict[str, Any]:
        """Process a query using the LangGraph agent"""
        
        start_time = time.time()
        
        # Initialize state
        initial_state = AgentState(
            messages=[],
            query=query,
            reasoning={},
            search_results=[],
            context="",
            answer="",
            sources=[],
            collections_searched=[],
            search_terms_used=[],
            confidence="medium",
            # Iterative search enhancements
            search_iterations=0,
            max_iterations=3,
            needs_refinement=False,
            refinement_strategy={},
            search_history=[],
            result_quality_scores={},
            web_results=[] # Initialize web_results
        )
        
        try:
            print(f"🤖 Starting LangGraph agent for query: '{query}'")
            
            # Run the workflow
            final_state = self.graph.invoke(initial_state)
            
            # Filter sources by threshold
            filtered_sources = [
                source for source in final_state["sources"]
                if source.get("score", 0.0) >= threshold
            ]
            
            processing_time = time.time() - start_time
            
            # Prepare response
            response = {
                "response": final_state["answer"],
                "sources": filtered_sources,
                "reasoning": final_state["reasoning"],
                "search_summary": {
                    "collections_searched": final_state["collections_searched"],
                    "search_terms_used": final_state["search_terms_used"],
                    "total_documents_found": len(final_state["search_results"]),
                    "documents_above_threshold": len(filtered_sources),
                    "threshold_used": threshold
                },
                "confidence": final_state["confidence"],
                "processing_steps": [msg.content for msg in final_state["messages"] if isinstance(msg, AIMessage)],
                "processing_time": f"{processing_time:.2f} seconds"
            }
            
            # Save debug file
            debug_file = self._save_query_debug(query, final_state, response)
            if debug_file:
                response["debug_file"] = debug_file
            
            print(f"🎯 Agent completed successfully")
            print(f"   Collections searched: {final_state['collections_searched']}")
            print(f"   Documents found: {len(final_state['search_results'])}")
            print(f"   Sources above threshold: {len(filtered_sources)}")
            print(f"   Processing time: {processing_time:.2f}s")
            
            return response
            
        except Exception as e:
            processing_time = time.time() - start_time
            print(f"❌ Error in agent workflow: {e}")
            error_response = {
                "response": f"I apologize, but I encountered an error while processing your query: {str(e)}",
                "sources": [],
                "reasoning": {"error": str(e)},
                "search_summary": {
                    "collections_searched": [],
                    "search_terms_used": [],
                    "total_documents_found": 0,
                    "documents_above_threshold": 0,
                    "threshold_used": threshold
                },
                "confidence": "low",
                "processing_steps": [f"Error: {str(e)}"],
                "processing_time": f"{processing_time:.2f} seconds"
            }
            
            # Try to save error debug info
            try:
                error_state = AgentState(
                    messages=[AIMessage(content=f"Error: {str(e)}")],
                    query=query,
                    reasoning={"error": str(e)},
                    search_results=[],
                    context="",
                    answer=error_response["response"],
                    sources=[],
                    collections_searched=[],
                    search_terms_used=[],
                    confidence="low",
                    # Iterative search enhancements
                    search_iterations=0,
                    max_iterations=3, # Default to 3 iterations
                    needs_refinement=False,
                    refinement_strategy={},
                    search_history=[],
                    result_quality_scores={},
                    web_results=[] # Ensure web_results is empty on error
                )
                debug_file = self._save_query_debug(query, error_state, error_response)
                if debug_file:
                    error_response["debug_file"] = debug_file
            except:
                pass
            
            return error_response 