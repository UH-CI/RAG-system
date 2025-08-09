#!/usr/bin/env python3
"""
View Aggregate Evaluation Results

This script loads the 'aggregate_evaluation_results.csv' file and displays
the results in a sorted, readable format using pandas.

Usage: python view_results.py
"""
import pandas as pd
import os

def view_results(file_path: str):
    """
    Loads, sorts, and prints the aggregate evaluation results.
    """
    # Check if the file exists
    if not os.path.exists(file_path):
        print(f"Error: The file '{file_path}' was not found.")
        print("Please run the evaluation script first to generate the results.")
        return

    # Load the CSV file into a pandas DataFrame
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(f"Error loading CSV file: {e}")
        return

    # Set pandas display options for better readability
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 200)
    pd.set_option('display.colheader_justify', 'center')
    pd.set_option('display.precision', 4)

    print("\n" + "="*80)
    print("AGGREGATE EVALUATION RESULTS")
    print("="*80)
    
    # Sort by BERT F1 score (descending)
    if 'bert_f1_mean' in df.columns:
        print("\n--- Results Sorted by BERT F1 Score (Best to Worst) ---")
        sorted_by_bert = df.sort_values(by='bert_f1_mean', ascending=False)
        print(sorted_by_bert)
    else:
        print("\n'bert_f1_mean' column not found. Skipping sorting by BERT score.")

    # Sort by Gemini score (descending) if the column exists
    if 'gemini_score_mean' in df.columns:
        print("\n--- Results Sorted by Gemini Score (Best to Worst) ---")
        # Ensure we only sort if there are non-zero scores
        if df['gemini_score_mean'].sum() > 0:
            sorted_by_gemini = df.sort_values(by='gemini_score_mean', ascending=False)
            print(sorted_by_gemini)
        else:
            print("Gemini scores are all zero. Displaying unsorted results.")
            print(df)
            
    print("\n" + "="*80)
    print("Script finished.")

if __name__ == "__main__":
    # The script assumes it's in the same directory as the CSV file
    csv_file = './aggregate_evaluation_results.csv'
    view_results(csv_file) 