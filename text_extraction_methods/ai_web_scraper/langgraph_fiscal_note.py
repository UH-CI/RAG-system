"""
LangGraph Fiscal Note Generation Agent

This module implements an agentic AI system that systematically generates
comprehensive fiscal notes by processing each property using RAG (Retrieval
Augmented Generation) with ChromaDB and web tools.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, TypedDict
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor

from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.tools import DuckDuckGoSearchRun
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sentence_transformers import CrossEncoder

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class FiscalNoteOutput:
    """Complete fiscal note output structure"""
    overview: str = ""
    policy_impact: str = ""
    appropriations: str = ""
    assumptions_and_methodology: str = ""
    agency_impact: str = ""
    economic_impact: str = ""
    revenue_sources: str = ""
    six_year_fiscal_implications: str = ""
    fiscal_implications_after_6_years: str = ""
    operating_revenue_impact: str = ""
    capital_expenditure_impact: str = ""
    generated_at: str = ""
    confidence_scores: Dict[str, float] = None

    def __post_init__(self):
        if self.generated_at == "":
            self.generated_at = datetime.now().isoformat()
        if self.confidence_scores is None:
            self.confidence_scores = {}


class FiscalNoteState(TypedDict):
    """State for the fiscal note generation workflow"""
    query: str
    current_property: str
    fiscal_note: FiscalNoteOutput
    retrieved_documents: List[Dict[str, Any]]
    property_index: int
    total_properties: int
    rag_config: Dict[str, Any]
    errors: List[str]
    completed_properties: List[str]


class FiscalNoteRAGConfig:
    """Configuration for RAG retrieval parameters"""
    def __init__(
        self,
        top_n_per_collection: int = 5,
        rerank_top_k: int = 10,
        similarity_threshold: Optional[float] = None,
        use_web_search: bool = True,
        web_search_results: int = 3,
        google_api_key: str = None,
        chroma_persist_directory: str = "./chroma_db",
        embedding_model_name: str = "sentence-transformers/all-mpnet-base-v2",
        collection_names: List[str] = None
    ):
        self.top_n_per_collection = top_n_per_collection
        self.rerank_top_k = rerank_top_k
        self.similarity_threshold = similarity_threshold
        self.use_web_search = use_web_search
        self.web_search_results = web_search_results
        self.google_api_key = google_api_key
        self.chroma_persist_directory = chroma_persist_directory
        self.embedding_model_name = embedding_model_name
        self.collection_names = collection_names or ["HB727_chunks_500_200"]


class FiscalNoteAgent:
    """LangGraph-based agent for generating comprehensive fiscal notes"""
    
    # Property definitions with their corresponding prompts
    PROPERTY_PROMPTS = {
        "overview": {
            "prompt": "Using the provided legislative documents, statutes, and testimonies, write a clear summary describing the purpose, scope, and key components of the proposed measure or bill, including any pilot or permanent programs, reporting requirements, and sunset clauses. This should be around 3 sentences.",
            "description": "General overview and summary of the measure"
        },
        "appropriations": {
            "prompt": "Based on budgetary data and legislative appropriations, detail the funding allocated for the program or measure, including fiscal years, amounts, intended uses such as staffing, training, contracts, technology, etc... This should be around 3 sentences.",
            "description": "Funding allocation and appropriations details"
        },
        "assumptions_and_methodology": {
            "prompt": "Explain the assumptions, cost estimation methods, and data sources used to calculate the financial projections for this program or measure, referencing comparable programs or historical budgets where applicable. This should be around 3 sentences.",
            "description": "Cost estimation methodology and assumptions"
        },
        "agency_impact": {
            "prompt": "Describe the anticipated operational, administrative, and budgetary impact of the program or measure on the relevant government agency or department, including supervision, staffing, and resource allocation. This should be around 3 sentences.",
            "description": "Impact on government agencies and departments"
        },
        "economic_impact": {
            "prompt": "Summarize the expected economic effects of the program or measure, such as cost savings, potential reductions in related expenditures, benefits to the community, and any relevant performance or participation statistics. This should be around 3 sentences.",
            "description": "Economic effects and community benefits"
        },
        "policy_impact": {
            "prompt": "Analyze the policy implications of the measure, including how it modifies existing laws or programs, its role within broader legislative strategies, and its potential effects on state or local governance. This should be around 3 sentences.",
            "description": "Policy implications and legislative analysis"
        },
        "revenue_sources": {
            "prompt": "Identify and describe the funding sources that will support the program or measure, such as general funds, grants, fees, or other revenue streams, based on the provided fiscal documents. This should be around 3 sentences.",
            "description": "Funding sources and revenue streams"
        },
        "six_year_fiscal_implications": {
            "prompt": "Provide a multi-year fiscal outlook (e.g., six years) for the program or measure, projecting costs, staffing changes, recurring expenses, and assumptions about program expansion or permanence using available budget and workload data. This should be around 10 sentences.",
            "description": "Six-year fiscal projections and outlook"
        },
        "operating_revenue_impact": {
            "prompt": "Describe any anticipated impacts on operating revenues resulting from the program or measure, including increases, decreases, or changes in revenue streams. This should be around 3 sentences.",
            "description": "Operating revenue impacts"
        },
        "capital_expenditure_impact": {
            "prompt": "Outline any expected capital expenditures related to the program or measure, such as investments in facilities, equipment, or technology infrastructure, based on capital budgets or agency plans.    This should be around 3 sentences.",
            "description": "Capital expenditure requirements"
        },
        "fiscal_implications_after_6_years": {
            "prompt": "Summarize the ongoing fiscal obligations after the initial multi-year period for the program or measure, including annual operating costs, expected number of program sites or units, and the sustainability of funding. This should be around 3 sentences.",
            "description": "Long-term fiscal obligations beyond six years"
        }
    }
    
    def __init__(self, config: FiscalNoteRAGConfig):
        self.config = config
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0.1,
            google_api_key=config.google_api_key,
            convert_system_message_to_human=True
        )
        self.embeddings = HuggingFaceEmbeddings(model_name=config.embedding_model_name)
        self.reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
        self.web_search = DuckDuckGoSearchRun() if config.use_web_search else None
        
        # Initialize ChromaDB
        self.vectorstore = Chroma(
            persist_directory=config.chroma_persist_directory,
            embedding_function=self.embeddings
        )
        
        # Build the workflow graph
        self.workflow = self._build_workflow()
    
    def _build_workflow(self) -> StateGraph:
        """Build the LangGraph workflow for fiscal note generation"""
        workflow = StateGraph(FiscalNoteState)
        
        # Add nodes
        workflow.add_node("initialize", self._initialize_state)
        workflow.add_node("retrieve_documents", self._retrieve_documents)
        workflow.add_node("generate_property", self._generate_property)
        workflow.add_node("update_state", self._update_state)
        workflow.add_node("finalize", self._finalize_fiscal_note)
        
        # Add edges
        workflow.set_entry_point("initialize")
        workflow.add_edge("initialize", "retrieve_documents")
        workflow.add_edge("retrieve_documents", "generate_property")
        workflow.add_edge("generate_property", "update_state")
        
        # Conditional edge for continuing or finishing
        workflow.add_conditional_edges(
            "update_state",
            self._should_continue,
            {
                "continue": "retrieve_documents",
                "finish": "finalize"
            }
        )
        workflow.add_edge("finalize", END)
        
        return workflow.compile()
    
    def _initialize_state(self, state: FiscalNoteState) -> FiscalNoteState:
        """Initialize the workflow state"""
        logger.info("Initializing fiscal note generation workflow")
        
        property_names = list(self.PROPERTY_PROMPTS.keys())
        
        state.update({
            "current_property": property_names[0],
            "fiscal_note": FiscalNoteOutput(),
            "retrieved_documents": [],
            "property_index": 0,
            "total_properties": len(property_names),
            "rag_config": self.config,
            "errors": [],
            "completed_properties": []
        })
        
        return state
    
    def _retrieve_documents(self, state: FiscalNoteState) -> FiscalNoteState:
        """Retrieve relevant documents using RAG"""
        current_property = state["current_property"]
        query = state["query"]
        
        logger.info(f"Retrieving documents for property: {current_property}")
        
        try:
            # Create property-specific query
            property_info = self.PROPERTY_PROMPTS[current_property]
            enhanced_query = f"{query} {property_info['description']}"
            
            # Retrieve from all collections in ChromaDB
            all_documents = []
            
            # Use specified collection names
            logger.info(f"Using collections: {self.config.collection_names}")
            for collection_name in self.config.collection_names:
                try:
                    # Search in each specified collection
                    logger.info(f"Searching in collection: {collection_name}")
                    
                    # Configure Chroma client and collection
                    collection = self.vectorstore._client.get_collection(collection_name)
                    if not collection:
                        logger.warning(f"Collection {collection_name} not found, skipping")
                        continue
                        
                    # Create a specific vectorstore for this collection
                    collection_vectorstore = Chroma(
                        client=self.vectorstore._client,
                        collection_name=collection_name,
                        embedding_function=self.embeddings
                    )
                    
                    # Now search using this collection-specific vectorstore
                    collection_docs = collection_vectorstore.similarity_search_with_score(
                        enhanced_query,
                        k=self.config.top_n_per_collection
                    )
                    
                    # Apply similarity threshold if specified
                    if self.config.similarity_threshold is not None:
                        collection_docs = [
                            (doc, score) for doc, score in collection_docs
                            if score >= self.config.similarity_threshold
                        ]
                    
                    # Add collection info to documents
                    for doc, score in collection_docs:
                        doc_dict = {
                            "content": doc.page_content,
                            "metadata": doc.metadata,
                            "score": score,
                            "collection": collection.name if hasattr(collection, 'name') else "unknown"
                        }
                        all_documents.append(doc_dict)
                        
                except Exception as e:
                    logger.warning(f"Error retrieving from collection {collection}: {e}")
                    continue
            
            logger.info(f"Retrieved {len(all_documents)} documents for {current_property} \n\n")
            # Rerank documents if we have more than the target
            if len(all_documents) > self.config.rerank_top_k:
                logger.info(f"Reranking documents for {current_property} \n\n")
                all_documents = self._rerank_documents(enhanced_query, all_documents)
            
            # Add web search results if enabled
            if self.config.use_web_search and self.web_search:
                try:
                    web_query = f"Hawaii {enhanced_query} fiscal budget appropriations"
                    web_results = self.web_search.run(web_query)
                    
                    # Add web results as documents
                    web_doc = {
                        "content": web_results,
                        "metadata": {"source": "web_search", "query": web_query},
                        "score": 0.5,  # Default score for web results
                        "collection": "web_search"
                    }
                    all_documents.append(web_doc)
                    
                except Exception as e:
                    logger.warning(f"Web search failed: {e}")
            
            state["retrieved_documents"] = all_documents
            logger.info(f"Retrieved {len(all_documents)} documents for {current_property}")
            
        except Exception as e:
            error_msg = f"Error retrieving documents for {current_property}: {e}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            state["retrieved_documents"] = []
        
        return state
    
    def _rerank_documents(self, query: str, documents: List[Dict]) -> List[Dict]:
        """Rerank documents using cross-encoder"""
        try:
            # Prepare query-document pairs for reranking
            query_doc_pairs = [(query, doc["content"]) for doc in documents]
            
            # Get reranking scores
            rerank_scores = self.reranker.predict(query_doc_pairs)
            
            # Update documents with rerank scores and sort
            for i, doc in enumerate(documents):
                doc["rerank_score"] = float(rerank_scores[i])
            
            # Sort by rerank score and take top k
            documents.sort(key=lambda x: x["rerank_score"], reverse=True)
            return documents[:self.config.rerank_top_k]
            
        except Exception as e:
            logger.warning(f"Reranking failed: {e}. Using original order.")
            return documents[:self.config.rerank_top_k]
    
    def _generate_property(self, state: FiscalNoteState) -> FiscalNoteState:
        """Generate content for the current property"""
        current_property = state["current_property"]
        query = state["query"]
        documents = state["retrieved_documents"]
        
        logger.info(f"Generating content for property: {current_property}")
        
        try:
            # Get the prompt for this property
            property_info = self.PROPERTY_PROMPTS[current_property]
            property_prompt = property_info["prompt"]
            
            # Prepare previously generated content to avoid duplicates
            previously_generated_parts = []
            completed_properties = state.get("completed_properties", [])
            fiscal_note = state["fiscal_note"]

            for prop_name in completed_properties:
                content = getattr(fiscal_note, prop_name, "").strip()
                if content and not content.startswith("Error"):
                    prop_title = prop_name.replace('_', ' ').title()
                    previously_generated_parts.append(f"**{prop_title}**:\n{content}")
            
            previously_generated_section = ""
            if previously_generated_parts:
                joined_parts = "\n\n".join(previously_generated_parts)
                previously_generated_section = (
                    "Previously Generated Fiscal Note Content:\n"
                    f"{'-'*50}\n"
                    f"{joined_parts}\n"
                    f"{'-'*50}\n"
                )

            # Prepare context from retrieved documents
            # context_parts = []
            context_parts = []
            sources = set()
            for i, doc in enumerate(documents):
                source = doc['metadata'].get('source', 'Unknown')
                if source not in sources:
                    sources.add(source)
                    context_parts.append(
                        f"Document {i+1} (Collection: {doc['collection']}, Score: {doc.get('score', 'N/A')}):\n"
                        f"Source: {doc['metadata'].get('source', 'Unknown')}\n"
                        f"Content: {doc['metadata'].get('context', 'Unknown')}\n"
                    )
                            
            context = "\n" + "="*50 + "\n".join(context_parts)
            
            
            # Create the prompt
            system_prompt = f"""
You are an expert fiscal analyst specializing in Hawaii state government budgets and appropriations.
Your task is to analyze legislative documents and generate detailed fiscal note components.

Current Task: Generate content for the '{current_property}' section of a fiscal note.

Property Description: {property_info['description']}

Instructions:
1. Use ONLY the provided documents and context to answer
2. Be specific and detailed in your analysis
3. Include relevant numbers, dates, and financial figures when available
4. If information is insufficient, clearly state what is missing
5. Maintain professional, analytical tone appropriate for fiscal documentation
6. Focus specifically on Hawaii state government context
7. **Critically, you MUST NOT repeat information that is already present in the 'Previously Generated Fiscal Note Content'.** Your goal is to provide novel information specific to the current property. If the context for the current property is already well-covered in previous sections, you can be brief.

Property Prompt: {property_prompt}
"""
            
            user_prompt = f"""
Original Query: {query}

{previously_generated_section}
Retrieved Documents and Context:
{context}

Based on the above documents and the specific prompt for '{current_property}', provide a comprehensive analysis.
Ensure your response directly addresses the property prompt requirements and avoids duplicating content from previous sections.
"""
            
            # Generate response
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = self.llm.invoke(messages)
            generated_content = response.content
            
            # Calculate confidence score based on document relevance and completeness
            confidence_score = self._calculate_confidence_score(documents, generated_content)
            
            # Update the fiscal note with the generated content
            fiscal_note = state["fiscal_note"]
            setattr(fiscal_note, current_property, generated_content)
            fiscal_note.confidence_scores[current_property] = confidence_score
            
            state["fiscal_note"] = fiscal_note
            
            logger.info(f"Generated content for {current_property} (confidence: {confidence_score:.2f})")
            
        except Exception as e:
            error_msg = f"Error generating content for {current_property}: {e}"
            logger.error(error_msg)
            state["errors"].append(error_msg)
            
            # Set empty content for this property
            fiscal_note = state["fiscal_note"]
            setattr(fiscal_note, current_property, f"Error generating content: {e}")
            fiscal_note.confidence_scores[current_property] = 0.0
            state["fiscal_note"] = fiscal_note
        
        return state
    
    def _calculate_confidence_score(self, documents: List[Dict], generated_content: str) -> float:
        """Calculate confidence score based on document quality and content completeness"""
        try:
            # Base score from document relevance
            if not documents:
                return 0.1
            
            # Average document scores
            doc_scores = [doc.get("rerank_score", doc.get("score", 0.5)) for doc in documents]
            avg_doc_score = sum(doc_scores) / len(doc_scores) if doc_scores else 0.5
            
            # Content completeness score (based on length and detail)
            content_length = len(generated_content)
            length_score = min(content_length / 500, 1.0)  # Normalize to 500 chars
            
            # Keyword relevance (check for fiscal/budget terms)
            fiscal_keywords = [
                "budget", "appropriation", "funding", "cost", "revenue", "expenditure",
                "fiscal", "financial", "allocation", "investment", "savings"
            ]
            keyword_matches = sum(1 for keyword in fiscal_keywords if keyword.lower() in generated_content.lower())
            keyword_score = min(keyword_matches / len(fiscal_keywords), 1.0)
            
            # Combine scores with weights
            confidence = (
                avg_doc_score * 0.4 +
                length_score * 0.3 +
                keyword_score * 0.3
            )
            
            return min(max(confidence, 0.0), 1.0)  # Clamp between 0 and 1
            
        except Exception as e:
            logger.warning(f"Error calculating confidence score: {e}")
            return 0.5
    
    def _update_state(self, state: FiscalNoteState) -> FiscalNoteState:
        """Update state after processing a property"""
        current_property = state["current_property"]
        state["completed_properties"].append(current_property)
        state["property_index"] += 1
        
        # Set next property if available
        property_names = list(self.PROPERTY_PROMPTS.keys())
        if state["property_index"] < len(property_names):
            state["current_property"] = property_names[state["property_index"]]
        
        logger.info(f"Completed {current_property}. Progress: {state['property_index']}/{state['total_properties']}")
        
        return state
    
    def _should_continue(self, state: FiscalNoteState) -> str:
        """Determine whether to continue processing or finish"""
        if state["property_index"] >= state["total_properties"]:
            return "finish"
        return "continue"
    
    def _finalize_fiscal_note(self, state: FiscalNoteState) -> FiscalNoteState:
        """Finalize the fiscal note generation"""
        logger.info("Finalizing fiscal note generation")
        
        fiscal_note = state["fiscal_note"]
        
        # Calculate overall confidence score
        if fiscal_note.confidence_scores:
            overall_confidence = sum(fiscal_note.confidence_scores.values()) / len(fiscal_note.confidence_scores)
            fiscal_note.confidence_scores["overall"] = overall_confidence
        
        # Log completion summary
        completed_count = len(state["completed_properties"])
        error_count = len(state["errors"])
        
        logger.info(f"Fiscal note generation completed:")
        logger.info(f"  - Properties completed: {completed_count}/{state['total_properties']}")
        logger.info(f"  - Errors encountered: {error_count}")
        logger.info(f"  - Overall confidence: {fiscal_note.confidence_scores.get('overall', 0):.2f}")
        
        if state["errors"]:
            logger.warning(f"Errors during generation: {state['errors']}")
        
        state["fiscal_note"] = fiscal_note
        return state
    
    async def generate_fiscal_note(
        self,
        query: str,
        top_n_per_collection: Optional[int] = None,
        rerank_top_k: Optional[int] = None,
        similarity_threshold: Optional[float] = None
    ) -> FiscalNoteOutput:
        """
        Generate a comprehensive fiscal note using the agentic workflow
        
        Args:
            query: The main query/bill description to analyze
            top_n_per_collection: Override for number of docs per collection
            rerank_top_k: Override for reranking top k
            similarity_threshold: Override for similarity threshold
            
        Returns:
            FiscalNoteOutput: Complete fiscal note with all properties
        """
        # Update config with any overrides
        if top_n_per_collection is not None:
            self.config.top_n_per_collection = top_n_per_collection
        if rerank_top_k is not None:
            self.config.rerank_top_k = rerank_top_k
        if similarity_threshold is not None:
            self.config.similarity_threshold = similarity_threshold
        
        # Initialize state
        initial_state = FiscalNoteState(
            query=query,
            current_property="",
            fiscal_note=FiscalNoteOutput(),
            retrieved_documents=[],
            property_index=0,
            total_properties=0,
            rag_config={},
            errors=[],
            completed_properties=[]
        )
        
        # Run the workflow with increased recursion limit
        logger.info(f"Starting fiscal note generation for query: {query}")
        config = {"recursion_limit": 50}
        final_state = await self.workflow.ainvoke(initial_state, config=config)
        
        return final_state["fiscal_note"]
    
    def generate_fiscal_note_sync(
        self,
        query: str,
        top_n_per_collection: Optional[int] = None,
        rerank_top_k: Optional[int] = None,
        similarity_threshold: Optional[float] = None
    ) -> FiscalNoteOutput:
        """
        Synchronous version of fiscal note generation
        
        Args:
            query: The main query/bill description to analyze
            top_n_per_collection: Override for number of docs per collection
            rerank_top_k: Override for reranking top k
            similarity_threshold: Override for similarity threshold
            
        Returns:
            FiscalNoteOutput: Complete fiscal note with all properties
        """
        return asyncio.run(self.generate_fiscal_note(
            query, top_n_per_collection, rerank_top_k, similarity_threshold
        ))


# Convenience function for easy usage
def create_fiscal_note_agent(
    google_api_key: str,
    chroma_persist_directory: str = "./chroma_db",
    top_n_per_collection: int = 5,
    rerank_top_k: int = 10,
    similarity_threshold: Optional[float] = None,
    use_web_search: bool = True,
    embedding_model_name: str = "sentence-transformers/all-mpnet-base-v2",
    collection_names: List[str] = None
) -> FiscalNoteAgent:
    """
    Create a configured fiscal note agent
    
    Args:
        google_api_key: Google API key for Gemini access
        chroma_persist_directory: Path to ChromaDB persistence directory
        top_n_per_collection: Number of documents to retrieve per collection
        rerank_top_k: Number of documents to keep after reranking
        similarity_threshold: Minimum similarity threshold (None to disable)
        use_web_search: Whether to include web search results
        embedding_model_name: HuggingFace model to use for embeddings
        
    Returns:
        FiscalNoteAgent: Configured agent ready for fiscal note generation
    """
    config = FiscalNoteRAGConfig(
        top_n_per_collection=top_n_per_collection,
        rerank_top_k=rerank_top_k,
        similarity_threshold=similarity_threshold,
        use_web_search=use_web_search,
        google_api_key=google_api_key,
        chroma_persist_directory=chroma_persist_directory,
        embedding_model_name=embedding_model_name,
        collection_names=collection_names
    )
    
    return FiscalNoteAgent(config)


# Example usage
if __name__ == "__main__":
    import os
    
    # Example configuration
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("Please set GOOGLE_API_KEY environment variable")

    n_collections = [30]
    rerank_top_ks = [30]

    for n_collection in n_collections:
        for rerank_top_k in rerank_top_ks:
            print(f"Running with n_collection={n_collection} and rerank_top_k={rerank_top_k}")
            agent = create_fiscal_note_agent(
                google_api_key=api_key,
                chroma_persist_directory="./chroma_db",
                top_n_per_collection=n_collection,
                rerank_top_k=rerank_top_k,
                similarity_threshold=0,
                use_web_search=True,
                embedding_model_name="sentence-transformers/all-mpnet-base-v2",
                collection_names=["HB400_chunks_500_200"]  # Specify collection to use
            )
            

    
            # Example query
            query = """
            Create a fiscal note with the following information
            """
    
            try:
                # Generate fiscal note
                fiscal_note = agent.generate_fiscal_note_sync(query)
                
                # Convert to dictionary for JSON serialization
                result = asdict(fiscal_note)
                
                # Print results
                print("\n" + "="*80)
                print("FISCAL NOTE GENERATION COMPLETED")
                print("="*80)
                
                for property_name, content in result.items():
                    if property_name not in ["generated_at", "confidence_scores"]:
                        print(f"\n{property_name.upper().replace('_', ' ')}:")
                        print("-" * 50)
                        print(content)
                
                print(f"\nGenerated at: {result['generated_at']}")
                print(f"Confidence Scores: {result['confidence_scores']}")
                
                # Save to file
                output_file = f"fiscal_note_{datetime.now().strftime('%Y%m%d_%H%M%S')}_n{n_collection}_rerank_k{rerank_top_k}_all_documents.json"
                with open(output_file, 'w') as f:
                    json.dump(result, f, indent=2)
                
                print(f"\nFiscal note saved to: {output_file}")
                
            except Exception as e:
                logger.error(f"Error generating fiscal note: {e}")
                raise