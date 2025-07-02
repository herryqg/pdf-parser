# PDF Parser and Text Replacement Tool

A powerful Python library for parsing and modifying text content in PDF files with precise character-level control. This tool allows you to replace text in PDF documents while preserving the original formatting and layout.

## Features

- **Precise Text Replacement**: Replace specific text instances in PDF documents
- **Text Search**: Search for text in PDF documents with contextual results and exact coordinates
- **Text Extraction**: Parse and extract all replaceable text from PDF pages with position information
- **Font-Aware Processing**: Handles complex font encoding and character mappings
- **Multi-instance Support**: Replace single or all instances of target text
- **Character Validation**: Verifies replacement text compatibility with document fonts
- **Font Analysis**: Analyze and debug font mappings in PDF documents
- **Flexible API**: Both functional and class-based interfaces for integration
- **GUI Interface**: Optional graphical interface for interactive text replacement
- **Hierarchical JSON Output**: Groups text instances in a two-level JSON structure for easy processing
- **Nested Text Filtering**: Automatically filters out text boxes that are completely contained within larger text boxes

## Installation

```bash
# From local source
pip install -e .

# From GitHub
pip install git+https://github.com/herryqg/pdf-parser.git

# Dependencies
pip install pikepdf fonttools PyMuPDF
```

## Requirements

- Python 3.7+
- pikepdf (PDF manipulation)
- fonttools (Font analysis and manipulation)
- PyMuPDF (fitz, PDF content extraction)

## Usage

### Command-line Usage

#### Text Replacement

```bash
# Basic text replacement
python -m pdf_parser.example replace --input input.pdf --find "Original text" --replace "New text"

# Replace text on a specific page (0-based index)
python -m pdf_parser.example replace --input input.pdf --find "Original text" --replace "New text" --page 2

# Replace a specific instance of text (0-based index)
python -m pdf_parser.example replace --input input.pdf --find "Original text" --replace "New text" --instance 1

# Control verbosity level (0-3)
python -m pdf_parser.example replace --input input.pdf --find "Original text" --replace "New text" --verbose 2

# Allow automatic insertion of characters not in the font
python -m pdf_parser.example replace --input input.pdf --find "Original text" --replace "New text" --allow-auto-insert
```

#### Text Search

```bash
# Basic text search (searches in all pages)
python -m pdf_parser.example search --input input.pdf --find "Search text"

# Search on a specific page (0-based index)
python -m pdf_parser.example search --input input.pdf --find "Search text" --page 2

# Case-sensitive search
python -m pdf_parser.example search --input input.pdf --find "Search text" --case-sensitive

# Get results in JSON format for further processing
python -m pdf_parser.example search --input input.pdf --find "Search text" --json

# Save JSON results to a specific file (in hierarchical format)
python -m pdf_parser.example search --input input.pdf --find "Search text" --json --json-file results.json
```

#### Text Extraction (Parse)

```bash
# Extract all replaceable text from a specific page
python -m pdf_parser.example parse --input input.pdf --page 2

# Include text coordinates in the output
python -m pdf_parser.example parse --input input.pdf --page 2 --with-coordinates

# Get results in JSON format for further processing
python -m pdf_parser.example parse --input input.pdf --page 2 --json

# Save JSON results to a specific file (in hierarchical format)
python -m pdf_parser.example parse --input input.pdf --page 2 --json --json-file parsed_page.json
```

### Python API

```python
# Method 1: Using the function directly
from pdf_parser.api import replace_pdf_text

success = replace_pdf_text(
    input_pdf="input.pdf",
    output_pdf="output.pdf",
    target_text="Original text",
    replacement_text="New text",
    page_num=0,  # 0-based page index
    instance_index=-1,  # -1 for all instances, or specific index (0-based)
    allow_auto_insert=False,  # Whether to allow inserting characters not in the font
    verbose=1  # Verbosity level (0-3)
)

# Method 2: Using the class-based API
from pdf_parser.api import PDFTextReplacer

# Create an instance of the replacer
replacer = PDFTextReplacer(debug=False, verbose=1)

# Replace text
success = replacer.replace_text(
    input_pdf="input.pdf",
    output_pdf="output.pdf",
    target_text="Original text",
    replacement_text="New text",
    page_num=0,
    instance_index=-1
)

# Search for text (includes coordinate information)
results = replacer.search_text(
    pdf_path="input.pdf",
    search_text="Search text",
    page_num=None,  # None for all pages, or specific page index (0-based)
    case_sensitive=False
)

# Parse all replaceable text from a page (with coordinates)
text_elements = replacer.parse_page_text(
    pdf_path="input.pdf",
    page_num=0  # 0-based page index
)

# Search using the function directly
from pdf_parser.api import search_text_in_pdf

results = search_text_in_pdf(
    pdf_path="input.pdf",
    search_text="Search text",
    page_num=None,  # None for all pages, or specific page index (0-based)
    case_sensitive=False
)

# Parse page text using the function directly
from pdf_parser.api import parse_page_text

text_elements = parse_page_text(
    pdf_path="input.pdf",
    page_num=0  # 0-based page index
)

# Analyze font mappings
replacer.analyze_fonts("input.pdf", "font_analysis.txt")

# Get font CMaps directly
font_cmaps = replacer.get_font_cmaps("input.pdf")
```

## How It Works

The PDF Parser processes documents in several steps:

1. **Font Analysis**: Extracts and analyzes font encodings and CMaps from the PDF
2. **Text Search**: Locates the target text in the PDF content stream using pattern matching
3. **Character Validation**: Verifies that all characters in the replacement text are available in the document's fonts
4. **Encoding**: Properly encodes the replacement text using the document's font encoding
5. **Content Update**: Modifies the PDF content stream with the new encoded text

## Project Structure

```
pdf-parser/
├── pdf_parser/                # Main package
│   ├── __init__.py            # Package initialization
│   ├── api.py                 # Public API interface
│   ├── example.py             # Command-line example script
│   ├── core/                  # Core functionality
│   │   ├── __init__.py
│   │   ├── cmap.py            # CMap parsing and manipulation
│   │   └── replacer.py        # Text replacement engine
│   ├── fonts/                 # Font handling
│   │   ├── __init__.py
│   │   ├── analysis.py        # Font analysis tools
│   │   └── embedding.py       # Font embedding utilities
│   └── utils/                 # Utility functions
│       └── ...
├── pdf_gui.py                 # Optional GUI interface
├── setup.py                   # Package installation configuration
└── README.md                  # Documentation
```

## Returned Data Structure

### Search Results

The search function returns a list of dictionaries with the following structure:

```python
[
  {
    "page": 0,                    # 0-based page index
    "text": "Search text",        # The matched text
    "context": "... surrounding text ...",  # Context around the match
    "rect": {                     # Text rectangle coordinates
      "x0": 100.0,                # Left position
      "y0": 200.0,                # Top position
      "x1": 150.0,                # Right position
      "y1": 220.0                 # Bottom position
    },
    "block_order": 3              # Order in the text flow
  },
  # ...more results
]
```

### Parse Results

The parse function returns a list of dictionaries with the following structure:

```python
[
  {
    "text": "Extracted text",     # The extracted text content
    "rect": {                     # Text rectangle coordinates
      "x0": 100.0,                # Left position
      "y0": 200.0,                # Top position
      "x1": 150.0,                # Right position
      "y1": 220.0                 # Bottom position
    },
    "font": "/F1",                # Font name (if available)
    "source": "content_stream"    # Source of extraction (pymupdf or content_stream)
  },
  # ...more text elements
]
```

## Character Validation

By default, the tool validates that all characters in the replacement text are available in the PDF's fonts:

- If a character is missing from the font, the replacement process will be canceled
- All missing characters will be reported in the log
- With `allow_auto_insert=True`, the tool can attempt to add missing characters to the font

## Logging and Verbosity

The tool supports different verbosity levels:

- **Level 0**: Errors only
- **Level 1**: Standard output (errors, warnings, basic info)
- **Level 2**: Detailed output (includes data about fonts and character mappings)
- **Level 3**: Debug output (comprehensive processing information)

## Limitations

- Only supports replacing text where the font has a ToUnicode CMap or can be mapped
- Characters in the replacement text must be available in the PDF's fonts (unless auto-insert is enabled)
- Cannot change text layout or formatting, only the content
- Not suitable for scanned PDFs or text stored as images
- PDF structure must conform to standard specifications

## Troubleshooting

If replacement fails:

1. Check if the target text exists exactly as specified (case-sensitive)
2. Verify if the replacement text contains characters not available in the document's fonts
3. Increase verbosity level to get more detailed information
4. Try with `--allow-auto-insert` if the issue is related to missing characters

## License

[MIT License](LICENSE) - Feel free to use, modify, and distribute as needed.

## JSON Output Format

When using the `--json` option, the tool outputs a hierarchical JSON structure with text content as the primary keys, and details as a list of sub-elements:

```json
{
  "Example text 1": [
    {
      "rect": {
        "x0": 100.0,
        "y0": 200.0,
        "x1": 150.0,
        "y1": 220.0
      },
      "font": "/F1",
      "encoded_bytes": "736f6d652062797465732068657265",
      "instance_index": 0
    },
    {
      "rect": {
        "x0": 300.0,
        "y0": 400.0,
        "x1": 350.0,
        "y1": 420.0
      },
      "font": "/F2",
      "encoded_bytes": "6f74686572206279746573",
      "instance_index": 1
    }
  ],
  "Example text 2": [
    {
      "rect": {
        "x0": 200.0,
        "y0": 300.0,
        "x1": 250.0,
        "y1": 320.0
      },
      "font": "/F3",
      "encoded_bytes": "62797465732076616c756573",
      "instance_index": 0
    }
  ]
}
```

This format groups identical text occurrences together, making it easier to process multiple instances of the same text. Key features:

- Each identical text instance has its own entry with unique coordinates
- The `instance_index` field tracks the occurrence order in the document
- Coordinates (`rect`) are matched with text instances in the correct order
- Multiple occurrences of identical text (like "40V5C") each get their own accurate coordinates
- Nested text boxes are filtered out - smaller text boxes completely contained within larger ones are removed
- Forward-only coordinate matching ensures each text instance only matches with unprocessed positions in the document