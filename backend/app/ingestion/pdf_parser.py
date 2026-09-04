import fitz  # PyMuPDF
from typing import List, Dict, Any

def parse_pdf_document(file_path: str) -> List[Dict[str, Any]]:
    """Extract structured pages, text chunks, tables, and page coordinates from PDF."""
    chunks = []
    doc = fitz.open(file_path)
    
    try:
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_num = page_idx + 1
            page_text = page.get_text("text").strip()
            
            # Extract tables if available
            tables = page.find_tables()
            table_markdowns = []
            
            for tab_idx, tab in enumerate(tables):
                try:
                    df = tab.to_pandas()
                    if not df.empty:
                        md_table = df.to_markdown(index=False)
                        table_markdowns.append(md_table)
                except Exception:
                    pass

            combined_content = page_text
            if table_markdowns:
                combined_content += "\n\n### Extracted Tables:\n" + "\n\n".join(table_markdowns)
                
            if not combined_content:
                # No text is better than invented page content. OCR is a later capability.
                continue

            # Split large pages into ~500 token semantic chunks if page is long
            paragraphs = [p.strip() for p in combined_content.split("\n\n") if p.strip()]
            
            current_chunk = []
            current_len = 0
            
            for p in paragraphs:
                current_chunk.append(p)
                current_len += len(p)
                
                if current_len > 1200:
                    chunk_text = "\n\n".join(current_chunk)
                    chunks.append({
                        "content": chunk_text,
                        "page_number": page_num,
                        "modality": "pdf",
                        "metadata": {
                            "page": page_num,
                            "char_count": len(chunk_text),
                            "has_tables": bool(table_markdowns)
                        }
                    })
                    current_chunk = []
                    current_len = 0
                    
            if current_chunk:
                chunk_text = "\n\n".join(current_chunk)
                chunks.append({
                    "content": chunk_text,
                    "page_number": page_num,
                    "modality": "pdf",
                    "metadata": {
                        "page": page_num,
                        "char_count": len(chunk_text),
                        "has_tables": bool(table_markdowns)
                    }
                })
    finally:
        doc.close()
        
    return chunks
