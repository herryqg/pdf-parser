#!/usr/bin/env python3
"""Test script to verify the functionality of analysis.py."""

import os
import sys
from pdf_parser.fonts.analysis import get_truetype_font_names, get_font_encoding_mapping, analyze_font_mappings

def main():
    """Run tests for analysis.py functions."""
    print("Testing analysis.py functions...")
    
    # Test analyze_font_mappings with a sample PDF if available
    sample_pdfs = []
    
    # Check inputs directory
    if os.path.exists('inputs'):
        for file in os.listdir('inputs'):
            if file.lower().endswith('.pdf'):
                sample_pdfs.append(os.path.join('inputs', file))
    
    if sample_pdfs:
        pdf_path = sample_pdfs[0]
        print(f"Testing analyze_font_mappings with {pdf_path}...")
        try:
            success = analyze_font_mappings(pdf_path)
            print(f"analyze_font_mappings result: {'Success' if success else 'Failed'}")
        except Exception as e:
            print(f"Error in analyze_font_mappings: {e}")
    else:
        print("No sample PDFs found to test with.")
    
    print("Test completed.")

if __name__ == "__main__":
    main() 