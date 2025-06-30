"""Public API for the PDF Parser module."""

from .core.cmap import parse_cmap, decode_pdf_string
from .core.replacer import replace_text
from .fonts.analysis import get_font_cmaps_from_reference, analyze_font_mappings

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