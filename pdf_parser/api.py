"""Public API for the PDF Parser module."""

from .core.replacer import replace_text
from .fonts.analysis import get_font_cmaps_from_reference, analyze_font_mappings

def parse_page_text(pdf_path, page_num=0):
    """
    解析PDF页面中的可替换文本并返回列表
    
    Args:
        pdf_path (str): PDF文件路径
        page_num (int): 页码 (0-based)
        
    Returns:
        list: 包含可替换文本的列表，每项为dict，包含文本内容和位置信息
        
    Notes:
        - 提取文本时会过滤掉被其他文本框完全包含的文本框
        - 文本框按面积从大到小排序，较小的文本框如果完全位于较大文本框内则被过滤
        - 相同文本的不同实例会根据其在文档中的顺序获得正确的坐标
        - 使用位置哈希确保每个文本实例都匹配到不同的页面位置，避免重复匹配
    """
    import fitz  # PyMuPDF
    import pikepdf
    import re
    from .core.cmap import parse_cmap, decode_pdf_string
    
    results = []
    
    try:
        # 打开PDF文档
        doc_mupdf = fitz.open(pdf_path)
        if page_num < 0 or page_num >= len(doc_mupdf):
            raise ValueError(f"页码 {page_num} 超出范围，PDF共有 {len(doc_mupdf)} 页")
        
        # 获取当前页面
        page = doc_mupdf[page_num]
        
        
        # 1. 使用pikepdf收集内容流中的文本
        try:
            # 打开pikepdf文档
            pdf = pikepdf.open(pdf_path)
            pikepdf_page = pdf.pages[page_num]
            
            # 从页面获取字体CMap
            font_cmaps = {}
            if "/Resources" in pikepdf_page and "/Font" in pikepdf_page["/Resources"]:
                font_dict = pikepdf_page["/Resources"]["/Font"]
                
                for font_name in font_dict.keys():
                    font_ref = font_dict[font_name]
                    
                    if "/ToUnicode" in font_ref:
                        cmap_bytes = font_ref["/ToUnicode"].read_bytes()
                        cmap_str = cmap_bytes.decode('utf-8', errors='ignore')
                        font_cmap = parse_cmap(cmap_str)
                        font_cmaps[str(font_name)] = font_cmap
                    else:
                        from .core.cmap import create_tounicode_cmap
                        encoding_name = '/WinAnsiEncoding'  # 默认
                        if "/Encoding" in font_ref:
                            encoding = font_ref["/Encoding"]
                            if isinstance(encoding, pikepdf.Name):
                                encoding_name = str(encoding)
                        
                        # 创建CMap
                        cmap_str = create_tounicode_cmap(font_ref, encoding_name)
                        font_cmap = parse_cmap(cmap_str)
                        font_cmaps[str(font_name)] = font_cmap
            
            # 解析内容流
            content_bytes = None
            if '/Contents' in pikepdf_page:
                content_objects = pikepdf_page['/Contents']
                
                if isinstance(content_objects, pikepdf.Array):
                    content_bytes = b''
                    for obj in content_objects:
                        content_bytes += obj.read_bytes()
                else:
                    content_bytes = content_objects.read_bytes()
            
            # 如果获取到内容流，解析文本
            decoded_items = []
            if content_bytes:
                content_str = content_bytes.decode('latin1', errors='replace')
                
                # 解析文本操作符
                text_pattern = re.compile(r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]')
                font_pattern = re.compile(r'/([A-Za-z0-9]+)\s+\d+\s+Tf')
                current_font = None
                
                for match in re.finditer(
                        r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]|/[A-Za-z0-9]+\s+\d+\s+Tf',
                        content_str):
                    
                    font_match = font_pattern.search(match.group(0))
                    if font_match:
                        current_font = '/' + font_match.group(1)
                        continue
                    
                    text_match = text_pattern.search(match.group(0))
                    if text_match and current_font in font_cmaps:
                        is_tj = match.group(0).strip().endswith('TJ')
                        inner_text = text_match.group(2) if is_tj else text_match.group(1)
                        
                        # 处理TJ数组
                        if is_tj:
                            try:
                                processed = ''
                                for part in inner_text.split():
                                    if part.startswith('(') and part.endswith(')'):
                                        processed += part[1:-1]
                                if processed:
                                    inner_text = processed
                            except Exception:
                                pass
                        
                        # 处理转义字符
                        text_content_for_decode = inner_text.replace('\\(', '(').replace('\\)', ')').replace('\\\\', '\\')
                        encoded_bytes = text_content_for_decode.encode('latin1')
                        
                        try:
                            # 使用CMap解码文本
                            decoded_text = decode_pdf_string(encoded_bytes, font_cmaps[current_font])
                            if decoded_text.strip():
                                decoded_items.append((current_font, decoded_text.strip(), encoded_bytes))
                        except Exception as e:
                            print(f"解码文本时出错: {e}")
            
            pdf.close()
            
            # 2. 从解码项目中提取所有文本项
            # 跟踪已处理的文本实例数量
            text_instance_counts = {}
            
            # 跟踪已处理位置的文本实例
            processed_positions = {}
            
            for font_name, text_str, encoded_bytes in decoded_items:
                if text_str:
                    # 初始化计数器（如果不存在）
                    if text_str not in text_instance_counts:
                        text_instance_counts[text_str] = 0
                        processed_positions[text_str] = set()
                    
                    current_instance_index = text_instance_counts[text_str]
                    text_instance_counts[text_str] += 1
                    
                    # 使用PyMuPDF搜索文本位置
                    text_instances = page.search_for(text_str)
                    rect = None
                    
                    # 过滤掉已处理过的位置
                    available_instances = []
                    for instance in text_instances:
                        # 使用矩形的哈希作为唯一标识
                        pos_hash = (round(instance.x0), round(instance.y0), 
                                   round(instance.x1), round(instance.y1))
                        if pos_hash not in processed_positions[text_str]:
                            available_instances.append((instance, pos_hash))
                    
                    # 确保找到了未处理过的实例
                    if available_instances:
                        # 使用第一个未处理的实例
                        rect, pos_hash = available_instances[0]
                        # 标记此位置已处理
                        processed_positions[text_str].add(pos_hash)
                        rect_dict = {
                            "x0": rect.x0,
                            "y0": rect.y0, 
                            "x1": rect.x1,
                            "y1": rect.y1
                        }
                    elif text_instances:
                        # 如果所有实例都已处理，但仍然需要一个位置（这种情况不应该发生）
                        rect = text_instances[0]
                        rect_dict = {
                            "x0": rect.x0,
                            "y0": rect.y0, 
                            "x1": rect.x1,
                            "y1": rect.y1
                        }
                        # 添加警告标记
                        log_warning = "警告：内容流中有更多实例，但页面上没有足够的匹配文本"
                    
                    # 添加到结果列表
                    results.append({
                        "text": text_str,
                        "rect": rect_dict if rect else None,
                        "font": font_name,
                        "encoded_bytes": encoded_bytes.hex(),
                        "instance_index": current_instance_index  # 添加实例索引以便追踪
                    })
            
            # 3. 如果没有找到任何文本，回退到PyMuPDF
            if not results:
                try:
                    all_text = page.get_text()
                    text_instance_counts = {}
                    processed_positions = {}
                    
                    for line in all_text.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        
                        # 初始化计数器（如果不存在）
                        if line not in text_instance_counts:
                            text_instance_counts[line] = 0
                            processed_positions[line] = set()
                        
                        current_instance_index = text_instance_counts[line]
                        text_instance_counts[line] += 1
                        
                        # 尝试搜索位置信息
                        try:
                            text_instances = page.search_for(line)
                            rect = None
                            
                            # 过滤掉已处理过的位置
                            available_instances = []
                            for instance in text_instances:
                                # 使用矩形的哈希作为唯一标识
                                pos_hash = (round(instance.x0), round(instance.y0), 
                                           round(instance.x1), round(instance.y1))
                                if pos_hash not in processed_positions[line]:
                                    available_instances.append((instance, pos_hash))
                            
                            if available_instances:
                                # 使用第一个未处理的实例
                                rect, pos_hash = available_instances[0]
                                # 标记此位置已处理
                                processed_positions[line].add(pos_hash)
                                results.append({
                                    "text": line,
                                    "rect": {
                                        "x0": rect.x0,
                                        "y0": rect.y0, 
                                        "x1": rect.x1,
                                        "y1": rect.y1
                                    },
                                    "source": "pymupdf_basic",
                                    "instance_index": current_instance_index
                                })
                            else:
                                # 无法获得位置或所有位置已处理
                                results.append({
                                    "text": line,
                                    "rect": None,
                                    "source": "pymupdf_basic",
                                    "instance_index": current_instance_index
                                })
                        except Exception:
                            # 搜索失败，返回无位置信息
                            results.append({
                                "text": line,
                                "rect": None,
                                "source": "pymupdf_basic",
                                "instance_index": current_instance_index
                            })
                except Exception as e:
                    print(f"PyMuPDF提取文本失败: {e}")
                    
        except Exception as e:
            print(f"处理页面内容时出错: {e}")
            # 如果处理失败，至少尝试返回基本的文本内容
            try:
                all_text = page.get_text()
                text_instance_counts = {}
                processed_positions = {}
                
                for line in all_text.splitlines():
                    line = line.strip()
                    if line:
                        # 初始化计数器（如果不存在）
                        if line not in text_instance_counts:
                            text_instance_counts[line] = 0
                            processed_positions[line] = set()
                        
                        current_instance_index = text_instance_counts[line]
                        text_instance_counts[line] += 1
                        
                        # 尝试搜索位置信息
                        try:
                            text_instances = page.search_for(line)
                            rect = None
                            
                            # 过滤掉已处理过的位置
                            available_instances = []
                            for instance in text_instances:
                                # 使用矩形的哈希作为唯一标识
                                pos_hash = (round(instance.x0), round(instance.y0), 
                                           round(instance.x1), round(instance.y1))
                                if pos_hash not in processed_positions[line]:
                                    available_instances.append((instance, pos_hash))
                            
                            if available_instances:
                                # 使用第一个未处理的实例
                                rect, pos_hash = available_instances[0]
                                # 标记此位置已处理
                                processed_positions[line].add(pos_hash)
                                results.append({
                                    "text": line,
                                    "rect": {
                                        "x0": rect.x0,
                                        "y0": rect.y0, 
                                        "x1": rect.x1,
                                        "y1": rect.y1
                                    },
                                    "source": "pymupdf_basic",
                                    "instance_index": current_instance_index
                                })
                            else:
                                # 无法获得位置或所有位置已处理
                                results.append({
                                    "text": line,
                                    "rect": None,
                                    "source": "pymupdf_basic",
                                    "instance_index": current_instance_index
                                })
                        except Exception:
                            # 搜索失败，返回无位置信息
                            results.append({
                                "text": line,
                                "rect": None,
                                "source": "pymupdf_basic",
                                "instance_index": current_instance_index
                            })
            except Exception:
                pass
        
        # 关闭PyMuPDF文档
        doc_mupdf.close()
        
        # 过滤掉被包含在其他框内部的文本框
        filtered_results = []
        # 首先，按照面积大小降序排列（从大到小）
        if results:
            # 计算所有矩形的面积
            for result in results:
                if result.get("rect"):
                    rect = result["rect"]
                    # 计算矩形面积
                    area = (rect["x1"] - rect["x0"]) * (rect["y1"] - rect["y0"])
                    result["area"] = area
                else:
                    result["area"] = 0
            
            # 按面积排序
            sorted_results = sorted(results, key=lambda x: x.get("area", 0), reverse=True)
            
            # 过滤被包含的框
            for i, result in enumerate(sorted_results):
                rect1 = result.get("rect")
                is_contained = False
                
                # 如果没有坐标信息，则保留
                if not rect1:
                    filtered_results.append(result)
                    continue
                
                # 检查是否被其他（更大的）框包含
                for j, larger_result in enumerate(sorted_results[:i]):  # 只检查面积更大的框
                    rect2 = larger_result.get("rect")
                    if not rect2:
                        continue
                        
                    # 判断rect1是否被rect2完全包含
                    if (rect1["x0"] >= rect2["x0"] and 
                        rect1["y0"] >= rect2["y0"] and 
                        rect1["x1"] <= rect2["x1"] and 
                        rect1["y1"] <= rect2["y1"]):
                        # 完全包含，标记为已包含
                        is_contained = True
                        break
                
                # 如果不被任何框包含，则添加到过滤结果中
                if not is_contained:
                    filtered_results.append(result)
                    
            # 移除临时的area字段
            for result in filtered_results:
                if "area" in result:
                    del result["area"]
        else:
            filtered_results = results
            
        return filtered_results
        
    except Exception as e:
        raise Exception(f"解析PDF页面时出错: {str(e)}")

def search_text_in_pdf(pdf_path, search_text, page_num=None, case_sensitive=False):
    """
    在PDF中搜索文本并返回结果列表。
    
    Args:
        pdf_path (str): PDF文件路径
        search_text (str): 要搜索的文本
        page_num (int, optional): 特定页码 (0-based)，如为None则搜索所有页面
        case_sensitive (bool): 是否区分大小写
        
    Returns:
        list: 包含搜索结果的列表，每个结果为dict，包含页码、文本、位置信息等
    """
    import fitz  # PyMuPDF
    
    results = []
    flags = 0 if case_sensitive else fitz.TEXT_PRESERVE_WHITESPACE
    
    try:
        doc = fitz.open(pdf_path)
        
        # 确定要搜索的页面范围
        if page_num is not None:
            if 0 <= page_num < len(doc):
                pages_to_search = [page_num]
            else:
                raise ValueError(f"页码 {page_num} 超出范围，PDF共有 {len(doc)} 页")
        else:
            pages_to_search = range(len(doc))
            
        # 搜索每一页
        for page_idx in pages_to_search:
            page = doc[page_idx]
            
            # 使用fitz搜索文本
            text_instances = page.search_for(search_text, flags=flags)
            
            # 获取页面文本块，用于判断文本顺序
            blocks = page.get_text("blocks")
            blocks_map = {}
            
            # 为每个文本块分配一个序号
            for idx, block in enumerate(blocks):
                # block格式: (x0, y0, x1, y1, "text", block_no, block_type)
                rect = fitz.Rect(block[:4])
                blocks_map[idx] = {
                    "rect": rect,
                    "text": block[4],
                    "order": idx
                }
            
            # 对搜索结果进行处理
            page_results = []
            for idx, rect in enumerate(text_instances):
                # 查找此矩形所在的文本块
                containing_block = None
                for block_idx, block_info in blocks_map.items():
                    if block_info["rect"].contains(rect) or block_info["rect"].intersects(rect):
                        containing_block = block_idx
                        break
                
                # 提取匹配文本的上下文
                context_text = ""
                if containing_block is not None:
                    context_text = blocks_map[containing_block]["text"]
                
                # 添加到结果列表
                result = {
                    "page": page_idx,
                    "rect": {
                        "x0": rect.x0,
                        "y0": rect.y0,
                        "x1": rect.x1,
                        "y1": rect.y1
                    },
                    "text": search_text,
                    "context": context_text,
                    "block_order": containing_block if containing_block is not None else -1
                }
                page_results.append(result)
            
            # 按照文本块顺序排序结果
            page_results.sort(key=lambda x: x["block_order"])
            results.extend(page_results)
        
        doc.close()
        return results
        
    except Exception as e:
        raise Exception(f"搜索PDF时出错: {str(e)}")

class PDFTextReplacer:
    """Main class for replacing text in PDF files."""
    
    def __init__(self, debug=False, verbose=1):
        """
        Initialize a PDFTextReplacer instance.
        
        Args:
            debug (bool): Enable debug logging
            verbose (int): 日志输出级别 (0=只输出错误, 1=标准输出, 2=详细输出, 3=调试输出)
        """
        self.debug = debug
        self.verbose = verbose
    
    def replace_text(self, input_pdf, output_pdf, target_text, replacement_text, page_num=0, instance_index=-1, allow_auto_insert=False):
        """
        Replace text in a PDF document.
        
        Args:
            input_pdf (str): Path to input PDF file
            output_pdf (str): Path to output PDF file
            target_text (str): Text to find and replace
            replacement_text (str): Text to insert as replacement
            page_num (int): Page number to modify (0-based)
            instance_index (int): Specific instance to replace (-1 for all instances)
            allow_auto_insert (bool): Whether to allow automatic insertion of characters not present in the font
            
        Returns:
            bool: True if successful, False otherwise
        """
        return replace_text(
            input_pdf=input_pdf,
            output_pdf=output_pdf,
            target_text=target_text, 
            replacement_text=replacement_text,
            page_num=page_num,
            instance_index=instance_index,
            debug=self.debug,
            allow_auto_insert=allow_auto_insert,
            verbose=self.verbose
        )
    
    def analyze_fonts(self, pdf_path, output_txt="font_mapping_analysis.txt"):
        """
        Analyze fonts in a PDF and output the mapping to a text file.
        
        Args:
            pdf_path (str): Path to the PDF to analyze
            output_txt (str): Path to the output text file
        """
        return analyze_font_mappings(pdf_path, output_txt)
    
    def get_font_cmaps(self, pdf_path):
        """
        Extract font CMap mappings from a PDF.
        
        Args:
            pdf_path (str): Path to the PDF file
            
        Returns:
            dict: Dictionary mapping font names to their CMap dictionaries
        """
        return get_font_cmaps_from_reference(pdf_path)
    
    def search_text(self, pdf_path, search_text, page_num=None, case_sensitive=False):
        """
        在PDF中搜索文本并返回结果列表。
        
        Args:
            pdf_path (str): PDF文件路径
            search_text (str): 要搜索的文本
            page_num (int, optional): 特定页码 (0-based)，如为None则搜索所有页面
            case_sensitive (bool): 是否区分大小写
            
        Returns:
            list: 包含搜索结果的列表，每个结果为dict，包含页码、文本、位置信息等
        """
        return search_text_in_pdf(pdf_path, search_text, page_num, case_sensitive)
        
    def parse_page_text(self, pdf_path, page_num=0):
        """
        解析PDF页面中的可替换文本并返回列表。
        
        Args:
            pdf_path (str): PDF文件路径
            page_num (int): 页码 (0-based)
            
        Returns:
            list: 包含可替换文本的列表，每项为dict，包含文本内容和位置信息
        """
        return parse_page_text(pdf_path, page_num)


# Simplified functions for direct use without creating a class instance

def replace_pdf_text(input_pdf, output_pdf, target_text, replacement_text, page_num=0, instance_index=-1, debug=False, allow_auto_insert=False, verbose=1):
    """
    Replace text in a PDF.
    
    Args:
        input_pdf (str): Path to input PDF.
        output_pdf (str): Path to output PDF.
        target_text (str): Text to replace.
        replacement_text (str): Replacement text.
        page_num (int): Page number (0-based).
        ttf_file (str, optional): Path to TrueType font file for embedding.
        log_path (str): Path to log file.
        instance_index (int): Index of text instance to replace, -1 for all.
        debug (bool): Whether to enable detailed debug logging.
        allow_auto_insert (bool): Whether to allow automatic insertion of characters 
                                 not present in the font. Default is False, which will
                                 skip replacement when missing characters are detected.
        verbose (int): log output level (0=only error, 1=standard output, 2=detailed output, 3=debug output)
        
    Returns:
        bool: True if successful, False otherwise.
    """
    return replace_text(
        input_pdf=input_pdf,
        output_pdf=output_pdf,
        target_text=target_text, 
        replacement_text=replacement_text,
        page_num=page_num,
        instance_index=instance_index,
        debug=debug,
        allow_auto_insert=allow_auto_insert,
        verbose=verbose
    ) 