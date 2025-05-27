import pikepdf
import re
import os

def ensure_glyph_and_width(ttf_path, new_chars):
    """
    确保TTF文件中新增字符有对应的glyf和宽度，优先尝试用新增字符自身的glyf和宽度，
    若TTF不包含该字符，则用已有的数字或拉丁字母作fallback，并打印调试信息。
    """
    from fontTools.ttLib import TTFont
    font = TTFont(ttf_path)
    glyf_table = font['glyf']
    hmtx_table = font['hmtx']
    cmap_table = None
    for table in font['cmap'].tables:
        if table.isUnicode():
            cmap_table = table
            break
    if cmap_table is None:
        raise ValueError("找不到cmap表")
    cmap = cmap_table.cmap

    changed = False
    for char in new_chars:
        code = ord(char)
        if code in cmap:
            print(f"✅ 字符 {char} ({code}) 已存在于 cmap，glyf: {cmap[code]}")
            continue  # 已存在
        # 优先用目标字符本身的 glyf
        if code in cmap:
            ref_glyph = cmap[code]
            ref_width, ref_lsb = hmtx_table[ref_glyph]
            print(f"✅ 新增字符 {char} ({code}) 使用自身 glyf {ref_glyph}")
        else:
            # fallback: 找到第一个数字或拉丁字母
            ref_glyph = None
            for fallback in '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                if ord(fallback) in cmap:
                    ref_glyph = cmap[ord(fallback)]
                    ref_width, ref_lsb = hmtx_table[ref_glyph]
                    print(f"⚠️ 字符 {char} ({code}) 缺失，使用 {fallback} 的 glyf {ref_glyph} 作为 fallback")
                    break
            if not ref_glyph:
                ref_glyph = list(hmtx_table.keys())[0]
                ref_width, ref_lsb = hmtx_table[ref_glyph]
                print(f"⚠️ 字符 {char} ({code}) 及 fallback 均缺失，使用首个 glyf {ref_glyph}")
        new_glyph = f"uni{code:04X}"
        glyf_table[new_glyph] = glyf_table[ref_glyph]
        hmtx_table[new_glyph] = (ref_width, ref_lsb)
        cmap[code] = new_glyph
        changed = True

    if changed:
        font.save(ttf_path)




def parse_cmap(cmap_str):
    cmap = {}
    for line in cmap_str.splitlines():
        # 匹配 beginbfrange 格式
        range_match = re.search(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", line)
        if range_match:
            start_hex, end_hex, target_hex = range_match.groups()
            start = int(start_hex, 16)
            end = int(end_hex, 16)
            target = int(target_hex, 16)
            for i in range(start, end + 1):
                cmap[bytes([i])] = chr(target + (i - start))
            continue

        # 匹配 beginbfchar 格式
        char_match = re.search(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", line)
        if char_match:
            code_hex, target_hex = char_match.groups()
            code = int(code_hex, 16)
            target = int(target_hex, 16)
            cmap[bytes([code])] = chr(target)

    return cmap

def decode_pdf_string(pdf_bytes, cmap):
    return ''.join(cmap.get(bytes([b]), '?') for b in pdf_bytes)

def encode_pdf_string(unicode_text, cmap):
    reverse = {v: k for k, v in cmap.items()}
    encoded = []
    for c in unicode_text:
        if c not in reverse:
            raise ValueError(f"字符 {c} 在 cmap 中未找到映射，无法编码。")
        encoded.append(reverse[c])
    return b''.join(encoded)

def escape_pdf_string(text):
    """为PDF文本添加转义符"""
    # 需要转义的字符
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




def get_font_cmaps_from_reference(reference_pdf):
    """从PDF中获取完整的字体映射表"""
    pdf = pikepdf.open(reference_pdf)
    font_cmaps = {}
    for page in pdf.pages:
        if "/Resources" not in page or "/Font" not in page["/Resources"]:
            continue
        font_dict = page["/Resources"]["/Font"]
        font_names = [str(name) for name in font_dict if str(name).startswith("/TT")]
        for font_name in font_names:
            font_ref = font_dict[pikepdf.Name(font_name)]
            if "/ToUnicode" not in font_ref:
                continue
            cmap_bytes = font_ref["/ToUnicode"].read_bytes()
            cmap_str = cmap_bytes.decode("utf-8", errors="ignore")
            font_cmaps[font_name] = parse_cmap(cmap_str)
    return font_cmaps

def count_common_mappings(cmap1, cmap2):
    """计算两个映射表中相同映射的数量"""
    common = 0
    for k, v in cmap1.items():
        if k in cmap2 and cmap2[k] == v:
            common += 1
    return common


def find_best_matching_fonts(cmaps1, cmaps2, min_similarity=0.2, top_k=3):
    """
    根据 Jaccard 相似度匹配两个 PDF 的字体映射。

    :param cmaps1: 第一个 PDF 的 font → cmap 映射
    :param cmaps2: 第二个 PDF 的 font → cmap 映射
    :param min_similarity: 最低相似度阈值（0~1），于此不匹配
    :param top_k: 每个字体最多保留 top_k 个相似度最高的匹配项
    :return: List of tuples: (font1, font2, similarity)
    """
    matches = []

    for name1, cmap1 in cmaps1.items():
        set1 = set(cmap1.items())
        best_local = []

        for name2, cmap2 in cmaps2.items():
            set2 = set(cmap2.items())
            if not set1 or not set2:
                continue

            intersection = set1 & set2
            union = set1 | set2
            similarity = len(intersection) / len(union)

            if similarity >= min_similarity:
                best_local.append((name1, name2, similarity, len(intersection), len(union)))

        # 排序本字体的候选匹配并取 top_k
        best_local.sort(key=lambda x: x[2], reverse=True)
        matches.extend(best_local[:top_k])

    # 最终结果整排序
    matches.sort(key=lambda x: x[2], reverse=True)
    return matches

def merge_cmaps(original_cmap, additional_cmap, font_name="", log_list=None):
    """
    合并字体映射，只补全缺失映射项，避免覆盖已有的原始映射。
    - 若尝试覆盖原始映射，将发出警告。
    """
    merged = original_cmap.copy()
    overwritten = 0
    added = 0

    for k, v in additional_cmap.items():
        if k in merged:
            if merged[k] != v:
                overwritten += 1
                if log_list is not None:
                    log_list.append(f"⚠️ 警告: 字体 {font_name} 中编码 {k.hex()} 已映射为 {merged[k]}，参考映射想改为 {v}，已忽略。")
        else:
            merged[k] = v
            added += 1

    if log_list is not None:
        log_list.append(f"🧩 映射合并完成：保留原有 {len(original_cmap)}，新增 {added}，冲突跳过 {overwritten}")
    return merged

def update_pdf_font_mapping(pdf_path, font_name, new_cmap):
    import os
    import tempfile
    from fontTools import subset
    from fontTools.ttLib import TTFont
    import pikepdf

    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n=== 开始处理字体 {font_name} ===")
    pdf = pikepdf.open(pdf_path)
    for page in pdf.pages:
        if "/Resources" in page and "/Font" in page["/Resources"]:
            font_dict = page["/Resources"]["/Font"]
            if pikepdf.Name(font_name) in font_dict:
                font_ref = font_dict[pikepdf.Name(font_name)]
                if "/ToUnicode" in font_ref:
                    # ====== 生成 ToUnicode CMap ======
                    cmap_str = "/CIDInit /ProcSet findresource begin\n"
                    cmap_str += "12 dict begin\n"
                    cmap_str += "begincmap\n"
                    cmap_str += "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
                    cmap_str += "/CMapName /Adobe-Identity-UCS def\n"
                    cmap_str += "/CMapType 2 def\n"
                    cmap_str += "1 begincodespacerange\n<00> <FF>\nendcodespacerange\n"

                    sorted_cmap = sorted(new_cmap.items())
                    cmap_str += f"{len(sorted_cmap)} beginbfchar\n"
                    for k, v in sorted_cmap:
                        print(f"📌 CMap映射: <{k.hex().upper()}> -> {v} (U+{ord(v):04X})")
                        cmap_str += f"<{k.hex().upper()}> <{ord(v):04X}>\n"
                    cmap_str += "endbfchar\nendcmap\n"
                    cmap_str += "CMapName currentdict /CMap defineresource pop\nend\nend"

                    font_ref["/ToUnicode"] = pikepdf.Stream(pdf, cmap_str.encode())

                    # ====== 生成并嵌入子集TTF ======
                    font_path = os.path.join(output_dir, font_name.replace("/", "") + ".ttf")
                    if not os.path.exists(font_path):
                        print(f"⚠️ 未找到字体文件: {font_path}")
                        continue

                    used_chars = set(new_cmap.values())
                    print(f"🛠️ 生成子集字体, 包含字符: {used_chars}")
                    unicodes = [ord(c) for c in used_chars]

                    with tempfile.NamedTemporaryFile(suffix=".ttf", delete=False, dir=output_dir) as temp_subset:
                        subset_path = temp_subset.name

                    options = subset.Options()
                    options.set(layout_features='*')
                    options.retain_gids = True
                    options.passthrough_tables = True
                    font = subset.load_font(font_path, options)
                    subsetter = subset.Subsetter(options)
                    subsetter.populate(unicodes=unicodes)
                    subsetter.subset(font)
                    font.save(subset_path)
                    print(f"📄 子集字体保存于: {subset_path}")

                    with open(subset_path, "rb") as f:
                        font_stream = pikepdf.Stream(pdf, f.read())
                        if "/FontDescriptor" in font_ref:
                            descriptor = font_ref["/FontDescriptor"]
                            descriptor["/FontFile2"] = font_stream
                            print(f"✅ 字体嵌入成功: {font_name}")
                        else:
                            print(f"⚠️ {font_name} 没有FontDescriptor，无法嵌入字体")
                    os.unlink(subset_path)

                    # ====== 字体宽度处理 (只新增) ======
                    if "/Widths" in font_ref:
                        font_ref["/FirstChar"] = 0
                        print(f"🛠️ 强制设置 FirstChar 为 0，允许低位编码写入 Widths")
                        widths = font_ref["/Widths"]
                        first_char = font_ref.get("/FirstChar", 0)
                        original_len = len(widths)

                        ttf_font = TTFont(font_path)
                        cmap_table = next((t for t in ttf_font['cmap'].tables if t.isUnicode()), None)

                        inv_cmap = {k[0]: v for k, v in new_cmap.items()}

                        # 仅基于已有 PDF 中定义的字符计算宽度比例，避免连锁偏差
                        char_width_ratios = {}
                        for i in range(original_len):
                            code = first_char + i
                            pdf_width = widths[i]
                            char = inv_cmap.get(code)
                            if not char:
                                continue
                            char_unicode = ord(char)
                            char_glyph = cmap_table.cmap.get(char_unicode) if cmap_table else None
                            if char_glyph:
                                ttf_width = ttf_font['hmtx'][char_glyph][0]
                                if ttf_width > 0:
                                    char_width_ratios[char_unicode] = (pdf_width / ttf_width)*0.96

                        default_ratio = sum(char_width_ratios.values()) / len(char_width_ratios) if char_width_ratios else 1.0

                        for code, char in inv_cmap.items():
                            index = code - first_char
                            # 新增检测: 若 index 为负或 code 超出范围，跳过
                            if code > 255 or code < first_char:
                                print(f"⚠️ 跳过非法编码: {code} (超出范围或小于 FirstChar {first_char})")
                                continue
                            char_unicode = ord(char)
                            char_glyph = cmap_table.cmap.get(char_unicode) if cmap_table else None
                            if 0 <= index < original_len:
                                existing_width = widths[index]
                                print(f"🔄 已有字符 '{char}' (编码 {hex(code)}) 宽度为: {existing_width}")
                                continue

                            if char_glyph:
                                ttf_width = ttf_font['hmtx'][char_glyph][0]
                                ratio = char_width_ratios.get(char_unicode, default_ratio)
                                new_width = int(round(ttf_width * ratio))
                                print(f"✅ 新增字符宽度: '{char}' (U+{char_unicode:04X}), TTF宽度: {ttf_width}, 比例: {ratio:.3f} → PDF宽度: {new_width}")
                            else:
                                new_width = int(round(sum(widths) / len(widths)))
                                print(f"⚠️ 无TTF支持: '{char}' (U+{char_unicode:04X}), 使用平均宽度: {new_width}")

                            if index >= len(widths):
                                default_width = int(round(sum(widths) / len(widths)))
                                while len(widths) < index:
                                    widths.append(default_width)
                                    print(f"🔧 填充缺失宽度至 index={len(widths)-1}, 默认宽度: {default_width}")
                                widths.append(new_width)
                                print(f"➕ 宽度添加完成: '{char}' (编码 {hex(code)}) 宽度为 {new_width}")
                            else:
                                widths[index] = new_width
                                print(f"📝 覆盖宽度: '{char}' (编码 {hex(code)}) 设为 {new_width}")

                        font_ref["/Widths"] = widths
                        print(f"最终宽度数组长度：{len(widths)}")
                    else:
                        print("⚠️ 字体无Widths属性")

    output_path = os.path.join(output_dir, os.path.basename(pdf_path).replace('.pdf', '_updated.pdf'))
    pdf.save(output_path)
    print(f"\n=== 处理完成，保存到: {output_path} ===")
    return output_path

def analyze_font_mappings(input_pdf, output_txt="font_mapping_analysis.txt"):
    """分析PDF字体映射并输出到文本文件"""
    input_cmaps = get_font_cmaps_from_reference(input_pdf)
    analysis = ["=== font report ===", f"\ninput: {input_pdf}", "\n--- input PDF full mappings ---"]
    for font_name, cmap in input_cmaps.items():
        analysis.append(f"\nfont: {font_name}")
        for k, v in sorted(cmap.items()):
            analysis.append(f"  {k.hex()} → {v}")
        analysis.append(f"mappings: {len(cmap)}")
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    output_txt_path = os.path.join(output_dir, output_txt)
    with open(output_txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(analysis))
    print(f"📊 字体映射分析已保存到: {output_txt_path}")

def print_character_stream_mapping(text, encoded_bytes, cmap, log_list=None):
    """
    打印字符流映射表，显示每个字符的：
    1. 字符本身
    2. Unicode编码
    3. PDF中的字节编码
    4. 原始字符流中的表示
    """
    mapping_info = []
    mapping_info.append("\n=== 字符流映射表 ===")
    mapping_info.append("字符 | Unicode | PDF字节 | 原始流")
    mapping_info.append("-" * 50)

    for i, char in enumerate(text):
        byte = encoded_bytes[i:i+1]
        byte_hex = byte.hex().upper()
        unicode_hex = f"U+{ord(char):04X}"
        stream_repr = repr(bytes([byte[0]]).decode('latin1'))
        mapping_info.append(f"{char} | {unicode_hex} | {byte_hex} | {stream_repr}")
    
    mapping_info.append("=" * 50)
    
    # 打印到控制台和日志
    for line in mapping_info:
        print(line)
        if log_list is not None:
            log_list.append(line)

def print_rendering_mapping(font_ref, char, code, log_list=None):
    """
    打印字符的完整渲染映射过程
    """
    mapping_info = []
    mapping_info.append(f"\n=== 字符 '{char}' 的渲染映射过程 ===")
    
    # 1. 显示字符基本信息
    mapping_info.append(f"字符: {char}")
    mapping_info.append(f"Unicode: U+{ord(char):04X}")
    mapping_info.append(f"PDF字节: {code:02X}")
    
    # 2. 显示字体编码信息
    if "/Encoding" in font_ref:
        encoding = font_ref["/Encoding"]
        if isinstance(encoding, dict):
            if "/BaseEncoding" in encoding:
                mapping_info.append(f"基础编码: {encoding['/BaseEncoding']}")
            if "/Differences" in encoding:
                mapping_info.append(f"差异编码: {encoding['/Differences']}")
                # 显示差异编码的映射关系
                differences = encoding["/Differences"]
                if isinstance(differences, list):
                    mapping_info.append("\n编码映射关系:")
                    current_code = None
                    for item in differences:
                        if isinstance(item, int):
                            current_code = item
                        elif isinstance(item, str) and current_code is not None:
                            mapping_info.append(f"  {current_code:02X} -> {item}")
                            current_code += 1
        else:
            mapping_info.append(f"编码数组: {encoding}")
    
    # 3. 显示字体描述符信息
    if "/FontDescriptor" in font_ref:
        descriptor = font_ref["/FontDescriptor"]
        mapping_info.append("\n字体描述符:")
        for key in ["/FontName", "/FontFamily", "/FontStretch", "/FontWeight"]:
            if key in descriptor:
                mapping_info.append(f"  {key}: {descriptor[key]}")
    
    # 4. 显示字形信息
    if "/FirstChar" in font_ref and "/LastChar" in font_ref:
        first_char = font_ref["/FirstChar"]
        last_char = font_ref["/LastChar"]
        mapping_info.append(f"\n字形范围: {first_char} - {last_char}")
    
    if "/Widths" in font_ref:
        widths = font_ref["/Widths"]
        if code >= first_char and code <= last_char:
            width = widths[code - first_char]
            mapping_info.append(f"字形宽度: {width}")
    
    mapping_info.append("=" * 50)
    
    # 打印到控制台和日志
    for line in mapping_info:
        print(line)
        if log_list is not None:
            log_list.append(line)

def get_font_encoding_mapping(font_ref):
    """
    获取字体的编码映射关系
    """
    encoding_map = {}
    if "/Encoding" in font_ref:
        encoding = font_ref["/Encoding"]
        if isinstance(encoding, dict) and "/Differences" in encoding:
            differences = encoding["/Differences"]
            if isinstance(differences, list):
                current_code = None
                for item in differences:
                    if isinstance(item, int):
                        current_code = item
                    elif isinstance(item, str) and current_code is not None:
                        encoding_map[current_code] = item
                        current_code += 1
    return encoding_map

def is_safe_code(code):
    """
    判断编码是否安全（不会直接显示为可读字符）
    """
    # ASCII可打印字符区间 (0x21-0x7E)
    if 0x21 <= code <= 0x7E:
        return False
    # 控制字符区间 (0x00-0x20)
    if 0x00 <= code <= 0x20:
        return False
    return True

def replace_text(input_pdf, output_pdf, target_text, replacement_text, ttf_file=None, log_path="replace_log.txt"):
    if target_text == replacement_text:
        print(f"⚠️ 替换文本与原文本相同，跳过处理")
        return
    import shutil
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)

    log = []
    input_cmaps = get_font_cmaps_from_reference(input_pdf)
    font_cmaps = input_cmaps
    log.append("📚 使用当前PDF字体映射")
    print("📚 使用当前PDF字体映射")
    pdf = pikepdf.open(input_pdf)
    page = pdf.pages[0]
    font_dict = page["/Resources"]["/Font"]
    # 修改字体名称匹配模式，匹配所有TT字体
    font_names = [str(name) for name in font_dict if str(name).startswith("/TT")]
    
    # 为所有TT字体创建编码映射
    font_encoding_maps = {}
    for font_name in font_names:
        font_ref = font_dict[pikepdf.Name(font_name)]
        font_encoding_maps[font_name] = get_font_encoding_mapping(font_ref)
        log.append(f"\n📊 字体 {font_name} 编码映射表:")
        print(f"\n📊 字体 {font_name} 编码映射表:")
        for code, glyph in sorted(font_encoding_maps[font_name].items()):
            log.append(f"  {code:02X} -> {glyph}")
            print(f"  {code:02X} -> {glyph}")
    
    if ttf_file:
        for font_name in font_names:
            target_font_path = os.path.join(output_dir, font_name.replace("/", "") + ".ttf")
            try:
                shutil.copy2(ttf_file, target_font_path)
                log.append(f"📦 已复制TTF文件 {ttf_file} 到 {target_font_path}")
                print(f"📦 已复制TTF文件 {ttf_file} 到 {target_font_path}")
            except Exception as e:
                log.append(f"❌ 复制TTF失败: {e}")
                print(f"❌ 复制TTF失败: {e}")
    content_objects = page['/Contents']
    combined = b''.join(obj.read_bytes() for obj in content_objects) if isinstance(content_objects, pikepdf.Array) else content_objects.read_bytes()
    content_raw = combined.decode("latin1")
    # 支持 Tj/TJ 指令（数组和字符串），扩展正则
    text_pattern = re.compile(r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]')
    font_pattern = re.compile(r'/([A-Za-z0-9]+)\s+\d+\s+Tf')
    segments = []
    current_pos = 0
    current_font = None
    # 支持Tj/TJ指令
    content_pattern = r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]|/[A-Za-z0-9]+\s+\d+\s+Tf|(?:[-\d.]+\s+){5}[-\d.]+\s+Tm'
    for match in re.finditer(content_pattern, content_raw):
        if match.start() > current_pos:
            segments.append(content_raw[current_pos:match.start()])
        segments.append(match.group(0))
        current_pos = match.end()
        font_match = font_pattern.search(match.group(0))
        if font_match:
            current_font = '/' + font_match.group(1)
    if current_pos < len(content_raw):
        segments.append(content_raw[current_pos:])
    changed = False
    new_segments = []
    modified_fonts = set()
    for segment in segments:
        font_match = font_pattern.search(segment)
        if font_match:
            current_font = '/' + font_match.group(1)
            new_segments.append(segment)
            continue
        text_match = text_pattern.search(segment)
        if text_match and current_font in font_cmaps:
            # 判断是Tj还是TJ
            is_tj = segment.strip().endswith('TJ')
            if is_tj:
                inner_text = text_match.group(2)
            else:
                inner_text = text_match.group(1)
            text_content_for_decode = inner_text.replace('\\', '')
            encoded_bytes = text_content_for_decode.encode("latin1")
            decoded_text = decode_pdf_string(encoded_bytes, font_cmaps[current_font])
            if decoded_text == target_text:
                log.append(f"🧾 ({current_font}) 替换: {decoded_text} → {replacement_text}")
                print(f"🧾 ({current_font}) 替换: {decoded_text} → {replacement_text}")
                
                # 打印原始文本的字符流映射表
                log.append("\n📊 原始文本字符流映射:")
                print("\n📊 原始文本字符流映射:")
                print_character_stream_mapping(decoded_text, encoded_bytes, font_cmaps[current_font], log)
                
                # 打印原始字符流（包含转义字符）
                log.append(f"  📝 原始字符流: {repr(text_content_for_decode)}")
                print(f"  📝 原始字符流: {repr(text_content_for_decode)}")
                
                # 打印原始文本的渲染映射过程
                font_ref = font_dict[pikepdf.Name(current_font)]
                encoding_map = get_font_encoding_mapping(font_ref)
                
                log.append("\n📊 字体编码映射表:")
                print("\n📊 字体编码映射表:")
                for code, glyph in sorted(encoding_map.items()):
                    log.append(f"  {code:02X} -> {glyph}")
                    print(f"  {code:02X} -> {glyph}")
                
                log.append("\n📊 原始文本渲染映射过程:")
                print("\n📊 原始文本渲染映射过程:")
                for i, char in enumerate(decoded_text):
                    print_rendering_mapping(font_ref, char, encoded_bytes[i], log)
                
                existing_cmap = font_cmaps[current_font]
                used_codes = set(k[0] for k in existing_cmap.keys())
                char_to_code = {v: k[0] for k, v in existing_cmap.items()}
                new_codes = []
                allocated_chars = {}
                for char in replacement_text:
                    if char in allocated_chars:
                        code = allocated_chars[char]
                    elif char in char_to_code:
                        code = char_to_code[char]
                        allocated_chars[char] = code
                    else:
                        # 从0x7F开始查找安全编码
                        start_code = 0x7F
                        found = False
                        
                        # 遍历所有可能的编码
                        for code_candidate in range(start_code, 0x100):
                            # 检查所有TT字体的编码映射
                            is_safe = True
                            for font_name, encoding_map in font_encoding_maps.items():
                                if code_candidate in encoding_map:
                                    is_safe = False
                                    break
                            
                            if code_candidate not in used_codes and is_safe_code(code_candidate) and is_safe:
                                key = bytes([code_candidate])
                                existing_cmap[key] = char
                                used_codes.add(code_candidate)
                                code = code_candidate
                                allocated_chars[char] = code
                                modified_fonts.add(current_font)
                                log.append(f"  🔄 为字符 '{char}' 分配安全编码: 0x{code:02X}")
                                print(f"  🔄 为字符 '{char}' 分配安全编码: 0x{code:02X}")
                                found = True
                                break
                        
                        if not found:
                            raise RuntimeError(f"❌ 无法为字符 '{char}' 找到安全编码")
                    new_codes.append(code)
                
                # 打印替换文本的字符流映射表
                new_encoded = bytes(new_codes)
                log.append("\n📊 替换文本字符流映射:")
                print("\n📊 替换文本字符流映射:")
                print_character_stream_mapping(replacement_text, new_encoded, font_cmaps[current_font], log)
                
                # 打印替换文本的渲染映射过程
                log.append("\n📊 替换文本渲染映射过程:")
                print("\n📊 替换文本渲染映射过程:")
                for i, char in enumerate(replacement_text):
                    print_rendering_mapping(font_ref, char, new_encoded[i], log)
                
                # 增强日志：记录新编码
                new_hex = ' '.join(f'{c:02X}' for c in new_codes)
                log.append(f"  ✨ 新编码: {new_hex}")
                print(f"  ✨ 新编码: {new_hex}")
                
                # 生成新的编码字符串
                new_encoded_str = escape_pdf_string(new_encoded.decode("latin1"))
                
                # 打印新字符流（包含转义字符）
                log.append(f"  📝 新字符流: {repr(new_encoded_str)}")
                print(f"  📝 新字符流: {repr(new_encoded_str)}")
                
                # TJ: [ ... ]TJ，Tj: ( ... )Tj
                if is_tj:
                    segment = segment.replace(f"[{text_match.group(2)}]", f"[({new_encoded_str})]")
                else:
                    segment = segment.replace(f"({text_match.group(1)})", f"({new_encoded_str})")
                changed = True
        new_segments.append(segment)
    content_raw = ''.join(new_segments)
    if changed:
        for font_name in modified_fonts:
            update_pdf_font_mapping(input_pdf, font_name, font_cmaps[font_name])
        updated_pdf_path = os.path.join(output_dir, os.path.basename(input_pdf).replace('.pdf', '_updated.pdf'))
        updated_pdf = pikepdf.open(updated_pdf_path)
        page = updated_pdf.pages[0]
        page['/Contents'] = pikepdf.Stream(updated_pdf, content_raw.encode("latin1"))
        output_pdf_path = os.path.join(output_dir, os.path.basename(output_pdf))
        updated_pdf.save(output_pdf_path)
        log.append(f"💾 保存修改到: {output_pdf_path}")
        print(f"💾 保存修改到: {output_pdf_path}")
    else:
        log.append("⚠️ 未发现匹配文本，未做替换。")
        print("⚠️ 未发现匹配文本，未做替换。")
    log_path_out = os.path.join(output_dir, os.path.basename(log_path))
    with open(log_path_out, "w", encoding="utf-8") as f:
        f.write('\n'.join(log))
    print(f"📘 日志写入: {log_path_out}")

replace_text(
    input_pdf="./inputs/MX650.pdf",
    output_pdf="output.pdf",
    target_text="TH-75MX650K",
    replacement_text="9",
    ttf_file="fonts/PUDSSB.ttf"
)
