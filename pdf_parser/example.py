#!/usr/bin/env python3
"""Example script demonstrating the PDF Parser API."""

import os
import argparse
import json
from pdf_parser.api import PDFTextReplacer, replace_pdf_text, search_text_in_pdf

def main():
    parser = argparse.ArgumentParser(description="PDF Text Replacement and Search Tool")
    
    # 创建子命令解析器
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # 替换命令
    replace_parser = subparsers.add_parser("replace", help="Replace text in PDF")
    replace_parser.add_argument("--input", "-i", required=True, help="Input PDF file path")
    replace_parser.add_argument("--output", "-o", help="Output PDF file path (default: auto-generated)")
    replace_parser.add_argument("--find", "-f", required=True, help="Text to find")
    replace_parser.add_argument("--replace", "-r", required=True, help="Text to replace with")
    replace_parser.add_argument("--page", "-p", type=int, default=0, help="Page number (0-based, default: 0)")
    replace_parser.add_argument("--instance", "-ist", type=int, default=-1, 
                       help="Specific text instance to replace (-1 for all instances, default: -1)")
    replace_parser.add_argument("--analyze", action="store_true", 
                       help="Analyze font mappings in the PDF")
    replace_parser.add_argument("--debug", action="store_true", 
                       help="Enable debug output")
    replace_parser.add_argument("--allow-auto-insert", action="store_true",
                       help="Allow automatic insertion of characters not present in the font")
    replace_parser.add_argument("--verbose", "-v", type=int, choices=[0, 1, 2, 3], default=1,
                       help="Verbosity level (0=errors only, 1=standard, 2=detailed, 3=debug)")
    
    # 搜索命令
    search_parser = subparsers.add_parser("search", help="Search text in PDF")
    search_parser.add_argument("--input", "-i", required=True, help="Input PDF file path")
    search_parser.add_argument("--find", "-f", required=True, help="Text to search for")
    search_parser.add_argument("--page", "-p", type=int, help="Page number to search (0-based, omit to search all pages)")
    search_parser.add_argument("--case-sensitive", "-cs", action="store_true", help="Enable case-sensitive search")
    search_parser.add_argument("--json", "-j", action="store_true", help="Output results in JSON format")
    
    args = parser.parse_args()
    
    # 如果没有指定命令，默认为替换命令
    if not args.command:
        args.command = "replace"
    
    # 处理替换命令
    if args.command == "replace":
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
    
    # 处理搜索命令
    elif args.command == "search":
        try:
            # 执行搜索
            print(f"Searching for '{args.find}' in {args.input}...")
            if args.page is not None:
                print(f"Searching only on page {args.page+1}")
                
            results = search_text_in_pdf(
                pdf_path=args.input, 
                search_text=args.find, 
                page_num=args.page,
                case_sensitive=args.case_sensitive
            )
            
            # 输出结果
            if results:
                if args.json:
                    # JSON格式输出
                    print(json.dumps(results, indent=2))
                else:
                    # 友好格式输出
                    print(f"\n✅ Found {len(results)} instances of '{args.find}':")
                    for i, result in enumerate(results):
                        page = result["page"] + 1  # 转为1-based页码
                        context = result["context"].strip().replace("\n", " ")
                        # 截取上下文，避免过长
                        max_context = 100
                        if len(context) > max_context:
                            context = context[:max_context] + "..."
                        print(f"  {i+1}. Page {page}: {context}")
            else:
                print(f"❌ No occurrences of '{args.find}' found.")
                
        except Exception as e:
            print(f"❌ Error during search: {e}")

if __name__ == "__main__":
    main() 