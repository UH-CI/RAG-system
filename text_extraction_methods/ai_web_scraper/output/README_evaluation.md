# Fiscal Note Evaluation

This directory contains an evaluation script that compares the `gold_standard.json` to all generated fiscal note JSON files using multiple evaluation metrics.

## Metrics Used

1. **BERTScore**: Evaluates semantic similarity using BERT embeddings (precision, recall, F1)
2. **MoverScore** (optional, requires CUDA): Word mover distance-based semantic similarity 
3. **ROUGE**: Traditional n-gram overlap metrics (ROUGE-1, ROUGE-2, ROUGE-L)
4. **Sentence Embedding Cosine Similarity**: Custom methodology where for each sentence in paragraph A, we compute cosine similarity to all sentences in paragraph B, take the maximum, then average those max scores
5. **Gemini LLM Scoring**: Uses Google's Gemini model to evaluate the quality of generated fiscal notes on a scale of 1-10

## Setup

1. Install required packages:
```bash
pip install -r requirements_evaluation.txt
```

2. Ensure you have the gold standard file in the parent directory:
```
ai_web_scraper/
├── gold_standard.json
└── output/
    ├── evaluate_fiscal_notes.py
    ├── fiscal_note_*.json
    └── ...
```

3. For Gemini LLM scoring (optional):
   - Get a Google AI API key from https://ai.google.dev/
   - You can provide your API key in three ways:
     - Set an environment variable: `export GEMINI_API_KEY=your_api_key`
     - Enter it when prompted during script execution
     - Pass it directly when running the script with `-k` flag

4. Note about MoverScore:
   - MoverScore requires PyTorch with CUDA support
   - If you don't have a GPU or CUDA enabled, the script will automatically skip MoverScore evaluation
   - All other metrics will still work without CUDA

## Usage

Run the evaluation script:
```bash
cd text_extraction_methods/ai_web_scraper/output
python evaluate_fiscal_notes.py
```

If you don't provide a Gemini API key, the script will still run but will skip the LLM evaluation component.

## Output

The script will generate:

1. **detailed_evaluation_results.csv**: Field-by-field scores for each file and metric
2. **aggregate_evaluation_results.csv**: Overall scores per file (means and standard deviations)
3. **gemini_evaluation_results.csv**: Detailed Gemini scores and explanations (if Gemini API is available)
4. **Console output**: Summary statistics including best/worst performing files

## Gemini LLM Evaluation

The Gemini evaluation:
- Rates each field on a scale from 1-10
- Provides explanations for scores
- Considers factual correctness, completeness, and preservation of key details
- 1 = Completely incorrect or missing critical information
- 5 = Partially correct with some missing details
- 10 = Perfect match to gold standard

## Fields Evaluated

The script evaluates the following fields from each JSON file:
- overview
- appropriations  
- assumptions_and_methodology
- fiscal_table
- agency_impact
- economic_impact
- policy_impact
- revenue_sources
- six_year_fiscal_implications
- operating_revenue_impact
- capital_expenditure_impact
- fiscal_implications_afer_6_years

## Interpretation

- **Higher scores = better performance** for all metrics
- **BERTScore F1** is generally the most reliable overall metric
- **Sentence embedding similarity** provides insights into semantic coherence
- **ROUGE scores** measure traditional n-gram overlap
- **MoverScore** captures semantic similarity with word movement (if available)
- **Gemini score** provides a human-like evaluation of quality and correctness

The script will identify the best and worst performing files based on BERTScore F1 and Gemini scores and provide detailed breakdowns by field. 