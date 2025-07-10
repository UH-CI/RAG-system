#!/usr/bin/env python3
"""
Extract budget items from the truncated JSON response
"""

import json
import re
import os

def extract_budget_items_from_truncated_json(input_file: str):
    """Extract budget items from truncated JSON."""
    
    print(f"🔧 Extracting budget items from: {input_file}")
    
    # Read the file
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    content = data['cleaned_text']
    
    # Find the start of the JSON
    json_start = content.find('{')
    if json_start == -1:
        print("❌ No JSON found")
        return None
    
    json_content = content[json_start:]
    
    # Extract budget items using regex since the JSON is truncated
    budget_items = []
    
    # Pattern to match budget item objects
    item_pattern = r'\{\s*"department":\s*"([^"]*)",\s*"program":\s*"([^"]*)",\s*"program_id":\s*"([^"]*)",\s*"amount":\s*(\d+),\s*"amount_formatted":\s*"([^"]*)",\s*"fund_type":\s*"([^"]*)",\s*"fund_code":\s*"([^"]*)",\s*"positions":\s*([^,]*),\s*"appropriation_type":\s*"([^"]*)",\s*"fiscal_year":\s*"([^"]*)"'
    
    matches = re.finditer(item_pattern, json_content, re.DOTALL)
    
    for match in matches:
        try:
            department = match.group(1)
            program = match.group(2)
            program_id = match.group(3)
            amount = int(match.group(4))
            amount_formatted = match.group(5)
            fund_type = match.group(6)
            fund_code = match.group(7)
            positions_str = match.group(8).strip()
            appropriation_type = match.group(9)
            fiscal_year = match.group(10)
            
            # Handle positions (could be null, float, or int)
            positions = None
            if positions_str and positions_str != 'null':
                try:
                    positions = float(positions_str)
                except ValueError:
                    positions = None
            
            budget_item = {
                "department": department,
                "program": program if program else None,
                "program_id": program_id if program_id else None,
                "amount": amount,
                "amount_formatted": amount_formatted,
                "fund_type": fund_type,
                "fund_code": fund_code,
                "positions": positions,
                "appropriation_type": appropriation_type,
                "fiscal_year": fiscal_year
            }
            
            budget_items.append(budget_item)
            
        except Exception as e:
            print(f"⚠️  Error parsing budget item: {e}")
            continue
    
    # Extract cleaned text (the actual clean text, not the JSON)
    cleaned_text_match = re.search(r'"cleaned_text":\s*"([^"]*(?:\\.[^"]*)*)"', json_content)
    cleaned_text = ""
    if cleaned_text_match:
        # Unescape the string
        cleaned_text = cleaned_text_match.group(1).replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
    
    # Calculate summary
    departments = list(set([item['department'] for item in budget_items if item['department']]))
    total_amount = sum([item['amount'] for item in budget_items])
    
    # Create the corrected structure
    corrected_data = {
        "source_file": data.get('source_file', ''),
        "pages_processed": data.get('pages_processed', 0),
        "cleaned_text": cleaned_text,
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
    
    print(f"✅ Extracted budget items successfully!")
    print(f"   📊 Extracted {len(budget_items)} budget items")
    print(f"   🏛️  Found {len(departments)} departments:")
    for dept in departments:
        dept_items = [item for item in budget_items if item['department'] == dept]
        dept_total = sum([item['amount'] for item in dept_items])
        print(f"      • {dept}: {len(dept_items)} items, ${dept_total:,.2f}")
    print(f"   💰 Total amount: ${total_amount:,.2f}")
    print(f"   📁 Saved to: {output_file}")
    
    return corrected_data

if __name__ == "__main__":
    input_file = "cleaned_output/HB300__hybrid_extraction_first_10_pages_structured.json"
    if os.path.exists(input_file):
        extract_budget_items_from_truncated_json(input_file)
    else:
        print(f"❌ File not found: {input_file}") 