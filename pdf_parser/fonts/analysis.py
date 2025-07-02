# """Font analysis utilities for PDF parsing and text replacement."""
#
# import os
# import pikepdf
# from ..core.cmap import parse_cmap
#
#
# def get_truetype_font_names(font_dict):
#     """
#     Get names of all TrueType fonts in a font dictionary.
#
#     Args:
#         font_dict: PDF font dictionary object
#
#     Returns:
#         list: Names of TrueType fonts
#     """
#     tt_names = []
#     try:
#         for name in font_dict.keys():
#             font = font_dict[name]
#             if "/Subtype" in font and font["/Subtype"] == "/TrueType":
#                 tt_names.append(str(name))
#             elif "/FontDescriptor" in font and "/FontFile2" in font["/FontDescriptor"]:
#                 tt_names.append(str(name))
#         except Exception:
#             pass
#     return tt_names
#
#
# def get_font_encoding_mapping(font_ref):
#     """
#     Get character encoding mapping for a font.
#
#     Args:
#         font_ref: PDF font reference object
#
#     Returns:
#         dict: Mapping from character codes to glyph names
#     """
#     encoding_map = {}
#
#     try:
#         if "/Encoding" in font_ref:
#             encoding = font_ref["/Encoding"]
#
#             # Standard encoding
#             if isinstance(encoding, pikepdf.Name):
#                 # TODO: Add support for standard encodings
#                 pass
#
#             # Custom encoding
#             elif isinstance(encoding, pikepdf.Dictionary):
#                 if "/Differences" in encoding:
#                     differences = encoding["/Differences"]
#                     current_code = 0
#
#                     for item in differences:
#                         if isinstance(item, int):
#                             current_code = item
#                         elif isinstance(item, pikepdf.Name):
#                             encoding_map[current_code] = str(item)
#                             current_code += 1
#     except Exception:
#         pass
#
#     return encoding_map
#
#
# def is_safe_code(code, font_info=None):
#     """
#     Check if a character code is safe to use for replacement.
#
#     Args:
#         code: Character code to check
#         font_info: Font information (optional)
#
#     Returns:
#         bool: True if the code is safe to use
#     """
#     # Basic safety check - avoid control characters, common symbols
#     unsafe_ranges = [
#         (0x00, 0x1F),  # Control characters
#         (0x20, 0x20),  # Space
#         (0x22, 0x22),  # Quote
#         (0x27, 0x27),  # Apostrophe
#         (0x28, 0x29),  # Parentheses
#         (0x2C, 0x2C),  # Comma
#         (0x2E, 0x2E),  # Period
#         (0x3A, 0x3B),  # Colon, semicolon
#         (0x3F, 0x3F),  # Question mark
#         (0x5B, 0x5D),  # Square brackets
#         (0x7B, 0x7D),  # Curly braces
#     ]
#
#     for start, end in unsafe_ranges:
#         if start <= code <= end:
#             return False
#
#     return True
#
#
# def get_font_cmaps_from_reference(pdf_path):
#     """
#     Extract all font CMap mappings from a PDF file.
#
#     Args:
#         pdf_path: Path to PDF file
#
#     Returns:
#         dict: Dictionary of font name to CMap mapping
#     """
#     font_cmaps = {}
#
#     try:
#         pdf = pikepdf.open(pdf_path)
#
#         for page_idx, page in enumerate(pdf.pages):
#             if "/Resources" not in page or "/Font" not in page["/Resources"]:
#                 continue
#
#             font_dict = page["/Resources"]["/Font"]
#
#             for font_name in font_dict.keys():
#                 font_ref = font_dict[font_name]
#
#                 if "/ToUnicode" in font_ref:
#                     cmap_bytes = font_ref["/ToUnicode"].read_bytes()
#                     cmap_str = cmap_bytes.decode('utf-8', errors='ignore')
#                     font_cmap = parse_cmap(cmap_str)
#
#                     if str(font_name) not in font_cmaps:
#                         font_cmaps[str(font_name)] = {}
#                     font_cmaps[str(font_name)].update(font_cmap)
#
#         pdf.close()
#     except Exception as e:
#         print(f"Error extracting CMaps: {e}")
#
#     return font_cmaps
#
#
# def analyze_font_mappings(pdf_path, output_txt="font_mapping_analysis.txt"):
#     """
#     Analyze fonts in a PDF and save the mapping information to a text file.
#
#     Args:
#         pdf_path: Path to PDF file
#         output_txt: Path to output text file
#
#     Returns:
#         bool: True if successful
#     """
#     output_dir = "output"
#     os.makedirs(output_dir, exist_ok=True)
#     output_path = os.path.join(output_dir, output_txt)
#
#     try:
#         font_cmaps = get_font_cmaps_from_reference(pdf_path)
#
#         with open(output_path, "w", encoding="utf-8") as f:
#             f.write(f"Font Mapping Analysis for {pdf_path}\n")
#             f.write("=" * 60 + "\n\n")
#
#             for font_name, cmap in font_cmaps.items():
#                 f.write(f"Font: {font_name}\n")
#                 f.write("-" * 40 + "\n")
#
#                 for code, char in sorted(cmap.items()):
#                     if isinstance(code, bytes) and len(code) == 1:
#                         hex_code = f"{code[0]:02X}"
#                         f.write(f"  {hex_code} -> {char} (Unicode: U+{ord(char):04X})\n")
#
#                 f.write("\n")
#
#         return True
#     except Exception as e:
#         print(f"Error analyzing font mappings: {e}")
#         return False