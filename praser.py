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
    
    # 首先收集这个字体在所有页面中使用的所有字符
    all_font_chars = set()
    # 收集原始CMap，确保我们只添加新的映射，不覆盖现有的
    original_cmap = {}
    
    for page_idx, page in enumerate(pdf.pages):
        if "/Resources" not in page or "/Font" not in page["/Resources"]:
            continue
            
        font_dict = page["/Resources"]["/Font"]
        if pikepdf.Name(font_name) not in font_dict:
            continue
            
        # 获取页面内容
        content_objects = page['/Contents']
        combined = b''.join(obj.read_bytes() for obj in content_objects) if isinstance(content_objects, pikepdf.Array) else content_objects.read_bytes()
        content_raw = combined.decode("latin1")
        
        # 找到所有文本
        text_pattern = re.compile(r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]')
        font_pattern = re.compile(r'/([A-Za-z0-9]+)\s+\d+\s+Tf')
        current_font = None
        
        # 遍历找到使用此字体的所有文本
        for match in re.finditer(r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]|/[A-Za-z0-9]+\s+\d+\s+Tf', content_raw):
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
                
                # 使用当前字体的映射解码
                font_ref = font_dict[pikepdf.Name(font_name)]
                if "/ToUnicode" in font_ref:
                    cmap_bytes = font_ref["/ToUnicode"].read_bytes()
                    cmap_str = cmap_bytes.decode("utf-8", errors="ignore")
                    local_cmap = parse_cmap(cmap_str)
                    # 保存原始映射
                    for k, v in local_cmap.items():
                        original_cmap[k] = v
                    try:
                        decoded_text = decode_pdf_string(encoded_bytes, local_cmap)
                        # 将所有字符添加到集合
                        all_font_chars.update(decoded_text)
                    except:
                        print(f"⚠️ 第{page_idx+1}页某段文本解码失败，已跳过")
    
    print(f"📊 字体 {font_name} 在PDF中使用的所有字符: {', '.join(sorted(all_font_chars))}")
    print(f"📊 原始CMap映射数量: {len(original_cmap)}")
    
    # 合并原始映射和新映射，优先保留原始映射
    merged_cmap = original_cmap.copy()
    added_count = 0
    
    # 只添加新的映射，不修改现有映射
    for k, v in new_cmap.items():
        if k not in merged_cmap:
            merged_cmap[k] = v
            added_count += 1
            print(f"➕ 添加新映射: <{k.hex().upper()}> -> {v} (U+{ord(v):04X})")
    
    print(f"📊 合并后CMap映射数量: {len(merged_cmap)}, 新增: {added_count}")
    
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

                    sorted_cmap = sorted(merged_cmap.items())
                    cmap_str += f"{len(sorted_cmap)} beginbfchar\n"
                    for k, v in sorted_cmap:
                        # if k == b'\x00':
                        #     continue  # 避免 Adobe 报错
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

                    used_chars = set(merged_cmap.values())  # 使用合并后的映射
                    print(f"🛠️ 生成子集字体, 包含字符: {used_chars}")
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
                    options.drop_tables = []  # 保留所有表格，避免 Adobe 报错
                    options.subset_prefix = ""  # 禁用字体子集前缀
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

                            # 从 TTF 中获取真实字体名称
                            from fontTools.ttLib import TTFont
                            ttf = TTFont(font_path)
                            name_record = ttf['name'].getName(1, 3, 1, 1033)
                            real_font_name = name_record.toUnicode() if name_record else "PUDHinban-B"
                            pdf_font_name = pikepdf.Name("/" + real_font_name)

                            descriptor["/FontName"] = pdf_font_name
                            font_ref["/BaseFont"] = pdf_font_name
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

                        # 仅处理新字符的编码->字符映射（只处理新增部分）
                        new_chars_mapping = {}
                        for k, v in new_cmap.items():
                            if k not in original_cmap:
                                new_chars_mapping[k[0]] = v
                        
                        # 存储原始PDF中已有的编码->字符映射
                        original_chars = {}
                        
                        # 仅基于已有 PDF 中定义的字符计算宽度比例，避免连锁偏差
                        char_width_ratios = {}
                        for i in range(original_len):
                            code = first_char + i
                            pdf_width = widths[i]
                            # 从原始映射中找出这个编码对应的字符
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
                                    char_width_ratios[char_unicode] = (pdf_width / ttf_width)*0.97

                        default_ratio = sum(char_width_ratios.values()) / len(char_width_ratios) if char_width_ratios else 1.0

                        # 只处理新增字符的宽度
                        for code, char in new_chars_mapping.items():
                            index = code - first_char
                            # 新增检测: 若 index 为负或 code 超出范围，跳过
                            if code > 255 or code < first_char:
                                print(f"⚠️ 跳过非法编码: {code} (超出范围或小于 FirstChar {first_char})")
                                continue
                                
                            # 判断是否为真正的新增字符
                            is_new_char = True
                            if code in original_chars and original_chars[code] == char:
                                is_new_char = False
                            elif char in all_font_chars:
                                is_new_char = False
                                print(f"ℹ️ 字符 '{char}' 在PDF其他位置已使用此字体，视为已有字符")
                            
                            # 如果不是新字符，跳过处理
                            if not is_new_char:
                                continue
                                
                            char_unicode = ord(char)
                            char_glyph = cmap_table.cmap.get(char_unicode) if cmap_table else None
                            
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
    # 获取 GID（glyph ID）
    from fontTools.ttLib import TTFont
    font_name = font_ref.get("/FontName", None)
    if font_name:
        font_file_path = f"output/{str(font_name).replace('/', '')}.ttf"
        try:
            font = TTFont(font_file_path)
            cmap_table = next((t for t in font['cmap'].tables if t.isUnicode()), None)
            glyph_name = cmap_table.cmap.get(ord(char)) if cmap_table else None
            gid = font.getGlyphID(glyph_name) if glyph_name else None
            if glyph_name and gid is not None:
                mapping_info.append(f"Glyph Name: {glyph_name}")
                mapping_info.append(f"GID: {gid}")
        except Exception as e:
            mapping_info.append(f"⚠️ 无法解析GID: {e}")
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

def replace_text(input_pdf, output_pdf, target_text, replacement_text, page_num=0, ttf_file=None, log_path="replace_log.txt"):
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
    
    # 检查页码是否有效
    if page_num < 0 or page_num >= len(pdf.pages):
        error_msg = f"❌ 无效的页码: {page_num}，PDF共有 {len(pdf.pages)} 页"
        log.append(error_msg)
        print(error_msg)
        with open(os.path.join(output_dir, os.path.basename(log_path)), "w", encoding="utf-8") as f:
            f.write('\n'.join(log))
        return
    
    # 收集整个PDF中所有字体的所有字符
    all_pdf_chars = {}  # 字体名 -> 字符集合
    all_char_codes = {}  # 字体名 -> {字符 -> 编码集合}
    for page_idx, page in enumerate(pdf.pages):
        if "/Resources" not in page or "/Font" not in page["/Resources"]:
            continue
            
        font_dict = page["/Resources"]["/Font"]
        for font_name in [str(name) for name in font_dict if str(name).startswith("/TT")]:
            if font_name not in all_pdf_chars:
                all_pdf_chars[font_name] = set()
                all_char_codes[font_name] = {}
                
            font_ref = font_dict[pikepdf.Name(font_name)]
            
            # 检查是否需要添加ToUnicode CMap
            if "/ToUnicode" not in font_ref:
                log.append(f"⚠️ 字体 {font_name} 缺少ToUnicode CMap，添加默认映射")
                print(f"⚠️ 字体 {font_name} 缺少ToUnicode CMap，添加默认映射")
                
                # 获取字体编码
                encoding_name = '/WinAnsiEncoding'  # 默认
                if "/Encoding" in font_ref:
                    encoding = font_ref["/Encoding"]
                    if isinstance(encoding, pikepdf.Name):
                        encoding_name = str(encoding)
                    elif isinstance(encoding, pikepdf.Dictionary) and "/BaseEncoding" in encoding:
                        encoding_name = str(encoding["/BaseEncoding"])
                
                # 创建并添加ToUnicode CMap
                cmap_str = create_tounicode_cmap(font_ref, encoding_name)
                font_ref["/ToUnicode"] = pikepdf.Stream(pdf, cmap_str.encode())
                
                # 重新提取CMap
                cmap_bytes = font_ref["/ToUnicode"].read_bytes()
                cmap_str = cmap_bytes.decode("utf-8", errors="ignore")
                font_cmap = parse_cmap(cmap_str)
                
                # 添加到映射字典
                if font_name not in font_cmaps:
                    font_cmaps[font_name] = {}
                font_cmaps[font_name].update(font_cmap)
                
                log.append(f"✅ 为字体 {font_name} 添加了 {len(font_cmap)} 个映射")
                print(f"✅ 为字体 {font_name} 添加了 {len(font_cmap)} 个映射")
            elif font_name not in font_cmaps:
                # 提取已有的ToUnicode映射
                cmap_bytes = font_ref["/ToUnicode"].read_bytes()
                cmap_str = cmap_bytes.decode("utf-8", errors="ignore")
                font_cmap = parse_cmap(cmap_str)
                font_cmaps[font_name] = font_cmap
            
            # 获取页面内容
            content_objects = page['/Contents']
            combined = b''.join(obj.read_bytes() for obj in content_objects) if isinstance(content_objects, pikepdf.Array) else content_objects.read_bytes()
            content_raw = combined.decode("latin1")
            
            # 找到所有文本
            text_pattern = re.compile(r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]')
            font_pattern = re.compile(r'/([A-Za-z0-9]+)\s+\d+\s+Tf')
            current_font = None
            
            # 遍历找到使用此字体的所有文本
            for match in re.finditer(r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]|/[A-Za-z0-9]+\s+\d+\s+Tf', content_raw):
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
                        # 将所有字符添加到集合
                        all_pdf_chars[font_name].update(decoded_text)
                        
                        # 记录每个字符对应的编码
                        for i, char in enumerate(decoded_text):
                            if char not in all_char_codes[font_name]:
                                all_char_codes[font_name][char] = set()
                            # 记录字符的原始字节编码
                            all_char_codes[font_name][char].add(encoded_bytes[i])
                    except:
                        print(f"⚠️ 第{page_idx+1}页某段文本解码失败，已跳过")
    
    # 记录每个字体已使用的所有编码
    all_used_codes = {}  # 字体名 -> 编码集合
    for font_name in all_char_codes:
        all_used_codes[font_name] = set()
        for char, codes in all_char_codes[font_name].items():
            all_used_codes[font_name].update(codes)
        log.append(f"📊 字体 {font_name} 已使用的编码: {', '.join(hex(code)[2:].upper() for code in sorted(all_used_codes[font_name]))}")
        print(f"📊 字体 {font_name} 已使用的编码: {', '.join(hex(code)[2:].upper() for code in sorted(all_used_codes[font_name]))}")
    
    # 使用指定页码
    page = pdf.pages[page_num]
    log.append(f"📄 处理第 {page_num + 1} 页")
    print(f"📄 处理第 {page_num + 1} 页")
    
    if "/Resources" not in page or "/Font" not in page["/Resources"]:
        error_msg = f"❌ 第 {page_num + 1} 页没有字体资源"
        log.append(error_msg)
        print(error_msg)
        with open(os.path.join(output_dir, os.path.basename(log_path)), "w", encoding="utf-8") as f:
            f.write('\n'.join(log))
        return
        
    font_dict = page["/Resources"]["/Font"]
    # 修改字体名称匹配模式，匹配所有TT字体
    font_names = [str(name) for name in font_dict if str(name).startswith("/TT")]
    
    if not font_names:
        error_msg = f"❌ 第 {page_num + 1} 页没有TrueType字体"
        log.append(error_msg)
        print(error_msg)
        with open(os.path.join(output_dir, os.path.basename(log_path)), "w", encoding="utf-8") as f:
            f.write('\n'.join(log))
        return
    
    # 检查当前页面的字体是否需要添加ToUnicode CMap
    for font_name in font_names:
        font_ref = font_dict[pikepdf.Name(font_name)]
        if "/ToUnicode" not in font_ref:
            log.append(f"⚠️ 第 {page_num + 1} 页字体 {font_name} 缺少ToUnicode CMap，添加默认映射")
            print(f"⚠️ 第 {page_num + 1} 页字体 {font_name} 缺少ToUnicode CMap，添加默认映射")
            
            # 获取字体编码
            encoding_name = '/WinAnsiEncoding'  # 默认
            if "/Encoding" in font_ref:
                encoding = font_ref["/Encoding"]
                if isinstance(encoding, pikepdf.Name):
                    encoding_name = str(encoding)
                elif isinstance(encoding, pikepdf.Dictionary) and "/BaseEncoding" in encoding:
                    encoding_name = str(encoding["/BaseEncoding"])
            
            # 创建并添加ToUnicode CMap
            cmap_str = create_tounicode_cmap(font_ref, encoding_name)
            font_ref["/ToUnicode"] = pikepdf.Stream(pdf, cmap_str.encode())
            
            # 重新提取CMap
            cmap_bytes = font_ref["/ToUnicode"].read_bytes()
            cmap_str = cmap_bytes.decode("utf-8", errors="ignore")
            font_cmap = parse_cmap(cmap_str)
            
            # 添加到映射字典
            if font_name not in font_cmaps:
                font_cmaps[font_name] = {}
            font_cmaps[font_name].update(font_cmap)
            
            log.append(f"✅ 为字体 {font_name} 添加了 {len(font_cmap)} 个映射")
            print(f"✅ 为字体 {font_name} 添加了 {len(font_cmap)} 个映射")

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

    # 收集所有使用该字体的文本
    all_texts = []
    content_objects = page['/Contents']
    combined = b''.join(obj.read_bytes() for obj in content_objects) if isinstance(content_objects, pikepdf.Array) else content_objects.read_bytes()
    content_raw = combined.decode("latin1")
    text_pattern = re.compile(r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]')
    font_pattern = re.compile(r'/([A-Za-z0-9]+)\s+\d+\s+Tf')
    
    # 首先收集所有文本
    current_pos = 0
    current_font = None
    for match in re.finditer(r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]|/[A-Za-z0-9]+\s+\d+\s+Tf', content_raw):
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

    # 处理替换
    changed = False
    modified_fonts = set()
    new_segments = []
    current_pos = 0
    
    for segment in re.finditer(r'(?:\(((?:[^()\\]|\\.)*)\)|\[((?:[^][\\()]|\\.)*)\])\s*T[Jj]|/[A-Za-z0-9]+\s+\d+\s+Tf|(?:[-\d.]+\s+){5}[-\d.]+\s+Tm', content_raw):
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
                
                # 获取该字体已使用的所有编码
                already_used_codes = all_used_codes.get(current_font, set())
                
                # 确保所有现有字符的映射保持不变
                for char in replacement_text:
                    if char in all_char_codes.get(current_font, {}):
                        # 优先使用该字符在其他文本中的编码
                        codes = list(all_char_codes[current_font][char])
                        if codes:
                            code = codes[0]
                            allocated_chars[char] = code
                            log.append(f"  🔄 使用字符 '{char}' 在PDF中的已有编码: 0x{code:02X}")
                            print(f"  🔄 使用字符 '{char}' 在PDF中的已有编码: 0x{code:02X}")
                    elif char in char_to_code:
                        code = char_to_code[char]
                        allocated_chars[char] = code
                    else:
                        # 从0xB0开始查找安全编码，提高起始位置避免与常用字符冲突
                        start_code = 0xB0
                        found = False

                        # 遍历所有可能的编码
                        for code_candidate in range(start_code, 0x100):
                            # 确保编码未被使用，且不在任何其他字符的编码集中
                            if (code_candidate in used_codes or 
                                code_candidate in already_used_codes):
                                continue
                                
                            # 检查所有TT字体的编码映射
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
                                log.append(f"  🔄 为字符 '{char}' 分配安全编码: 0x{code:02X}")
                                print(f"  🔄 为字符 '{char}' 分配安全编码: 0x{code:02X}")
                                found = True
                                break

                        if not found:
                            # 尝试更高范围的编码
                            for code_candidate in range(0x100, 0x110):
                                # 注意：超出单字节范围需要特殊处理
                                if code_candidate > 0xFF:
                                    log.append(f"⚠️ 尝试使用扩展编码范围: 0x{code_candidate:02X}")
                                    print(f"⚠️ 尝试使用扩展编码范围: 0x{code_candidate:02X}")
                                key = bytes([code_candidate & 0xFF])
                                if key in existing_cmap:
                                    continue
                                existing_cmap[key] = char
                                code = code_candidate & 0xFF
                                allocated_chars[char] = code
                                modified_fonts.add(current_font)
                                log.append(f"  ⚠️ 为字符 '{char}' 分配扩展编码: 0x{code:02X}")
                                print(f"  ⚠️ 为字符 '{char}' 分配扩展编码: 0x{code:02X}")
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
        # 即使没有修改字体映射，也创建更新后的PDF
        if modified_fonts:
            # 有新增字符，需要更新字体映射
            for font_name in modified_fonts:
                update_pdf_font_mapping(input_pdf, font_name, font_cmaps[font_name])
            updated_pdf_path = os.path.join(output_dir, os.path.basename(input_pdf).replace('.pdf', '_updated.pdf'))
            updated_pdf = pikepdf.open(updated_pdf_path)
        else:
            # 没有新增字符，直接基于原PDF创建副本
            log.append(f"ℹ️ 没有新增字符，直接修改内容流")
            print(f"ℹ️ 没有新增字符，直接修改内容流")
            # pikepdf没有copy方法，创建新的PDF
            updated_pdf_path = os.path.join(output_dir, os.path.basename(input_pdf).replace('.pdf', '_updated.pdf'))
            # 关闭当前PDF，重新打开以复制
            pdf.close()
            import shutil
            shutil.copy2(input_pdf, updated_pdf_path)
            updated_pdf = pikepdf.open(updated_pdf_path)
            
        # 更新内容流
        page = updated_pdf.pages[page_num]
        page['/Contents'] = pikepdf.Stream(updated_pdf, content_raw.encode("latin1"))
        output_pdf_path = os.path.join(output_dir, os.path.basename(output_pdf))
        updated_pdf.save(output_pdf_path)
        log.append(f"💾 保存修改到: {output_pdf_path}")
        print(f"💾 保存修改到: {output_pdf_path}")
    else:
        log.append(f"⚠️ 在第 {page_num + 1} 页未发现匹配文本，未做替换。")
        print(f"⚠️ 在第 {page_num + 1} 页未发现匹配文本，未做替换。")
    log_path_out = os.path.join(output_dir, os.path.basename(log_path))
    with open(log_path_out, "w", encoding="utf-8") as f:
        f.write('\n'.join(log))
    print(f"📘 日志写入: {log_path_out}")

def create_tounicode_cmap(font_ref, encoding_name='/WinAnsiEncoding'):
    """
    Create a ToUnicode CMap for the given font based on standard encodings
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

replace_text(
    input_pdf="./inputs/m2.pdf",
    output_pdf="output_page02.pdf",
    target_text="MADE IN THAILAND",
    replacement_text="1234567890abcdefghijklmnopqrstuvwxyz ",
    page_num=0,  # 页码从0开始，0表示第一页
    ttf_file=""
)
