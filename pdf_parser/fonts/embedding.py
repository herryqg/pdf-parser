"""Font embedding and manipulation utilities for PDF text replacement."""

import os
import tempfile
import pikepdf
import re
from fontTools import subset
from fontTools.ttLib import TTFont

def update_pdf_font_mapping(pdf_path, font_name, new_cmap, log=None):
    """
    Update PDF font mapping and embed font subset.
    
    Args:
        pdf_path (str): Path to input PDF.
        font_name (str): Name of the font to update.
        new_cmap (dict): New CMap to use for the font.
        log (list, optional): List to append log messages.
        
    Returns:
        str: Path to the updated PDF.
    """
    if log is None:
        log = []
        
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    
    log.append(f"\n=== Processing font {font_name} ===")
    pdf = pikepdf.open(pdf_path)
    
    # First collect all characters used with this font in the whole PDF
    all_font_chars = set()
    # Collect original CMap to ensure we only add new mappings, not overwrite existing ones
    original_cmap = {}
    
    for page_idx, page in enumerate(pdf.pages):
        if "/Resources" not in page or "/Font" not in page["/Resources"]:
            continue
            
        font_dict = page["/Resources"]["/Font"]
        if pikepdf.Name(font_name) not in font_dict:
            continue
            
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
                r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]|/[A-Za-z0-9]+\s+\d+\s+Tf', content_raw):
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
                
                # Decode using the current font's mapping
                font_ref = font_dict[pikepdf.Name(font_name)]
                if "/ToUnicode" in font_ref:
                    cmap_bytes = font_ref["/ToUnicode"].read_bytes()
                    cmap_str = cmap_bytes.decode("utf-8", errors="ignore")
                    
                    from ..core.cmap import parse_cmap, decode_pdf_string
                    local_cmap = parse_cmap(cmap_str)
                    
                    # Save original mapping
                    for k, v in local_cmap.items():
                        original_cmap[k] = v
                    try:
                        decoded_text = decode_pdf_string(encoded_bytes, local_cmap)
                        # Add all characters to the set
                        all_font_chars.update(decoded_text)
                    except:
                        log.append(f"⚠️ Decoding failed for some text on page {page_idx + 1}, skipped")
    
    log.append(f"📊 Font {font_name} uses characters: {', '.join(sorted(all_font_chars))}")
    log.append(f"📊 Original CMap mappings: {len(original_cmap)}")
    
    # Merge original mapping and new mapping, keeping original when there's a conflict
    merged_cmap = original_cmap.copy()
    added_count = 0
    
    # Only add new mappings, don't modify existing ones
    for k, v in new_cmap.items():
        if k not in merged_cmap:
            merged_cmap[k] = v
            added_count += 1
            log.append(f"➕ Added new mapping: <{k.hex().upper()}> -> {v} (U+{ord(v):04X})")
            
    log.append(f"📊 Merged CMap mappings: {len(merged_cmap)}, added: {added_count}")
    
    for page in pdf.pages:
        if "/Resources" in page and "/Font" in page["/Resources"]:
            font_dict = page["/Resources"]["/Font"]
            if pikepdf.Name(font_name) in font_dict:
                font_ref = font_dict[pikepdf.Name(font_name)]
                if "/ToUnicode" in font_ref:
                    # Generate ToUnicode CMap
                    cmap_str = "/CIDInit /ProcSet findresource begin\n"
                    cmap_str += "12 dict begin\n"
                    cmap_str += "begincmap\n"
                    cmap_str += "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
                    cmap_str += "/CMapName /Adobe-Identity-UCS def\n"
                    cmap_str += "/CMapType 2 def\n"
                    cmap_str += "1 begincodespacerange\n<00> <FF>\nendcodespacerange\n"
                    
                    sorted_cmap = sorted(merged_cmap.items())
                    cmap_str += f"{len(sorted_cmap)} beginbfchar\n"
                    for k, v in sorted_cmap:
                        log.append(f"📌 CMap mapping: <{k.hex().upper()}> -> {v} (U+{ord(v):04X})")
                        cmap_str += f"<{k.hex().upper()}> <{ord(v):04X}>\n"
                    cmap_str += "endbfchar\nendcmap\n"
                    cmap_str += "CMapName currentdict /CMap defineresource pop\nend\nend"
                    
                    font_ref["/ToUnicode"] = pikepdf.Stream(pdf, cmap_str.encode())
                    
                    # Generate and embed font subset
                    font_path = os.path.join(output_dir, font_name.replace("/", "") + ".ttf")
                    if not os.path.exists(font_path):
                        log.append(f"⚠️ Font file not found: {font_path}")
                        continue
                        
                    used_chars = set(merged_cmap.values())  # Use merged mapping
                    log.append(f"🛠️ Generating subset font, includes: {used_chars}")
                    unicodes = [ord(c) for c in used_chars]
                    
                    with tempfile.NamedTemporaryFile(suffix=".ttf", delete=False, dir=output_dir) as temp_subset:
                        subset_path = temp_subset.name
                        
                    options = subset.Options()
                    options.set(layout_features='')
                    options.name_IDs = ['*']
                    options.name_legacy = True
                    options.name_languages = ['*']
                    options.retain_gids = True
                    options.passthrough_tables = True
                    options.drop_tables = []  # Keep all tables to avoid Adobe errors
                    options.subset_prefix = ""  # Disable font subset prefix
                    font = subset.load_font(font_path, options)
                    subsetter = subset.Subsetter(options)
                    subsetter.populate(unicodes=unicodes)
                    subsetter.subset(font)
                    font.save(subset_path)
                    log.append(f"📄 Subset font saved to: {subset_path}")
                    
                    with open(subset_path, "rb") as f:
                        font_stream = pikepdf.Stream(pdf, f.read())
                        if "/FontDescriptor" in font_ref:
                            descriptor = font_ref["/FontDescriptor"]
                            descriptor["/FontFile2"] = font_stream
                            
                            # Get real font name from TTF
                            ttf = TTFont(font_path)
                            name_record = ttf['name'].getName(1, 3, 1, 1033)
                            real_font_name = name_record.toUnicode() if name_record else "PUDHinban-B"
                            pdf_font_name = pikepdf.Name("/" + real_font_name)
                            
                            descriptor["/FontName"] = pdf_font_name
                            font_ref["/BaseFont"] = pdf_font_name
                            log.append(f"✅ Font embedded: {font_name}")
                        else:
                            log.append(f"⚠️ {font_name} has no FontDescriptor, cannot embed font")
                    os.unlink(subset_path)
                    
                    # Handle font widths (add new ones only)
                    if "/Widths" in font_ref:
                        font_ref["/FirstChar"] = 0
                        log.append(f"🛠️ Force set FirstChar to 0 to allow low code points in Widths")
                        widths = font_ref["/Widths"]
                        first_char = font_ref.get("/FirstChar", 0)
                        original_len = len(widths)
                        
                        ttf_font = TTFont(font_path)
                        cmap_table = next((t for t in ttf_font['cmap'].tables if t.isUnicode()), None)
                        
                        # Process only new char to code mappings
                        new_chars_mapping = {}
                        for k, v in new_cmap.items():
                            if k not in original_cmap:
                                new_chars_mapping[k[0]] = v
                                
                        # Store original character mappings from PDF
                        original_chars = {}
                        
                        # Calculate width ratios based only on characters already in the PDF
                        char_width_ratios = {}
                        for i in range(original_len):
                            code = first_char + i
                            pdf_width = widths[i]
                            # Find character for this code from original mapping
                            char = None
                            for k, v in original_cmap.items():
                                if k[0] == code:
                                    char = v
                                    break
                            if not char:
                                continue
                            original_chars[code] = char
                            char_unicode = ord(char)
                            char_glyph = cmap_table.cmap.get(char_unicode) if cmap_table else None
                            if char_glyph:
                                ttf_width = ttf_font['hmtx'][char_glyph][0]
                                if ttf_width > 0:
                                    char_width_ratios[char_unicode] = (pdf_width / ttf_width) * 0.97
                                    
                        default_ratio = sum(char_width_ratios.values()) / len(
                            char_width_ratios) if char_width_ratios else 1.0
                            
                        # Process only new characters' widths
                        for code, char in new_chars_mapping.items():
                            index = code - first_char
                            # Skip invalid codes
                            if code > 255 or code < first_char:
                                log.append(f"⚠️ Skipping invalid code: {code} (out of range or less than FirstChar {first_char})")
                                continue
                                
                            # Check if this is truly a new character
                            is_new_char = True
                            if code in original_chars and original_chars[code] == char:
                                is_new_char = False
                            elif char in all_font_chars:
                                is_new_char = False
                                log.append(f"ℹ️ Character '{char}' already used elsewhere with this font, treating as existing")
                                
                            # Skip if not a new character
                            if not is_new_char:
                                continue
                                
                            char_unicode = ord(char)
                            char_glyph = cmap_table.cmap.get(char_unicode) if cmap_table else None
                            
                            if char_glyph:
                                ttf_width = ttf_font['hmtx'][char_glyph][0]
                                ratio = char_width_ratios.get(char_unicode, default_ratio)
                                new_width = int(round(ttf_width * ratio))
                                log.append(
                                    f"✅ New char width: '{char}' (U+{char_unicode:04X}), TTF width: {ttf_width}, "
                                    f"ratio: {ratio:.3f} → PDF width: {new_width}")
                            else:
                                new_width = int(round(sum(widths) / len(widths)))
                                log.append(f"⚠️ No TTF support: '{char}' (U+{char_unicode:04X}), using average width: {new_width}")
                                
                            if index >= len(widths):
                                default_width = int(round(sum(widths) / len(widths)))
                                while len(widths) < index:
                                    widths.append(default_width)
                                    log.append(f"🔧 Filling missing width at index={len(widths) - 1}, default width: {default_width}")
                                widths.append(new_width)
                                log.append(f"➕ Width added: '{char}' (code {hex(code)}) width = {new_width}")
                            else:
                                widths[index] = new_width
                                log.append(f"📝 Width replaced: '{char}' (code {hex(code)}) set to {new_width}")
                                
                        font_ref["/Widths"] = widths
                        log.append(f"Final widths array length: {len(widths)}")
                    else:
                        log.append("⚠️ Font has no Widths attribute")
                        
    output_path = os.path.join(output_dir, os.path.basename(pdf_path).replace('.pdf', '_updated.pdf'))
    pdf.save(output_path)
    log.append(f"\n=== Processing complete, saved to: {output_path} ===")
    return output_path


def print_character_stream_mapping(text, encoded_bytes, font_cmap, log_list=None, debug=False):
    """
    Print mapping between characters and their stream encodings.
    
    Args:
        text: The Unicode text
        encoded_bytes: The encoded bytes in the PDF stream
        font_cmap: Font CMap mapping dictionary
        log_list: List to append log messages
        debug: Whether to enable detailed debug output
    """
    msg = []
    for i, char in enumerate(text):
        if i < len(encoded_bytes):
            code = encoded_bytes[i]
            byte_repr = f"{code:02X}"
            msg.append(f"  '{char}' → {byte_repr}")
        
    if log_list is not None:
            log_list.append("\n".join(msg))
    elif debug:
        print("\n".join(msg))


def print_rendering_mapping(font_ref, char, byte_code, log_list=None, debug=False):
    """
    Print mapping between a character and its rendering process.
    
    Args:
        font_ref: Font reference from PDF
        char: Unicode character
        byte_code: Byte code in PDF stream
        log_list: List to append log messages
        debug: Whether to enable detailed debug output
    """
    msg = []
    msg.append(f"  Character: '{char}' (Unicode: U+{ord(char):04X})")
    msg.append(f"  Stream encoding: 0x{byte_code:02X}")
    
    if "/Encoding" in font_ref:
        encoding_name = "Custom"
        if isinstance(font_ref["/Encoding"], pikepdf.Name):
            encoding_name = str(font_ref["/Encoding"])
        msg.append(f"  Encoding: {encoding_name}")
        
    if log_list is not None:
        log_list.append("\n".join(msg))
    elif debug:
            print("\n".join(msg)) 