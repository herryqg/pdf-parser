import os
import re
import shutil
from pathlib import Path

try:
    from googletrans import Translator  # type: ignore
except ImportError:
    raise SystemExit("Please install googletrans: pip install googletrans==4.0.0-rc1")

# Regex pattern to detect Chinese characters
CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]+")

# File extensions to process
EXTENSIONS = {'.py'}

translator = Translator(service_urls=['translate.googleapis.com'])

def translate_line(line: str) -> str:
    """Translate Chinese substring(s) inside a single code line to English."""
    segments = CHINESE_PATTERN.split(line)
    chinese_parts = CHINESE_PATTERN.findall(line)
    if not chinese_parts:
        return line

    translated_parts = []
    for zh in chinese_parts:
        try:
            translated = translator.translate(zh, src='zh-cn', dest='en').text
        except Exception:
            translated = zh  # fallback
        translated_parts.append(translated)

    # Reconstruct line
    new_line = ''
    for i, seg in enumerate(segments):
        new_line += seg
        if i < len(translated_parts):
            new_line += translated_parts[i]
    return new_line


def process_file(path: Path):
    """Translate a single file in-place, keeping a .bak backup."""
    if path.suffix not in EXTENSIONS:
        return
    original_text = path.read_text(encoding='utf-8', errors='ignore').splitlines(keepends=True)
    changed = False
    translated_lines = []
    for line in original_text:
        if CHINESE_PATTERN.search(line):
            new_line = translate_line(line)
            translated_lines.append(new_line)
            if new_line != line:
                changed = True
        else:
            translated_lines.append(line)

    if changed:
        backup_path = path.with_suffix(path.suffix + '.bak')
        shutil.copy2(path, backup_path)
        path.write_text(''.join(translated_lines), encoding='utf-8')
        print(f"Translated {path} (backup saved to {backup_path})")


def walk_project(root: Path):
    for file_path in root.rglob('*'):
        if file_path.is_file() and file_path.suffix in EXTENSIONS and file_path.name != Path(__file__).name:
            process_file(file_path)


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent
    walk_project(project_root)
    print("Translation completed.") 