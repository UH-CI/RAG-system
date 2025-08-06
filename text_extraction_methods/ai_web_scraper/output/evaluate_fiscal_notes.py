#!/usr/bin/env python3
"""
Fiscal Note Evaluation Script

This script compares the gold_standard.json to all generated fiscal note JSON files
using multiple evaluation metrics:
- BERTScore
- MoverScore (optional, requires CUDA)
- ROUGE (1, 2, L)
- Sentence embedding cosine similarity
- Gemini LLM scoring (1-10 scale)

Usage: python evaluate_fiscal_notes.py
"""

import json
import os
import glob
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Any
import warnings
import time
warnings.filterwarnings('ignore')

# Required imports
try:
    from bert_score import score as bert_score
    from rouge_score import rouge_scorer
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    import nltk
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
    import google.generativeai as genai
    
    # Try to import MoverScore (optional)
    MOVERSCORE_AVAILABLE = False
    try:
        from moverscore_v2 import get_idf_dict, word_mover_score
        MOVERSCORE_AVAILABLE = True
        print("MoverScore is available and will be used for evaluation")
    except (ImportError, AssertionError) as e:
        print(f"MoverScore is not available (this is OK): {e}")
        print("Evaluation will continue without MoverScore")
except ImportError as e:
    print(f"Missing required packages. Please install with:")
    print("pip install bert-score rouge-score sentence-transformers scikit-learn nltk google-generativeai")
    raise e

class FiscalNoteEvaluator:
    def __init__(self, gemini_api_key: Optional[str] = None):
        self.sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.rouge_scorer = rouge_scorer.RougeScorer(['rouge1', 'rouge2', 'rougeL'], use_stemmer=True)
        
        # Initialize Gemini if API key is provided
        self.gemini_available = False
        if gemini_api_key:
            try:
                genai.configure(api_key=gemini_api_key)
                self.gemini_model = genai.GenerativeModel('gemini-2.5-pro')
                self.gemini_available = True
                print("Gemini API initialized successfully")
            except Exception as e:
                print(f"Warning: Could not initialize Gemini API: {e}")
        else:
            print("Warning: No Gemini API key provided. LLM evaluation will be skipped.")
        
        # Fields to evaluate (excluding metadata fields)
        self.eval_fields = [
            'overview', 'appropriations', 'assumptions_and_methodology', 'agency_impact', 'economic_impact', 'policy_impact',
            'revenue_sources', 'six_year_fiscal_implications', 'fiscal_implications_afer_6_years'
        ]
         
    def load_json_files(self, directory: str) -> Tuple[Dict, List[Dict]]:
        """Load gold standard and all output JSON files"""
        # Load gold standard
        gold_path = os.path.join(os.path.dirname(directory), 'gold_standard.json')
        with open(gold_path, 'r') as f:
            gold_standard = json.load(f)
            
        # Load all output files
        output_files = glob.glob(os.path.join(directory, 'fiscal_note_*.json'))
        outputs = []
        
        for file_path in output_files:
            with open(file_path, 'r') as f:
                data = json.load(f)
                data['filename'] = os.path.basename(file_path)
                outputs.append(data)
                
        return gold_standard, outputs
    
    def preprocess_text(self, text: str) -> str:
        """Clean and preprocess text for evaluation"""
        if not text or text.strip() == "":
            return ""
        return text.strip()
    
    def sentence_embedding_similarity(self, text1: str, text2: str) -> float:
        """
        Compute sentence embedding cosine similarity using the specified methodology:
        For each sentence in paragraph A, compute cosine similarity to all sentences 
        in paragraph B, and take the maximum. Then average those max scores.
        """
        if not text1 or not text2:
            return 0.0
            
        # Split into sentences
        sentences1 = nltk.sent_tokenize(text1)
        sentences2 = nltk.sent_tokenize(text2)
        
        if not sentences1 or not sentences2:
            return 0.0
            
        # Get embeddings
        embeddings1 = self.sentence_model.encode(sentences1)
        embeddings2 = self.sentence_model.encode(sentences2)
        
        # For each sentence in text1, find max similarity with sentences in text2
        max_similarities = []
        for emb1 in embeddings1:
            similarities = cosine_similarity([emb1], embeddings2)[0]
            max_similarities.append(np.max(similarities))
            
        return np.mean(max_similarities)
    
    def compute_bert_score(self, reference: str, candidate: str) -> Dict[str, float]:
        """Compute BERTScore"""
        if not reference or not candidate:
            return {'precision': 0.0, 'recall': 0.0, 'f1': 0.0}
            
        P, R, F1 = bert_score([candidate], [reference], lang='en', verbose=False)
        return {
            'precision': P[0].item(),
            'recall': R[0].item(), 
            'f1': F1[0].item()
        }
    
    def compute_mover_score(self, reference: str, candidate: str) -> float:
        """Compute MoverScore if available, otherwise return 0"""
        if not MOVERSCORE_AVAILABLE:
            return 0.0
            
        if not reference or not candidate:
            return 0.0
            
        try:
            # Create IDF dictionary (using a simple approach for this evaluation)
            idf_dict_hyp = get_idf_dict([candidate])
            idf_dict_ref = get_idf_dict([reference])
            
            score = word_mover_score([reference], [candidate], idf_dict_ref, idf_dict_hyp, 
                                   stop_words=[], n_gram=1, remove_subwords=False)
            return score[0] if score else 0.0
        except Exception as e:
            print(f"MoverScore computation failed: {e}")
            return 0.0
    
    def compute_rouge_scores(self, reference: str, candidate: str) -> Dict[str, float]:
        """Compute ROUGE scores"""
        if not reference or not candidate:
            return {'rouge1': 0.0, 'rouge2': 0.0, 'rougeL': 0.0}
            
        scores = self.rouge_scorer.score(reference, candidate)
        return {
            'rouge1': scores['rouge1'].fmeasure,
            'rouge2': scores['rouge2'].fmeasure,
            'rougeL': scores['rougeL'].fmeasure
        }
        
    def generate_gemini_prompt(self, field_name: str, gold_text: str, candidate_text: str) -> str:
        """Generate a prompt for Gemini to evaluate the generated text"""
        return f"""
You are an expert evaluator for fiscal note documents. Your task is to compare a gold standard reference text to a machine-generated candidate text and rate the quality of the candidate on a scale of 1-10.

For this evaluation:
1 = Completely incorrect, missing critical information, or contradicting the reference
5 = Partially correct with some key points but missing important details or contains inaccuracies
10 = Perfectly captures all information and nuance from the reference

Field being evaluated: {field_name}

GOLD STANDARD TEXT:
{gold_text}

CANDIDATE TEXT:
{candidate_text}

Please evaluate how well the candidate text captures the information from the gold standard text.
Focus on factual correctness, completeness, and preservation of key details.

Provide your evaluation as a single number between 1 and 10, followed by a brief explanation.
First line should be just the numerical score, then on separate lines provide your reasoning.
"""

    def compute_gemini_score(self, field_name: str, gold_text: str, candidate_text: str) -> Dict[str, Any]:
        """Compute a score from 1-10 using Gemini"""
        if not self.gemini_available:
            return {'gemini_score': 0, 'gemini_explanation': "Gemini API not available"}
            
        if not gold_text or not candidate_text:
            return {'gemini_score': 0, 'gemini_explanation': "Missing text"}
            
        # Generate prompt
        prompt = self.generate_gemini_prompt(field_name, gold_text, candidate_text)
        
        try:
            # Call Gemini API
            response = self.gemini_model.generate_content(prompt)
            result = response.text
            
            # Extract the score (first line should be just the number)
            lines = result.strip().split('\n')
            
            try:
                score = float(lines[0])
                # Ensure score is between 1 and 10
                score = max(1, min(10, score))
                explanation = '\n'.join(lines[1:]) if len(lines) > 1 else "No explanation provided"
            except (ValueError, IndexError):
                # If we can't extract a clean score, search for a number in the text
                import re
                score_matches = re.findall(r'(\d+(?:\.\d+)?)\s*\/\s*10|\b(\d+(?:\.\d+)?)\b', result)
                flattened_matches = [match for group in score_matches for match in group if match]
                
                if flattened_matches:
                    try:
                        score = float(flattened_matches[0])
                        # Ensure score is between 1 and 10
                        score = max(1, min(10, score))
                    except ValueError:
                        score = 0
                else:
                    score = 0
                    
                explanation = result
            
            # Add a small delay to avoid rate limiting
            time.sleep(0.5)
            
            return {'gemini_score': score, 'gemini_explanation': explanation}
        except Exception as e:
            print(f"Gemini evaluation failed: {e}")
            return {'gemini_score': 0, 'gemini_explanation': f"Error: {str(e)}"}
    
    def evaluate_field(self, gold_text: str, candidate_text: str, field_name: str) -> Dict:
        """Evaluate a single field with all metrics"""
        gold_text = self.preprocess_text(gold_text)
        candidate_text = self.preprocess_text(candidate_text)
        
        results = {
            'field': field_name,
            'gold_length': len(gold_text),
            'candidate_length': len(candidate_text)
        }
        
        # BERTScore
        bert_scores = self.compute_bert_score(gold_text, candidate_text)
        results.update({f'bert_{k}': v for k, v in bert_scores.items()})
        
        # MoverScore (if available)
        results['mover_score'] = self.compute_mover_score(gold_text, candidate_text)
        
        # ROUGE scores
        rouge_scores = self.compute_rouge_scores(gold_text, candidate_text)
        results.update(rouge_scores)
        
        # Sentence embedding similarity
        results['sentence_embedding_sim'] = self.sentence_embedding_similarity(gold_text, candidate_text)
        
        # Gemini evaluation (if available)
        if self.gemini_available:
            gemini_results = self.compute_gemini_score(field_name, gold_text, candidate_text)
            results.update(gemini_results)
        
        return results
    
    def evaluate_file(self, gold_standard: Dict, output_file: Dict) -> Dict:
        """Evaluate all fields for a single output file"""
        filename = output_file.get('filename', 'unknown')
        results = {'filename': filename, 'field_scores': []}
        
        field_scores = []
        for field in self.eval_fields:
            gold_text = gold_standard.get(field, "")
            candidate_text = output_file.get(field, "")
            
            field_result = self.evaluate_field(gold_text, candidate_text, field)
            field_scores.append(field_result)
        
        results['field_scores'] = field_scores
        
        # Compute aggregate scores
        results['aggregate_scores'] = self.compute_aggregate_scores(field_scores)
        
        return results
    
    def compute_aggregate_scores(self, field_scores: List[Dict]) -> Dict:
        """Compute aggregate scores across all fields"""
        metrics = ['bert_precision', 'bert_recall', 'bert_f1', 'rouge1', 'rouge2', 
                  'rougeL', 'sentence_embedding_sim']
        
        # Only include MoverScore if it's available
        if MOVERSCORE_AVAILABLE:
            metrics.append('mover_score')
            
        if self.gemini_available:
            metrics.append('gemini_score')
        
        aggregates = {}
        for metric in metrics:
            scores = [fs[metric] for fs in field_scores if metric in fs]
            if scores:
                aggregates[f'{metric}_mean'] = np.mean(scores)
                aggregates[f'{metric}_std'] = np.std(scores)
            else:
                aggregates[f'{metric}_mean'] = 0.0
                aggregates[f'{metric}_std'] = 0.0
                
        return aggregates
    
    def save_detailed_results(self, all_results: List[Dict], output_dir: str):
        """Save detailed results to CSV files"""
        # Prepare data for CSV
        rows = []
        for file_result in all_results:
            filename = file_result['filename']
            for field_score in file_result['field_scores']:
                row = {'filename': filename}
                row.update(field_score)
                rows.append(row)
        
        # Save detailed field-by-field results
        df_detailed = pd.DataFrame(rows)
        detailed_path = os.path.join(output_dir, 'detailed_evaluation_results.csv')
        df_detailed.to_csv(detailed_path, index=False)
        print(f"Detailed results saved to: {detailed_path}")
        
        # Save aggregate results
        aggregate_rows = []
        for file_result in all_results:
            row = {'filename': file_result['filename']}
            row.update(file_result['aggregate_scores'])
            aggregate_rows.append(row)
            
        df_aggregate = pd.DataFrame(aggregate_rows)
        aggregate_path = os.path.join(output_dir, 'aggregate_evaluation_results.csv')
        df_aggregate.to_csv(aggregate_path, index=False)
        print(f"Aggregate results saved to: {aggregate_path}")
        
        # Save Gemini explanations if available
        if self.gemini_available:
            gemini_rows = []
            for file_result in all_results:
                filename = file_result['filename']
                for field_score in file_result['field_scores']:
                    if 'gemini_explanation' in field_score:
                        gemini_rows.append({
                            'filename': filename,
                            'field': field_score['field'],
                            'gemini_score': field_score.get('gemini_score', 0),
                            'gemini_explanation': field_score.get('gemini_explanation', '')
                        })
            
            if gemini_rows:
                df_gemini = pd.DataFrame(gemini_rows)
                gemini_path = os.path.join(output_dir, 'gemini_evaluation_results.csv')
                df_gemini.to_csv(gemini_path, index=False)
                print(f"Gemini explanations saved to: {gemini_path}")
        
        return df_detailed, df_aggregate
    
    def print_summary(self, df_aggregate: pd.DataFrame):
        """Print a summary of results"""
        print("\n" + "="*80)
        print("EVALUATION SUMMARY")
        print("="*80)
        
        metrics = ['bert_f1_mean', 'rouge1_mean', 'rouge2_mean', 
                  'rougeL_mean', 'sentence_embedding_sim_mean']
        
        # Only include MoverScore if it's available
        if MOVERSCORE_AVAILABLE and 'mover_score_mean' in df_aggregate.columns:
            metrics.append('mover_score_mean')
            
        if 'gemini_score_mean' in df_aggregate.columns:
            metrics.append('gemini_score_mean')
        
        print(f"\nNumber of files evaluated: {len(df_aggregate)}")
        print(f"Number of fields per file: {len(self.eval_fields)}")
        
        print("\nAVERAGE SCORES ACROSS ALL FILES:")
        print("-" * 50)
        for metric in metrics:
            if metric in df_aggregate.columns:
                mean_score = df_aggregate[metric].mean()
                std_score = df_aggregate[metric].std()
                print(f"{metric:25s}: {mean_score:.4f} (±{std_score:.4f})")
        
        print("\nBEST PERFORMING FILE:")
        print("-" * 30)
        best_idx = df_aggregate['bert_f1_mean'].idxmax()
        best_file = df_aggregate.iloc[best_idx]
        print(f"File: {best_file['filename']}")
        for metric in metrics:
            if metric in df_aggregate.columns:
                print(f"{metric:25s}: {best_file[metric]:.4f}")
        
        print("\nWORST PERFORMING FILE:")
        print("-" * 30)
        worst_idx = df_aggregate['bert_f1_mean'].idxmin()
        worst_file = df_aggregate.iloc[worst_idx]
        print(f"File: {worst_file['filename']}")
        for metric in metrics:
            if metric in df_aggregate.columns:
                print(f"{metric:25s}: {worst_file[metric]:.4f}")
                
        if 'gemini_score_mean' in df_aggregate.columns:
            print("\nBEST FILE BY GEMINI SCORE:")
            best_gemini_idx = df_aggregate['gemini_score_mean'].idxmax()
            best_gemini_file = df_aggregate.iloc[best_gemini_idx]
            print(f"File: {best_gemini_file['filename']}")
            for metric in metrics:
                if metric in df_aggregate.columns:
                    print(f"{metric:25s}: {best_gemini_file[metric]:.4f}")

def main():
    """Main evaluation function"""
    # Set up paths
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    print("Starting Fiscal Note Evaluation...")
    print(f"Working directory: {current_dir}")
    
    # Get Gemini API key from environment variable or prompt user
    gemini_api_key = os.environ.get('GOOGLE_API_KEY')
    if not gemini_api_key:
        try:
            gemini_api_key = input("Enter your Gemini API key (press Enter to skip LLM evaluation): ").strip()
        except:
            gemini_api_key = None
    
    # Initialize evaluator
    evaluator = FiscalNoteEvaluator(gemini_api_key)
    
    # Load data
    print("Loading JSON files...")
    gold_standard, output_files = evaluator.load_json_files(current_dir)
    print(f"Loaded gold standard and {len(output_files)} output files")
    
    # Evaluate all files
    print("Running evaluation metrics...")
    all_results = []
    
    for i, output_file in enumerate(output_files):
        print(f"Evaluating file {i+1}/{len(output_files)}: {output_file['filename']}")
        result = evaluator.evaluate_file(gold_standard, output_file)
        all_results.append(result)
    
    # Save and display results
    print("Saving results...")
    df_detailed, df_aggregate = evaluator.save_detailed_results(all_results, current_dir)
    
    # Print summary
    evaluator.print_summary(df_aggregate)
    
    print(f"\nEvaluation complete! Check the output directory for detailed results.")

if __name__ == "__main__":
    main() 