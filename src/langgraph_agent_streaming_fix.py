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
        
        # Answer all subquestions using the workflow method
        state = self.answer_subquestions(state)
        
        # Yield completion for each subquestion
        for i, subquestion_data in enumerate(state["subquestions"]):
            subquestion_text = subquestion_data["question"]
            
            # Find the corresponding answer
            subquestion_answer = ""
            search_results_count = 0
            
            if i < len(state.get("subquestion_answers", [])):
                answer_data = state["subquestion_answers"][i]
                if isinstance(answer_data, dict):
                    subquestion_answer = answer_data.get("answer", "")
                else:
                    subquestion_answer = str(answer_data)
            
            # Count search results for this subquestion
            if i < len(state.get("subquestion_results", [])):
                search_results_count = len(state["subquestion_results"][i])
            
            yield {
                "type": "subquestion_completed",
                "subquestion": subquestion_text,
                "answer": subquestion_answer,
                "index": i,
                "search_results_count": search_results_count,
                "timestamp": datetime.now().isoformat()
            }
            time.sleep(0.3)  # Longer delay to allow frontend to process completed subquestion
        
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
