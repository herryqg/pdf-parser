#!/usr/bin/env python3
"""Example script for using the PDF Parser module."""

import argparse
import json
import os
import sys
from pdf_parser.api import PDFTextReplacer, replace_pdf_text, search_text_in_pdf, parse_page_text


def main():
    """Main entry point for the example script."""
    parser = argparse.ArgumentParser(description='PDF Parser and Text Replacement Tool')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Replace command
    replace_parser = subparsers.add_parser('replace', help='Replace text in PDF')
    replace_parser.add_argument('--input', '-i', required=True, help='Input PDF file')
    replace_parser.add_argument('--output', '-o', required=True, help='Output PDF file')
    replace_parser.add_argument('--target', '-t', required=True, help='Text to find and replace')
    replace_parser.add_argument('--replacement', '-r', required=True, help='Replacement text')
    replace_parser.add_argument('--page', '-p', type=int, default=0, help='Page number (0-based)')
    replace_parser.add_argument('--instance', '-n', type=int, default=-1, help='Instance number (-1 for all)')
    replace_parser.add_argument('--debug', '-d', action='store_true', help='Enable debug mode')
    replace_parser.add_argument('--auto-insert', '-a', action='store_true', help='Allow auto-insertion of characters')
    
    # Search command
    search_parser = subparsers.add_parser('search', help='Search text in PDF')
    search_parser.add_argument('--input', '-i', required=True, help='Input PDF file')
    search_parser.add_argument('--text', '-t', required=True, help='Text to search for')
    search_parser.add_argument('--page', '-p', type=int, default=None, help='Page number (0-based), omit to search all pages')
    search_parser.add_argument('--case-sensitive', '-c', action='store_true', help='Case sensitive search')
    search_parser.add_argument('--json', '-j', action='store_true', help='Output in JSON format')
    
    # Parse command
    parse_parser = subparsers.add_parser('parse', help='Parse text from PDF page')
    parse_parser.add_argument('--input', '-i', required=True, help='Input PDF file')
    parse_parser.add_argument('--page', '-p', type=int, default=0, help='Page number (0-based)')
    parse_parser.add_argument('--json', '-j', action='store_true', help='Output in JSON format')
    parse_parser.add_argument('--all-instances', '-a', action='store_true', help='Include all instances of each text')
    
    args = parser.parse_args()
    
    if args.command == 'replace':
        # Check if input file exists
        if not os.path.isfile(args.input):
            print(f"Error: Input file '{args.input}' not found.")
            return 1
            
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(args.output)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # Execute replacement
        success = replace_pdf_text(
            input_pdf=args.input,
            output_pdf=args.output,
            target_text=args.target,
            replacement_text=args.replacement,
            page_num=args.page,
            instance_index=args.instance,
            debug=args.debug,
            allow_auto_insert=args.auto_insert
        )
        
        if success:
            print(f"Text successfully replaced. Output saved to '{args.output}'.")
            return 0
        else:
            print("Text replacement failed.")
            return 1
            
    elif args.command == 'search':
        # Check if input file exists
        if not os.path.isfile(args.input):
            print(f"Error: Input file '{args.input}' not found.")
            return 1
            
        # Execute search
        results = search_text_in_pdf(
            pdf_path=args.input,
            search_text=args.text,
            page_num=args.page,
            case_sensitive=args.case_sensitive
        )
        
        if args.json:
            # Output as JSON
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            # Pretty print results
            if not results:
                print(f"Text '{args.text}' not found in the document.")
            else:
                print(f"Found {len(results)} occurrences of '{args.text}':")
                for idx, result in enumerate(results, 1):
                    page = result['page'] + 1  # Convert to 1-based for display
                    rect = result['rect']
                    print(f"{idx}. Page {page}, Position: ({rect['x0']:.2f}, {rect['y0']:.2f}) - ({rect['x1']:.2f}, {rect['y1']:.2f})")
                    if 'context' in result and result['context']:
                        context = result['context'].replace('\n', ' ')
                        if len(context) > 100:
                            context = context[:97] + '...'
                        print(f"   Context: \"{context}\"")
                    print()
        
        return 0
        
    elif args.command == 'parse':
        # Check if input file exists
        if not os.path.isfile(args.input):
            print(f"Error: Input file '{args.input}' not found.")
            return 1
            
        # Execute parse
        results = parse_page_text(
            pdf_path=args.input,
            page_num=args.page,
            include_all_instances=args.all_instances
        )
        
        if args.json:
            # Output as JSON
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            # Pretty print results
            if not results:
                print(f"No text found on page {args.page+1}.")
            else:
                print(f"Found {len(results)} text elements on page {args.page+1}:")
                for idx, result in enumerate(results, 1):
                    text = result['text']
                    
                    if args.all_instances and 'instances' in result:
                        instance_count = len(result['instances'])
                        print(f"{idx}. \"{text}\" ({instance_count} instances)")
                        
                        # 打印每个实例的位置
                        for i, rect in enumerate(result['instances'], 1):
                            if rect:
                                print(f"   Instance {i}: ({rect['x0']:.2f}, {rect['y0']:.2f}) - ({rect['x1']:.2f}, {rect['y1']:.2f})")
                    else:
                        rect = result.get('rect')
                        if rect:
                            print(f"{idx}. \"{text}\" at ({rect['x0']:.2f}, {rect['y0']:.2f}) - ({rect['x1']:.2f}, {rect['y1']:.2f})")
                        else:
                            print(f"{idx}. \"{text}\" (position unknown)")
                    
                    if 'font' in result:
                        print(f"   Font: {result['font']}")
                    
                    print()
        
        return 0
        
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main()) 