#!/usr/bin/env python3
"""Extract text from PDF files for forensic analysis."""
import sys
from pathlib import Path

try:
    import pymupdf
except ImportError:
    print("Install: pip install pymupdf")
    sys.exit(1)

def extract_pdf(pdf_path: str, output_path: str = None) -> str:
    """Extract text from PDF. Returns extracted text."""
    doc = pymupdf.open(pdf_path)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(text)
    
    return text

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_pdf.py <pdf_path> [output_path]")
        sys.exit(1)
    
    pdf = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else None
    text = extract_pdf(pdf, out)
    print(f"Extracted {len(text)} chars from {pdf}")
