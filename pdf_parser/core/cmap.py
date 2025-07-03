"""CMap parsing and handling functionality for PDF text processing."""

import re
def parse_cmap(cmap_str):
    """
    Parse a PDF CMap string into a mapping dictionary.
    
    Args:
        cmap_str (str): The CMap string from PDF.
        
    Returns:
        dict: A dictionary mapping PDF byte codes to Unicode characters.
    """
    cmap = {}
    for line in cmap_str.splitlines():
        # Match beginbfrange format
        range_match = re.search(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", line)
        if range_match:
            start_hex, end_hex, target_hex = range_match.groups()
            start = int(start_hex, 16)
            end = int(end_hex, 16)
            target = int(target_hex, 16)
            for i in range(start, end + 1):
                if i > 0xFF:
                    continue
                cmap[bytes([i])] = chr(target + (i - start))
            continue

        # Match beginbfchar format
        char_match = re.search(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", line)
        if char_match:
            code_hex, target_hex = char_match.groups()
            code = int(code_hex, 16)
            target = int(target_hex, 16)
            if code > 0xFF:
                # Skip multi-byte encodings
                continue
            cmap[bytes([code])] = chr(target)

    return cmap


def decode_pdf_string(pdf_bytes, cmap):
    """
    Decode PDF encoded text using a CMap.
    
    Args:
        pdf_bytes (bytes): The encoded PDF text bytes.
        cmap (dict): The CMap mapping dictionary.
        
    Returns:
        str: The decoded Unicode text.
    """
    return ''.join(cmap.get(bytes([b]), '?') for b in pdf_bytes)


def encode_pdf_string(unicode_text, cmap):
    """
    Encode Unicode text using a CMap for PDF.
    
    Args:
        unicode_text (str): The Unicode text to encode.
        cmap (dict): The CMap mapping dictionary.
        
    Returns:
        bytes: The encoded PDF bytes.
        
    Raises:
        ValueError: If any character in the text doesn't have a mapping in the CMap.
    """
    reverse = {v: k for k, v in cmap.items()}
    encoded = []
    for c in unicode_text:
        if c not in reverse:
            raise ValueError(f"Character {c} not found in CMap, cannot encode.")
        encoded.append(reverse[c])
    return b''.join(encoded)


def escape_pdf_string(text):
    """
    Add escape characters to PDF text.
    
    Args:
        text (str): The text to escape.
        
    Returns:
        str: The escaped text.
    """
    # Characters that need escaping
    escape_chars = {
        '(': '\\(',
        ')': '\\)',
        '\\': '\\\\',
        '\r': '\\r',
        '\n': '\\n',
        '\t': '\\t',
        '\b': '\\b',
        '\f': '\\f'
    }
    result = ''
    for char in text:
        result += escape_chars.get(char, char)
    return result


def create_tounicode_cmap(font_ref, encoding_name='/WinAnsiEncoding'):
    """
    Create a ToUnicode CMap for a font based on standard encodings.
    
    Args:
        font_ref: The PDF font reference object.
        encoding_name (str): The name of the encoding to use.
        
    Returns:
        str: The CMap string.
    """
    # Define standard encodings
    standard_encodings = {
        '/WinAnsiEncoding': {
            # Standard Windows encoding - this is a simplified version
            32: ' ', 33: '!', 34: '"', 35: '#', 36: '$', 37: '%', 38: '&', 39: "'",
            40: '(', 41: ')', 42: '*', 43: '+', 44: ',', 45: '-', 46: '.', 47: '/',
            48: '0', 49: '1', 50: '2', 51: '3', 52: '4', 53: '5', 54: '6', 55: '7',
            56: '8', 57: '9', 58: ':', 59: ';', 60: '<', 61: '=', 62: '>', 63: '?',
            64: '@', 65: 'A', 66: 'B', 67: 'C', 68: 'D', 69: 'E', 70: 'F', 71: 'G',
            72: 'H', 73: 'I', 74: 'J', 75: 'K', 76: 'L', 77: 'M', 78: 'N', 79: 'O',
            80: 'P', 81: 'Q', 82: 'R', 83: 'S', 84: 'T', 85: 'U', 86: 'V', 87: 'W',
            88: 'X', 89: 'Y', 90: 'Z', 91: '[', 92: '\\', 93: ']', 94: '^', 95: '_',
            96: '`', 97: 'a', 98: 'b', 99: 'c', 100: 'd', 101: 'e', 102: 'f', 103: 'g',
            104: 'h', 105: 'i', 106: 'j', 107: 'k', 108: 'l', 109: 'm', 110: 'n', 111: 'o',
            112: 'p', 113: 'q', 114: 'r', 115: 's', 116: 't', 117: 'u', 118: 'v', 119: 'w',
            120: 'x', 121: 'y', 122: 'z', 123: '{', 124: '|', 125: '}', 126: '~'
        }
    }

    # Use the appropriate encoding
    if encoding_name in standard_encodings:
        encoding = standard_encodings[encoding_name]
    else:
        # Default to WinAnsi if encoding not recognized
        encoding = standard_encodings['/WinAnsiEncoding']

    # Create ToUnicode CMap
    cmap_str = "/CIDInit /ProcSet findresource begin\n"
    cmap_str += "12 dict begin\n"
    cmap_str += "begincmap\n"
    cmap_str += "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
    cmap_str += "/CMapName /Adobe-Identity-UCS def\n"
    cmap_str += "/CMapType 2 def\n"
    cmap_str += "1 begincodespacerange\n<00> <FF>\nendcodespacerange\n"

    # Create bfchar entries
    bfchar_entries = []
    for code, char in encoding.items():
        if 0 <= code <= 255:  # Ensure code is in valid range
            bfchar_entries.append(f"<{code:02X}> <{ord(char):04X}>")

    # Write bfchar
    cmap_str += f"{len(bfchar_entries)} beginbfchar\n"
    for entry in bfchar_entries:
        cmap_str += entry + "\n"
    cmap_str += "endbfchar\nendcmap\n"
    cmap_str += "CMapName currentdict /CMap defineresource pop\nend\nend"

    return cmap_str 