#!/usr/bin/env python3
"""Example script demonstrating the PDF Parser API."""

import os
import sys
import argparse
from pdf_parser.api import PDFTextReplacer, replace_pdf_text

def main():
    parser = argparse.ArgumentParser(description="PDF Text Replacement Tool")
    parser.add_argument("--input", "-i", required=True, help="Input PDF file path")
    parser.add_argument("--output", "-o", help="Output PDF file path (default: auto-generated)")
    parser.add_argument("--find", "-f", required=True, help="Text to find")
    parser.add_argument("--replace", "-r", required=True, help="Text to replace with")
    parser.add_argument("--page", "-p", type=int, default=0, help="Page number (0-based, default: 0)")
    parser.add_argument("--instance", "-ist", type=int, default=-1, 
                       help="Specific text instance to replace (-1 for all instances, default: -1)")
    parser.add_argument("--analyze", action="store_true", 
                       help="Analyze font mappings in the PDF")
    parser.add_argument("--debug", action="store_true", 
                       help="Enable debug output")
    parser.add_argument("--allow-auto-insert", action="store_true",
                       help="Allow automatic insertion of characters not present in the font")
    parser.add_argument("--verbose", "-v", type=int, choices=[0, 1, 2, 3], default=1,
                       help="Verbosity level (0=errors only, 1=standard, 2=detailed, 3=debug)")
    
    args = parser.parse_args()
    
    # Generate default output path if not provided
    if not args.output:
        base_name = os.path.basename(args.input)
        name, ext = os.path.splitext(base_name)
        args.output = f"output/{name}_replaced{ext}"
        
    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    
    # Example 1: Using the function directly
    print(f"Replacing '{args.find}' with '{args.replace}' on page {args.page+1}...")
    success = replace_pdf_text(
        input_pdf=args.input,
        output_pdf=args.output,
        target_text=args.find,
        replacement_text=args.replace,
        page_num=args.page,
        instance_index=args.instance,
        debug=args.debug,
        allow_auto_insert=args.allow_auto_insert,
        verbose=args.verbose
    )
    
    if success:
        print(f"✅ Replacement successful! Output saved to: {args.output}")
    else:
        print(f"❌ Replacement failed or nothing was replaced.")
    
    # Example 2: Using the class-based API for additional operations
    if args.analyze:
        print("\nAnalyzing PDF font mappings...")
        analyzer = PDFTextReplacer(debug=args.debug, verbose=args.verbose)
        analyzer.analyze_fonts(args.input)
        print("✅ Font analysis complete. Results saved to output/font_mapping_analysis.txt")

if __name__ == "__main__":
    main() 