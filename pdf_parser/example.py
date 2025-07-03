#!/usr/bin/env python3
"""Example script demonstrating the PDF Parser API."""

import os
import argparse
import json
from pdf_parser.api import PDFTextReplacer, replace_pdf_text, search_text_in_pdf, parse_page_text

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
    search_parser.add_argument("--json-file", "-jf", help="Save JSON results to specified file path")
    search_parser.add_argument("--array-format", "-af", action="store_true", help="Use array format for JSON output instead of hierarchical format")
    
    # 解析命令
    parse_parser = subparsers.add_parser("parse", help="Parse and extract all replaceable text from a PDF page")
    parse_parser.add_argument("--input", "-i", required=True, help="Input PDF file path")
    parse_parser.add_argument("--page", "-p", type=int, default=0, help="Page number (0-based, default: 0)")
    parse_parser.add_argument("--json", "-j", action="store_true", help="Output results in JSON format")
    parse_parser.add_argument("--json-file", "-jf", help="Save JSON results to specified file path")
    parse_parser.add_argument("--with-coordinates", "-c", action="store_true", help="Include text coordinates in output")
    parse_parser.add_argument("--array-format", "-af", action="store_true", default=True, help="Use array format for JSON output instead of hierarchical format")
    
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
                    if args.array_format:
                        # 使用数组格式
                        array_results = []
                        global_index = 0
                        
                        # 先按文本分组
                        text_groups = {}
                        for item in results:
                            if "text" in item:
                                text = item["text"]
                            elif "context" in item:
                                text = item["context"]
                            else:
                                text = args.find
                            
                            if text not in text_groups:
                                text_groups[text] = []
                            
                            details = {k: v for k, v in item.items() if k != "text" and k != "context"}
                            text_groups[text].append(details)
                        
                        # 展平为数组
                        for text, details_list in text_groups.items():
                            for details in details_list:
                                array_results.append({
                                    "index": global_index,
                                    "text": text,
                                    "details": details
                                })
                                global_index += 1
                        
                        # JSON格式输出
                        print(json.dumps(array_results, indent=2))
                        
                        # 保存JSON到文件
                        if args.json_file:
                            json_file_path = args.json_file
                            os.makedirs(os.path.dirname(json_file_path) if os.path.dirname(json_file_path) else '.', exist_ok=True)
                        else:
                            base_name = os.path.basename(args.input)
                            name, _ = os.path.splitext(base_name)
                            search_text_safe = args.find.replace(" ", "_")[:20]
                            page_str = f"_page{args.page}" if args.page is not None else ""
                            json_file_path = f"output/{name}{page_str}_search_{search_text_safe}.json"
                            os.makedirs(os.path.dirname(json_file_path), exist_ok=True)
                        
                        # 保存JSON到文件
                        with open(json_file_path, "w", encoding="utf-8") as f:
                            json.dump(array_results, f, indent=2, ensure_ascii=False)
                    else:
                        # 使用原来的层次化结构
                        hierarchical_results = {}
                        
                        for item in results:
                            if "text" in item:
                                text = item["text"]
                            elif "context" in item:
                                text = item["context"]
                            else:
                                text = args.find
                            
                            details = {k: v for k, v in item.items() if k != "text" and k != "context"}
                            
                            if text in hierarchical_results:
                                hierarchical_results[text].append(details)
                            else:
                                hierarchical_results[text] = [details]
                        
                        # JSON格式输出
                        print(json.dumps(hierarchical_results, indent=2))
                        
                        # 保存JSON到文件
                        if args.json_file:
                            json_file_path = args.json_file
                            os.makedirs(os.path.dirname(json_file_path) if os.path.dirname(json_file_path) else '.', exist_ok=True)
                        else:
                            base_name = os.path.basename(args.input)
                            name, _ = os.path.splitext(base_name)
                            search_text_safe = args.find.replace(" ", "_")[:20]
                            page_str = f"_page{args.page}" if args.page is not None else ""
                            json_file_path = f"output/{name}{page_str}_search_{search_text_safe}.json"
                            os.makedirs(os.path.dirname(json_file_path), exist_ok=True)
                        
                        # 保存JSON到文件
                        with open(json_file_path, "w", encoding="utf-8") as f:
                            json.dump(hierarchical_results, f, indent=2, ensure_ascii=False)
                    
                    print(f"✅ JSON results saved to: {json_file_path}")
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
                        
                        # 输出坐标信息
                        if "rect" in result:
                            rect = result["rect"]
                            print(f"     Position: x0={rect['x0']:.2f}, y0={rect['y0']:.2f}, x1={rect['x1']:.2f}, y1={rect['y1']:.2f}")
            else:
                print(f"❌ No occurrences of '{args.find}' found.")
                
        except Exception as e:
            print(f"❌ Error during search: {e}")
            
    # 处理解析命令
    elif args.command == "parse":
        try:
            # 执行页面解析
            print(f"Parsing text from page {args.page+1} in {args.input}...")
            
            results = parse_page_text(
                pdf_path=args.input,
                page_num=args.page
            )
            
            # 输出结果
            if results:
                if args.json:
                    if args.array_format:
                        # 使用数组格式
                        array_results = []
                        global_index = 0
                        
                        # 先按文本分组
                        text_groups = {}
                        for item in results:
                            if "text" in item:
                                text = item["text"]
                                if text not in text_groups:
                                    text_groups[text] = []
                                # 移除text键，其余信息作为详情
                                details = {k: v for k, v in item.items() if k != "text"}
                                text_groups[text].append(details)
                        
                        # 展平为数组
                        for text, details_list in text_groups.items():
                            for details in details_list:
                                array_results.append({
                                    "index": global_index,
                                    "text": text,
                                    "details": details
                                })
                                global_index += 1
                        
                        # JSON格式输出
                        print(json.dumps(array_results, indent=2))
                        
                        # 保存JSON到文件
                        if args.json_file:
                            json_file_path = args.json_file
                            os.makedirs(os.path.dirname(json_file_path) if os.path.dirname(json_file_path) else '.', exist_ok=True)
                        else:
                            base_name = os.path.basename(args.input)
                            name, _ = os.path.splitext(base_name)
                            json_file_path = f"output/{name}_page{args.page}_parsed.json"
                            os.makedirs(os.path.dirname(json_file_path), exist_ok=True)
                        
                        # 保存JSON到文件
                        with open(json_file_path, "w", encoding="utf-8") as f:
                            json.dump(array_results, f, indent=2, ensure_ascii=False)
                    else:
                        # 使用原来的层次化结构
                        hierarchical_results = {}
                        
                        for item in results:
                            text = item["text"]
                            # 移除text键，其余信息作为详情
                            details = {k: v for k, v in item.items() if k != "text"}
                            
                            if text in hierarchical_results:
                                # 如果文本已存在，将详情添加到列表中
                                hierarchical_results[text].append(details)
                            else:
                                # 如果文本不存在，创建新列表
                                hierarchical_results[text] = [details]
                        
                        # JSON格式输出
                        print(json.dumps(hierarchical_results, indent=2))
                        
                        # 保存JSON到文件
                        if args.json_file:
                            json_file_path = args.json_file
                            # 确保输出目录存在
                            os.makedirs(os.path.dirname(json_file_path) if os.path.dirname(json_file_path) else '.', exist_ok=True)
                        else:
                            # 如果未指定输出文件名，使用默认文件名
                            base_name = os.path.basename(args.input)
                            name, _ = os.path.splitext(base_name)
                            json_file_path = f"output/{name}_page{args.page}_parsed.json"
                            os.makedirs(os.path.dirname(json_file_path), exist_ok=True)
                        
                        # 保存JSON到文件
                        with open(json_file_path, "w", encoding="utf-8") as f:
                            json.dump(hierarchical_results, f, indent=2, ensure_ascii=False)
                    
                    print(f"✅ JSON results saved to: {json_file_path}")
                else:
                    # 友好格式输出
                    print(f"\n✅ Extracted {len(results)} text elements from page {args.page+1} (including duplicates):")
                    for i, result in enumerate(results):
                        text = result["text"]
                        # 截取文本，避免过长
                        max_text = 100
                        if len(text) > max_text:
                            text = text[:max_text] + "..."
                        print(f"  {i+1}. {text}")
                        
                        # 如果指定了输出坐标
                        if args.with_coordinates and "rect" in result and result["rect"]:
                            rect = result["rect"]
                            print(f"     Position: x0={rect['x0']:.2f}, y0={rect['y0']:.2f}, x1={rect['x1']:.2f}, y1={rect['y1']:.2f}")
                        
                        # 如果有字体信息，则输出
                        if "font" in result:
                            print(f"     Font: {result['font']}")
            else:
                print(f"❌ No text elements extracted from page {args.page+1}.")
                
        except Exception as e:
            print(f"❌ Error during parsing: {e}")

if __name__ == "__main__":
    main() 