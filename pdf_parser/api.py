"""Public API for the PDF Parser module."""

from .core.replacer import replace_text
from .fonts.analysis import get_font_cmaps_from_reference, analyze_font_mappings

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


# Simplified functions for direct use without creating a class instance

def replace_pdf_text(input_pdf, output_pdf, target_text, replacement_text, page_num=0, instance_index=-1, debug=False, allow_auto_insert=False, verbose=1):
    """
    Replace text in a PDF document (simplified function).
    
    Args:
        input_pdf (str): Path to input PDF file
        output_pdf (str): Path to output PDF file
        target_text (str): Text to find and replace
        replacement_text (str): Text to insert as replacement
        page_num (int): Page number to modify (0-based)
        instance_index (int): Specific instance to replace (-1 for all instances)
        debug (bool): Enable debug logging
        allow_auto_insert (bool): Whether to allow automatic insertion of characters not present in the font
        verbose (int): 日志输出级别 (0=只输出错误, 1=标准输出, 2=详细输出, 3=调试输出)
        
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
        debug=debug,
        allow_auto_insert=allow_auto_insert,
        verbose=verbose
    ) 