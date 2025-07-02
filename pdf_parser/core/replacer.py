"""Core functionality for PDF text replacement."""

import os
import re
import pikepdf
from datetime import datetime

from .cmap import parse_cmap, decode_pdf_string, escape_pdf_string, create_tounicode_cmap
from ..fonts.analysis import get_truetype_font_names, get_font_encoding_mapping, is_safe_code
from ..fonts.embedding import print_character_stream_mapping, print_rendering_mapping, update_pdf_font_mapping

# Constant to control detailed debug output
RENDER_LOG = False

def log_message(log_list, level, message, print_to_console=True):
    """
    Log a message with a specific level and optional console output.
    
    Args:
        log_list: 日志列表，用于存储日志消息
        level: 日志级别 (INFO, DEBUG, WARNING, ERROR, SUCCESS, DATA)
        message: 日志消息内容
        print_to_console: 是否将消息打印到控制台
    """

    prefix_map = {
        "INFO": "INFO",
        "DEBUG": "DEBUG",
        "WARNING": "WARNING",
        "ERROR": "ERROR",
        "SUCCESS": "SUCCESS",
        "DATA": "DATA",
    }
    
    prefix = prefix_map.get(level, "INFO")
    formatted_message = f"[{prefix}] {message}"

    if log_list is not None:
        log_list.append(formatted_message)

    if print_to_console:
        print(formatted_message)

def replace_text(input_pdf, output_pdf, target_text, replacement_text, page_num=0, ttf_file=None,
                 log_path="replace_log.txt", instance_index=-1, debug=False, allow_auto_insert=False,
                 verbose=1):
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
        verbose (int): 日志输出级别 (0=只输出错误, 1=标准输出, 2=详细输出, 3=调试输出)
        
    Returns:
        bool: True if successful, False otherwise.
    """
    # 根据verbose级别决定是否打印各种日志
    def should_print(level):
        if level == "ERROR":
            return verbose >= 0  # 始终输出错误
        elif level == "WARNING":
            return verbose >= 1  # 标准输出包括警告
        elif level == "SUCCESS" or level == "INFO":
            return verbose >= 1  # 标准输出包括信息和成功
        elif level == "DATA":
            return verbose >= 2  # 详细输出包括数据信息
        elif level == "DEBUG":
            return verbose >= 3 or debug  # 调试输出
        return True  # 默认打印
    
    # 重写log_message在当前上下文中的行为
    def log(log_list, level, message, print_to_console=True):
        if should_print(level) and print_to_console:
            log_message(log_list, level, message, print_to_console=True)
        else:
            # 仍然添加到日志列表，但不打印
            if log_list is not None:
                prefix = {"INFO": "INFO", "DEBUG": "DEBUG", "WARNING": "WARNING", 
                         "ERROR": "ERROR", "SUCCESS": "SUCCESS", "DATA": "DATA"}.get(level, "INFO")
                log_list.append(f"[{prefix}] {message}")
    
    if target_text == replacement_text:
        log(None, "WARNING", "Replacement text is the same as original text, skipping")
        return False
        
    import shutil
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)

    log_list = []
    pdf = pikepdf.open(input_pdf)
    
    # Get font mappings from the PDF
    from ..fonts.analysis import get_font_cmaps_from_reference
    font_cmaps = get_font_cmaps_from_reference(input_pdf)
    log(log_list, "INFO", "Using current PDF font mappings")

    # Check if page number is valid
    if page_num < 0 or page_num >= len(pdf.pages):
        error_msg = f"Invalid page number: {page_num}, PDF has {len(pdf.pages)} pages"
        log(log_list, "ERROR", error_msg)
        log_path_out = os.path.join(output_dir, os.path.basename(log_path))
        with open(log_path_out, "a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====\n")
            filtered = [ln for ln in log_list if 'missing ToUnicode CMap' not in ln and 'adding default mapping' not in ln]
            f.write('\n'.join(filtered) + '\n')
        return False

    # Collect all characters and their encodings from the entire PDF
    all_pdf_chars = {}  # font name -> character set
    all_char_codes = {}  # font name -> {character -> code set}
    for page_idx, page in enumerate(pdf.pages):
        if "/Resources" not in page or "/Font" not in page["/Resources"]:
            continue

        font_dict = page["/Resources"]["/Font"]
        tt_names_page = get_truetype_font_names(font_dict)
        if not tt_names_page:
            tt_names_page = [str(name) for name in font_dict.keys()]
        for font_name in tt_names_page:
            if font_name not in all_pdf_chars:
                all_pdf_chars[font_name] = set()
                all_char_codes[font_name] = {}

            font_ref = font_dict[pikepdf.Name(font_name)]

            # Check if we need to add ToUnicode CMap
            if "/ToUnicode" not in font_ref:
                # log(log_list, "WARNING", f"Font {font_name} missing ToUnicode CMap, adding default mapping")

                # Get font encoding
                encoding_name = '/WinAnsiEncoding'  # Default
                if "/Encoding" in font_ref:
                    encoding = font_ref["/Encoding"]
                    if isinstance(encoding, pikepdf.Name):
                        encoding_name = str(encoding)
                    elif isinstance(encoding, pikepdf.Dictionary) and "/BaseEncoding" in encoding:
                        encoding_name = str(encoding["/BaseEncoding"])

                # Create and add ToUnicode CMap
                cmap_str = create_tounicode_cmap(font_ref, encoding_name)
                font_ref["/ToUnicode"] = pikepdf.Stream(pdf, cmap_str.encode())

                # Extract CMap
                cmap_bytes = font_ref["/ToUnicode"].read_bytes()
                cmap_str = cmap_bytes.decode("utf-8", errors="ignore")
                font_cmap = parse_cmap(cmap_str)

                # Add to mapping dictionary
                if font_name not in font_cmaps:
                    font_cmaps[font_name] = {}
                font_cmaps[font_name].update(font_cmap)

                # log(log_list, "SUCCESS", f"Added {len(font_cmap)} mappings to font {font_name}")
            elif font_name not in font_cmaps:
                # Extract existing ToUnicode mapping
                cmap_bytes = font_ref["/ToUnicode"].read_bytes()
                cmap_str = cmap_bytes.decode("utf-8", errors="ignore")
                font_cmap = parse_cmap(cmap_str)
                font_cmaps[font_name] = font_cmap

            # Get page content
            content_objects = page['/Contents']
            combined = b''.join(obj.read_bytes() for obj in content_objects) if isinstance(content_objects,
                                                                                       pikepdf.Array) else content_objects.read_bytes()
            content_raw = combined.decode("latin1")

            # Find all text
            text_pattern = re.compile(r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]')
            font_pattern = re.compile(r'/([A-Za-z0-9]+)\s+\d+\s+Tf')
            current_font = None

            # Find all text using this font
            for match in re.finditer(
                    r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]|/[A-Za-z0-9]+\s+\d+\s+Tf',
                    content_raw):
                font_match = font_pattern.search(match.group(0))
                if font_match:
                    current_font = '/' + font_match.group(1)
                    continue

                if current_font != font_name:
                    continue

                text_match = text_pattern.search(match.group(0))
                if text_match:
                    is_tj = match.group(0).strip().endswith('TJ')
                    inner_text = text_match.group(2) if is_tj else text_match.group(1)
                    text_content_for_decode = inner_text.replace('\\', '')
                    encoded_bytes = text_content_for_decode.encode("latin1")

                    try:
                        decoded_text = decode_pdf_string(encoded_bytes, font_cmaps[font_name])
                        # Add all characters to the set
                        all_pdf_chars[font_name].update(decoded_text)

                        # Record encodings for each character
                        for i, char in enumerate(decoded_text):
                            if char not in all_char_codes[font_name]:
                                all_char_codes[font_name][char] = set()
                            # Record the character's original byte encoding
                            all_char_codes[font_name][char].add(encoded_bytes[i])
                    except:
                        log(log_list, "WARNING", f"⚠️ Decoding failed for some text on page {page_idx + 1}, skipped")

    # Record all used codes for each font
    all_used_codes = {}  # font name -> code set
    for font_name in all_char_codes:
        all_used_codes[font_name] = set()
        for char, codes in all_char_codes[font_name].items():
            all_used_codes[font_name].update(codes)
            
        # Get full font name for display
        display_font_name = font_name
        try:
            # Try to find this font reference to get its real name
            for page_idx, page in enumerate(pdf.pages):
                if "/Resources" not in page or "/Font" not in page["/Resources"]:
                    continue
                font_dict = page["/Resources"]["/Font"]
                if pikepdf.Name(font_name.lstrip("/")) in font_dict:
                    font_ref = font_dict[pikepdf.Name(font_name.lstrip("/"))]
                    if "/BaseFont" in font_ref:
                        base_font = str(font_ref["/BaseFont"])
                        display_font_name = f"{font_name} ({base_font})"
                        break
                    elif "/FontDescriptor" in font_ref and "/FontName" in font_ref["/FontDescriptor"]:
                        font_descriptor = font_ref["/FontDescriptor"]
                        font_name_obj = font_descriptor["/FontName"]
                        display_font_name = f"{font_name} ({str(font_name_obj)})"
                        break
        except Exception:
            # If anything fails, fall back to just using the font name
            pass
            
        log(log_list, "DATA", f"Font {display_font_name} uses codes: {', '.join(hex(code)[2:].upper() for code in sorted(all_used_codes[font_name]))}")

    # Use the specified page
    page = pdf.pages[page_num]
    log(log_list, "INFO", f"Processing page {page_num + 1}")

    if "/Resources" not in page or "/Font" not in page["/Resources"]:
        error_msg = f"Page {page_num + 1} has no font resources"
        log(log_list, "ERROR", error_msg)
        log_path_out = os.path.join(output_dir, os.path.basename(log_path))
        with open(log_path_out, "a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====\n")
            filtered = [ln for ln in log_list if 'missing ToUnicode CMap' not in ln and 'adding default mapping' not in ln]
            f.write('\n'.join(filtered) + '\n')
        print(f"Log written to: {log_path_out}")
        return False

    font_dict = page["/Resources"]["/Font"]
    # Prefer TrueType fonts; if none are found, fall back to all fonts
    tt_names = get_truetype_font_names(font_dict)
    if not tt_names:
        tt_names = [str(name) for name in font_dict.keys()]
    for font_name in tt_names:
        font_ref = font_dict[pikepdf.Name(font_name)]
        # Extract full font name from the descriptor if available
        display_font_name = font_name
        if "/BaseFont" in font_ref:
            base_font = str(font_ref["/BaseFont"])
            display_font_name = f"{font_name} ({base_font})"
        elif "/FontDescriptor" in font_ref and "/FontName" in font_ref["/FontDescriptor"]:
            font_descriptor = font_ref["/FontDescriptor"]
            font_name_obj = font_descriptor["/FontName"]
            display_font_name = f"{font_name} ({str(font_name_obj)})"
        if "/ToUnicode" not in font_ref:
            log(log_list, "WARNING", f"Font {display_font_name} on page {page_num + 1} missing ToUnicode CMap, adding default mapping")

            # Get font encoding
            encoding_name = '/WinAnsiEncoding'  # Default
            if "/Encoding" in font_ref:
                encoding = font_ref["/Encoding"]
                if isinstance(encoding, pikepdf.Name):
                    encoding_name = str(encoding)
                elif isinstance(encoding, pikepdf.Dictionary) and "/BaseEncoding" in encoding:
                    encoding_name = str(encoding["/BaseEncoding"])

            # Create and add ToUnicode CMap
            cmap_str = create_tounicode_cmap(font_ref, encoding_name)
            font_ref["/ToUnicode"] = pikepdf.Stream(pdf, cmap_str.encode())

            # Extract CMap
            cmap_bytes = font_ref["/ToUnicode"].read_bytes()
            cmap_str = cmap_bytes.decode("utf-8", errors="ignore")
            font_cmap = parse_cmap(cmap_str)

            # Add to mapping dictionary
            if font_name not in font_cmaps:
                font_cmaps[font_name] = {}
            font_cmaps[font_name].update(font_cmap)

            log(log_list, "SUCCESS", f"Added {len(font_cmap)} mappings to font {display_font_name}")

    # Create encoding mappings for all TT fonts
    font_encoding_maps = {}
    for font_name in tt_names:
        font_ref = font_dict[pikepdf.Name(font_name)]
        font_encoding_maps[font_name] = get_font_encoding_mapping(font_ref)
        
        # Get full font name for display
        display_font_name = font_name
        if "/BaseFont" in font_ref:
            base_font = str(font_ref["/BaseFont"])
            display_font_name = f"{font_name} ({base_font})"
        elif "/FontDescriptor" in font_ref and "/FontName" in font_ref["/FontDescriptor"]:
            font_descriptor = font_ref["/FontDescriptor"]
            font_name_obj = font_descriptor["/FontName"]
            display_font_name = f"{font_name} ({str(font_name_obj)})"
            
        if verbose >= 2:  # 详细输出模式下才输出字体编码映射
            log(log_list, "DATA", f"\nFont {display_font_name} encoding map:")
            for code, glyph in sorted(font_encoding_maps[font_name].items()):
                log(log_list, "DATA", f"  {code:02X} -> {glyph}")

    # Collect all text on the page
    all_texts = []
    content_objects = page['/Contents']
    combined = b''.join(obj.read_bytes() for obj in content_objects) if isinstance(content_objects,
                                                                               pikepdf.Array) else content_objects.read_bytes()
    content_raw = combined.decode("latin1")
    text_pattern = re.compile(r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]')
    font_pattern = re.compile(r'/([A-Za-z0-9]+)\s+\d+\s+Tf')

    # First collect all text
    current_pos = 0
    current_font = None
    for match in re.finditer(r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]|/[A-Za-z0-9]+\s+\d+\s+Tf',
                             content_raw):
        if match.start() > current_pos:
            current_pos = match.end()
            continue

        font_match = font_pattern.search(match.group(0))
        if font_match:
            current_font = '/' + font_match.group(1)
            current_pos = match.end()
            continue

        text_match = text_pattern.search(match.group(0))
        if text_match and current_font in font_cmaps:
            is_tj = match.group(0).strip().endswith('TJ')
            inner_text = text_match.group(2) if is_tj else text_match.group(1)
            text_content_for_decode = inner_text.replace('\\', '')
            encoded_bytes = text_content_for_decode.encode("latin1")
            decoded_text = decode_pdf_string(encoded_bytes, font_cmaps[current_font])
            all_texts.append((current_font, decoded_text, encoded_bytes, text_match, is_tj))
        current_pos = match.end()

    # Process the replacement
    changed = False
    modified_fonts = set()
    new_segments = []
    current_pos = 0
    current_instance_index = 0  # Track current instance index
    
    # Add instance selection log info
    if instance_index >= 0:
        log(log_list, "INFO", f"Only replacing instance #{instance_index+1}")
    else:
        log(log_list, "INFO", f"Replacing all instances")
    
    # Find which font the target text is using
    target_font = None
    target_font_chars = set()
    
    # Add instance selection log info
    for font_name, texts, bytes_list, text_match, is_tj in all_texts:
        if texts == target_text:
            target_font = font_name
            break
    
    # If target font is found, only check characters in that font
    if target_font and target_font in all_pdf_chars:
        target_font_chars = all_pdf_chars[target_font]
        
        # Get full target font name for display
        target_font_display = target_font
        try:
            for page_idx, page in enumerate(pdf.pages):
                if "/Resources" not in page or "/Font" not in page["/Resources"]:
                    continue
                font_dict_check = page["/Resources"]["/Font"]
                if pikepdf.Name(target_font.lstrip("/")) in font_dict_check:
                    target_font_ref = font_dict_check[pikepdf.Name(target_font.lstrip("/"))]
                    if "/BaseFont" in target_font_ref:
                        base_font = str(target_font_ref["/BaseFont"])
                        target_font_display = f"{target_font} ({base_font})"
                        break
                    elif "/FontDescriptor" in target_font_ref and "/FontName" in target_font_ref["/FontDescriptor"]:
                        font_descriptor = target_font_ref["/FontDescriptor"]
                        font_name_obj = font_descriptor["/FontName"]
                        target_font_display = f"{target_font} ({str(font_name_obj)})"
                        break
        except Exception:
            pass
            
        log(log_list, "INFO", f"Found target text font: {target_font_display}, contains {len(target_font_chars)} characters")
    else:
        # If target font is not found, merge all fonts' characters
        log(log_list, "WARNING", f"Could not determine which font the target text uses, checking all fonts")
        for font_name, char_set in all_pdf_chars.items():
            target_font_chars.update(char_set)
    
    # Check for unsupported characters in replacement text
    unsupported_chars = []
    # 对映射的更严格检查
    for char in replacement_text:
        is_supported = False
        
        # 如果在目标字体的字符集中找到，则支持
        if char in target_font_chars or char in " \t\n\r":  # 忽略空白字符
            is_supported = True
        
        # 如果通过CMap反向映射能找到，也算支持
        elif target_font and target_font in font_cmaps:
            target_cmap = font_cmaps[target_font]
            reverse_map = {v: k for k, v in target_cmap.items()}
            if char in reverse_map:
                is_supported = True
                
        # 如果字符不受支持，则加入列表
        if not is_supported:
            unsupported_chars.append(char)
    
    # If any characters are unsupported, log them and stop the replacement
    if unsupported_chars and not allow_auto_insert:
        unsupported_str = ''.join(unsupported_chars)
        if target_font:
            # Use full target font name if available
            target_font_display = target_font_display if 'target_font_display' in locals() else target_font
            
            for ch in unsupported_chars:
                log(log_list, "WARNING", f"Font {target_font_display} missing character '{ch}', replacement canceled")
        else:
            for ch in unsupported_chars:
                log(log_list, "WARNING", f"Unknown font missing character '{ch}', replacement canceled")
        
        log(log_list, "INFO", f"Found unsupported characters, preserving original text")
        
        # Copy original PDF to output
        try:
            shutil.copy2(input_pdf, output_pdf)
            log(log_list, "SUCCESS", f"Original PDF preserved: {output_pdf}")
        except Exception as e:
            log(log_list, "ERROR", f"Failed to copy original PDF: {e}")

        # Write log and return early
        log_path_out = os.path.join(output_dir, os.path.basename(log_path))
        with open(log_path_out, "a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====\n")
            filtered = [ln for ln in log_list if 'missing ToUnicode CMap' not in ln and 'adding default mapping' not in ln]
            f.write('\n'.join(filtered) + '\n')
        print(f"Log written to: {log_path_out}")
        return False

    # Main text replacement loop
    for segment in re.finditer(
            r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]|/[A-Za-z0-9]+\s+\d+\s+Tf|(?:[-\d.]+\s+){5}[-\d.]+\s+Tm',
            content_raw):
        if segment.start() > current_pos:
            new_segments.append(content_raw[current_pos:segment.start()])

        font_match = font_pattern.search(segment.group(0))
        if font_match:
            current_font = '/' + font_match.group(1)
            new_segments.append(segment.group(0))
            current_pos = segment.end()
            continue

        text_match = text_pattern.search(segment.group(0))
        if text_match and current_font in font_cmaps:
            is_tj = segment.group(0).strip().endswith('TJ')
            inner_text = text_match.group(2) if is_tj else text_match.group(1)
            text_content_for_decode = inner_text.replace('\\', '')
            encoded_bytes = text_content_for_decode.encode("latin1")
            decoded_text = decode_pdf_string(encoded_bytes, font_cmaps[current_font])

            if decoded_text == target_text:
                # If an instance index is specified, track the current instance
                if instance_index >= 0:
                    # Skip if not the target instance
                    if current_instance_index != instance_index:
                        current_instance_index += 1
                        new_segments.append(segment.group(0))
                        current_pos = segment.end()
                        continue
                    current_instance_index += 1
                
                # Get full font name for display
                display_font_name = current_font
                font_ref = font_dict[pikepdf.Name(current_font)]
                if "/BaseFont" in font_ref:
                    base_font = str(font_ref["/BaseFont"])
                    display_font_name = f"{current_font} ({base_font})"
                elif "/FontDescriptor" in font_ref and "/FontName" in font_ref["/FontDescriptor"]:
                    font_descriptor = font_ref["/FontDescriptor"]
                    font_name_obj = font_descriptor["/FontName"]
                    display_font_name = f"{current_font} ({str(font_name_obj)})"
                
                log(log_list, "INFO", f"({display_font_name}) Replacing: {decoded_text} → {replacement_text}")

                # Debug original text's character stream mapping
                if verbose >= 2:  # 详细模式下输出流映射信息
                    log(log_list, "INFO", "\nOriginal text stream mapping:")
                    print_character_stream_mapping(decoded_text, encoded_bytes, font_cmaps[current_font], log_list, debug)
                    log(log_list, "INFO", f"  Original stream: {repr(text_content_for_decode)}")

                    # Print original text's rendering mapping
                    font_ref = font_dict[pikepdf.Name(current_font)]
                    encoding_map = get_font_encoding_mapping(font_ref)

                    log(log_list, "INFO", "\nFont encoding map:")
                    for code, glyph in sorted(encoding_map.items()):
                        log(log_list, "DATA", f"  {code:02X} -> {glyph}")

                    log(log_list, "INFO", "\nOriginal text rendering process:")
                    for i, char in enumerate(decoded_text):
                        print_rendering_mapping(font_ref, char, encoded_bytes[i], log_list, debug)

                existing_cmap = font_cmaps[current_font]
                used_codes = set(k[0] for k in existing_cmap.keys())
                char_to_code = {v: k[0] for k, v in existing_cmap.items()}
                new_codes = []
                allocated_chars = {}

                # Get all codes already used with this font
                already_used_codes = all_used_codes.get(current_font, set())

                # First check all characters in replacement text
                unsupported_chars_segment = []
                
                # 预检查字符支持状态
                for char in replacement_text:
                    is_supported = False
                    # 严格检查是否在当前字体中
                    if char in all_char_codes.get(current_font, {}):
                        is_supported = True
                    # 空白字符总是支持的
                    elif char in " \t\n\r":
                        is_supported = True
                    # 对于not allow_auto_insert模式，我们需要更严格，只接受当前字体中的字符
                    # 不再检查CMap，因为这与实际处理过程保持一致
                    
                    # 如果不支持且不允许自动插入，添加到不支持字符列表
                    if not is_supported and not allow_auto_insert:
                        unsupported_chars_segment.append(char)
                
                # 如果有不支持的字符且不允许自动插入，完整检查并报告每个字符，然后跳过替换
                if unsupported_chars_segment and not allow_auto_insert:
                    # 获取当前字体的完整显示名称
                    current_display_font = display_font_name
                    if current_font != current_display_font and not "(" in current_display_font:
                        try:
                            font_ref = font_dict[pikepdf.Name(current_font.lstrip("/"))]
                            if "/BaseFont" in font_ref:
                                base_font = str(font_ref["/BaseFont"])
                                current_display_font = f"{current_font} ({base_font})"
                            elif "/FontDescriptor" in font_ref and "/FontName" in font_ref["/FontDescriptor"]:
                                font_descriptor = font_ref["/FontDescriptor"]
                                font_name_obj = font_descriptor["/FontName"]
                                current_display_font = f"{current_font} ({str(font_name_obj)})"
                        except Exception:
                            pass
                    
                    # 报告所有不支持字符
                    for char in unsupported_chars_segment:
                        log(log_list, "WARNING", f"Character '{char}' not found in current font {current_display_font}")
                        log(log_list, "WARNING", f"  Character '{char}' not available in current font. Auto-insert disabled.")
                    
                    # 记录不支持字符并拒绝替换
                    log(log_list, "WARNING", f"Not all characters in replacement text were processed: {', '.join(unsupported_chars_segment)}")
                    log(log_list, "WARNING", f"Partial replacement not allowed with auto-insert disabled. Preserving original text.")
                    new_segments.append(segment.group(0))
                    current_pos = segment.end()
                    continue
                
                # 如果所有字符都支持或允许自动插入，继续正常的处理
                new_codes = []
                allocated_chars = {}
                
                # Process each character for replacement
                for char in replacement_text:
                    # First check if the character exists in the current font and record it clearly
                    is_in_current_font = char in all_char_codes.get(current_font, {})
                    if not is_in_current_font:
                        # 获取当前字体的完整显示名称
                        current_display_font = display_font_name
                        if current_font != current_display_font and not "(" in current_display_font:
                            try:
                                font_ref = font_dict[pikepdf.Name(current_font.lstrip("/"))]
                                if "/BaseFont" in font_ref:
                                    base_font = str(font_ref["/BaseFont"])
                                    current_display_font = f"{current_font} ({base_font})"
                                elif "/FontDescriptor" in font_ref and "/FontName" in font_ref["/FontDescriptor"]:
                                    font_descriptor = font_ref["/FontDescriptor"]
                                    font_name_obj = font_descriptor["/FontName"]
                                    current_display_font = f"{current_font} ({str(font_name_obj)})"
                            except Exception:
                                pass

                        log(log_list, "WARNING", f"Character '{char}' not found in current font {current_display_font}")
                        
                        # 如果字符不在当前字体且不允许自动插入，则跳过整个替换
                        if not allow_auto_insert:
                            log(log_list, "WARNING", f"  Character '{char}' not available in current font. Auto-insert disabled.")
                            # 应该不会执行到这里，因为我们已经预检查过了
                            new_segments.append(segment.group(0))
                            current_pos = segment.end()
                            break
                        
                        if char not in char_to_code:
                            log(log_list, "WARNING", f"  Character '{char}' not available in current font without borrowing from other fonts.")
                            if not allow_auto_insert:
                                # 应该不会执行到这里，因为我们已经预检查过了
                                new_segments.append(segment.group(0))
                                current_pos = segment.end()
                                break
                    
                    # 处理字符编码
                    code = None
                    if is_in_current_font:
                        # Character exists in current font
                        codes = list(all_char_codes[current_font][char])
                        if codes:
                            code = codes[0]
                            allocated_chars[char] = code
                            log(log_list, "INFO", f"  Using current font encoding '{char}': 0x{code:02X}")
                    elif char in char_to_code:
                        code = char_to_code[char]
                        allocated_chars[char] = code
                        log(log_list, "INFO", f"  Using mapping from font CMap '{char}': 0x{code:02X}")
                    else:
                        # 如果不允许自动插入，则直接跳过替换
                        if not allow_auto_insert:
                            log(log_list, "WARNING", f"  Character '{char}' not available in font. Auto-insert disabled.")
                            # 应该不会执行到这里，因为我们已经预检查过了
                            new_segments.append(segment.group(0))
                            current_pos = segment.end()
                            break
                            
                        # If character not found in current font, check other fonts
                        found_in_other_font = False
                        found_font = None
                        for other_font, chars in all_pdf_chars.items():
                            if char in chars and char in all_char_codes.get(other_font, {}):
                                found_in_other_font = True
                                found_font = other_font
                                break
                        
                        if found_in_other_font:
                            # Try to get the full name of the found font
                            found_font_display = found_font
                            try:
                                for page_idx, page in enumerate(pdf.pages):
                                    if "/Resources" not in page or "/Font" not in page["/Resources"]:
                                        continue
                                    font_dict_check = page["/Resources"]["/Font"]
                                    if pikepdf.Name(found_font.lstrip("/")) in font_dict_check:
                                        found_font_ref = font_dict_check[pikepdf.Name(found_font.lstrip("/"))]
                                        if "/BaseFont" in found_font_ref:
                                            base_font = str(found_font_ref["/BaseFont"])
                                            found_font_display = f"{found_font} ({base_font})"
                                            break
                                        elif "/FontDescriptor" in found_font_ref and "/FontName" in found_font_ref["/FontDescriptor"]:
                                            font_descriptor = found_font_ref["/FontDescriptor"]
                                            font_name_obj = font_descriptor["/FontName"]
                                            found_font_display = f"{found_font} ({str(font_name_obj)})"
                                            break
                            except Exception:
                                pass
                                
                            log(log_list, "WARNING", f"  Character '{char}' not in current font {display_font_name}, but found in font {found_font_display}")
                            
                            # 退出循环并保存日志
                            log(log_list, "WARNING", f"  Cannot use characters from different fonts. Stopping replacement.")
                            new_segments.append(segment.group(0))
                            current_pos = segment.end()
                            continue
                        else:
                            log(log_list, "WARNING", f"  Character '{char}' not found in any font in the PDF, attempting to assign new encoding")
                            
                            # Start looking for safe codes from 0xB0 to avoid common character conflicts
                            start_code = 0xB0
                            found = False

                            # Try all possible codes
                            for code_candidate in range(start_code, 0x100):
                                # Make sure code isn't already used
                                if (code_candidate in used_codes or 
                                        code_candidate in already_used_codes):
                                    continue

                                # Check all TT font encoding maps
                                is_safe = True
                                for font_name, encoding_map in font_encoding_maps.items():
                                    if code_candidate in encoding_map:
                                        is_safe = False
                                        break

                                if is_safe_code(code_candidate) and is_safe:
                                    key = bytes([code_candidate])
                                    existing_cmap[key] = char
                                    used_codes.add(code_candidate)
                                    already_used_codes.add(code_candidate)
                                    code = code_candidate
                                    allocated_chars[char] = code
                                    modified_fonts.add(current_font)
                                    log(log_list, "INFO", f"  Allocated safe code for '{char}': 0x{code:02X}")
                                    found = True
                                    break

                            if not found:
                                # Try extended range
                                for code_candidate in range(0x100, 0x110):
                                    # Note: beyond single byte range requires special handling
                                    if code_candidate > 0xFF:
                                        log(log_list, "WARNING", f"⚠️ Trying extended code range: 0x{code_candidate:02X}")
                                        print(f"⚠️ Trying extended code range: 0x{code_candidate:02X}")
                                    key = bytes([code_candidate & 0xFF])
                                    if key in existing_cmap:
                                        continue
                                    existing_cmap[key] = char
                                    code = code_candidate & 0xFF
                                    allocated_chars[char] = code
                                    modified_fonts.add(current_font)
                                    log(log_list, "INFO", f"  ⚠️ Allocated extended code for '{char}': 0x{code:02X}")
                                    print(f"  ⚠️ Allocated extended code for '{char}': 0x{code:02X}")
                                    found = True
                                    break

                            if not found:
                                log(log_list, "WARNING", f"  ❌ Could not find safe code for '{char}', skipping")
                                print(f"  ❌ Could not find safe code for '{char}', skipping")
                                continue
                    
                    # 只有当成功分配了编码时，才添加到new_codes列表
                    if code is not None:
                        new_codes.append(code)

                if not new_codes:
                    log(log_list, "WARNING", f"All replacement characters unavailable, preserving original text")
                    new_segments.append(segment.group(0))
                    current_pos = segment.end()
                    continue

                # Debug replacement text's character stream mapping
                new_encoded = bytes(new_codes)

                # 检查是否所有字符都被正确处理
                # 如果不允许自动插入，确认已处理的字符数量应与替换文本字符数相同
                if not allow_auto_insert and len(new_codes) < len(replacement_text):
                    unhandled_chars = [ch for ch in replacement_text if ch not in allocated_chars]
                    if unhandled_chars:
                        log(log_list, "WARNING", f"Not all characters in replacement text were processed: {', '.join(unhandled_chars)}")
                        log(log_list, "WARNING", f"Partial replacement not allowed with auto-insert disabled. Preserving original text.")
                        new_segments.append(segment.group(0))
                        current_pos = segment.end()
                        continue
                
                # 详细输出部分，仅在verbose >= 2时输出
                if verbose >= 2:
                    # Debug replacement text's character stream mapping
                    log(log_list, "INFO", "\nReplacement text stream mapping:")
                    print_character_stream_mapping(''.join([char for char in replacement_text if char in allocated_chars]), 
                                           new_encoded, font_cmaps[current_font], log_list, debug)

                    # Debug replacement text's rendering process
                    log(log_list, "INFO", "\nReplacement text rendering process:")
                    for i, char in enumerate(allocated_chars.keys()):
                        print_rendering_mapping(font_ref, char, new_encoded[i], log_list, debug)

                    # Enhanced log: record new encodings
                    new_hex = ' '.join(f'{c:02X}' for c in new_codes)
                    log(log_list, "INFO", f"  New encodings: {new_hex}")

                # Generate new encoded string
                new_encoded_str = escape_pdf_string(new_encoded.decode("latin1"))

                # Print new stream (including escape characters)
                if verbose >= 2:
                    log(log_list, "INFO", f"  New stream: {repr(new_encoded_str)}")

                # TJ: [ ... ]TJ, Tj: ( ... )Tj
                if is_tj:
                    segment_text = segment.group(0).replace(f"[{text_match.group(2)}]", f"[({new_encoded_str})]")
                else:
                    segment_text = segment.group(0).replace(f"({text_match.group(1)})", f"({new_encoded_str})")
                new_segments.append(segment_text)
                changed = True
            else:
                new_segments.append(segment.group(0))
        else:
            new_segments.append(segment.group(0))
        current_pos = segment.end()

    if current_pos < len(content_raw):
        new_segments.append(content_raw[current_pos:])

    content_raw = ''.join(new_segments)
    if changed:
        # Even if no font mappings were modified, create updated PDF
        if modified_fonts:
            # New characters added, need to update font mappings
            from ..fonts.embedding import update_pdf_font_mapping
            for font_name in modified_fonts:
                update_pdf_font_mapping(input_pdf, font_name, font_cmaps[font_name], log_list)
            updated_pdf_path = os.path.join(output_dir, os.path.basename(input_pdf).replace('.pdf', '_updated.pdf'))
            updated_pdf = pikepdf.open(updated_pdf_path)
        else:
            # No new characters, just modify content stream
            log(log_list, "INFO", f"No new characters, directly modifying content stream")
            # pikepdf doesn't have a copy method, create a new PDF
            updated_pdf_path = os.path.join(output_dir, os.path.basename(input_pdf).replace('.pdf', '_updated.pdf'))
            # Close current PDF, reopen to copy
            pdf.close()
            import shutil
            shutil.copy2(input_pdf, updated_pdf_path)
            updated_pdf = pikepdf.open(updated_pdf_path)

        # Update content stream
        page = updated_pdf.pages[page_num]
        page['/Contents'] = pikepdf.Stream(updated_pdf, content_raw.encode("latin1"))
        output_pdf_path = os.path.join(output_dir, os.path.basename(output_pdf))
        updated_pdf.save(output_pdf_path)
        log(log_list, "SUCCESS", f"Changes saved to: {output_pdf_path}")
        success = True
    else:
        log(log_list, "WARNING", f"No matching text found on page {page_num + 1}, nothing replaced.")
        success = False
        
    log_path_out = os.path.join(output_dir, os.path.basename(log_path))
    with open(log_path_out, "a", encoding="utf-8") as f:
        f.write(f"\n===== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====\n")
        filtered = [ln for ln in log_list if 'missing ToUnicode CMap' not in ln and 'adding default mapping' not in ln]
        f.write('\n'.join(filtered) + '\n')
    print(f"Log written to: {log_path_out}")
    
    return success