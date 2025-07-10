#!/usr/bin/env python3
"""
Fix the JSON structure of the existing cleaned file
"""

import json
import os

def fix_json_structure(input_file: str):
    """Fix the nested JSON structure in the cleaned file."""
    
    print(f"🔧 Fixing JSON structure in: {input_file}")
    
    # Read the malformed JSON
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Extract the nested JSON from cleaned_text
    cleaned_text_content = data.get('cleaned_text', '')
    
    if cleaned_text_content.startswith('\n{'):
        # Remove leading newline and parse the JSON
        try:
            # Find the complete JSON structure
            json_start = cleaned_text_content.find('{')
            if json_start != -1:
                json_content = cleaned_text_content[json_start:]
                
                # The JSON might be truncated, so let's try to extract what we can
                try:
                    # First, try to parse the complete JSON if it's valid
                    nested_data = json.loads(json_content)
                except json.JSONDecodeError:
                    # If that fails, try to find the end manually
                    brace_count = 0
                    json_end = 0
                    in_string = False
                    escape_next = False
                    
                    for i, char in enumerate(json_content):
                        if escape_next:
                            escape_next = False
                            continue
                        
                        if char == '\\':
                            escape_next = True
                            continue
                        
                        if char == '"' and not escape_next:
                            in_string = not in_string
                            continue
                        
                        if not in_string:
                            if char == '{':
                                brace_count += 1
                            elif char == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    json_end = i + 1
                                    break
                    
                    if json_end > 0:
                        clean_json_str = json_content[:json_end]
                        nested_data = json.loads(clean_json_str)
                    else:
                        print("❌ Could not find complete JSON structure")
                        return None
                
                # Extract the components
                actual_cleaned_text = nested_data.get('cleaned_text', '')
                budget_items = nested_data.get('budget_items', [])
                summary = nested_data.get('summary', {"total_items": 0, "total_amount": 0, "departments": []})
                
                # Calculate proper summary
                departments = list(set([item.get('department', '') for item in budget_items if item.get('department')]))
                total_amount = sum([item.get('amount', 0) for item in budget_items])
                
                # Create the corrected structure
                corrected_data = {
                    "source_file": data.get('source_file', ''),
                    "pages_processed": data.get('pages_processed', 0),
                    "cleaned_text": actual_cleaned_text,
                    "budget_items": budget_items,
                    "summary": {
                        "total_items": len(budget_items),
                        "total_amount": total_amount,
                        "departments": departments
                    }
                }
                
                # Save the corrected file
                output_file = input_file.replace('.json', '_fixed.json')
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(corrected_data, f, indent=2, ensure_ascii=False)
                
                print(f"✅ Fixed JSON structure!")
                print(f"   📊 Extracted {len(budget_items)} budget items")
                print(f"   🏛️  Found {len(departments)} departments: {', '.join(departments[:3])}{'...' if len(departments) > 3 else ''}")
                print(f"   💰 Total amount: ${total_amount:,.2f}")
                print(f"   📁 Saved to: {output_file}")
                
                return corrected_data
                
        except Exception as e:
            print(f"❌ Error parsing nested JSON: {e}")
            return None
    
    print("⚠️  No nested JSON structure found in cleaned_text")
    return None

if __name__ == "__main__":
    input_file = "cleaned_output/HB300__hybrid_extraction_first_10_pages_structured.json"
    if os.path.exists(input_file):
        fix_json_structure(input_file)
    else:
        print(f"❌ File not found: {input_file}") 