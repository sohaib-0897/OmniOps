import docx
from typing import List, Dict, Any

def parse_docx_document(file_path: str) -> List[Dict[str, Any]]:
    """Extract paragraphs, headings, and tables from DOCX documents."""
    doc = docx.Document(file_path)
    chunks = []
    
    current_heading = "Document Root"
    current_paragraphs = []
    
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
            
        if para.style.name.startswith("Heading"):
            if current_paragraphs:
                chunks.append({
                    "content": f"## {current_heading}\n" + "\n\n".join(current_paragraphs),
                    "modality": "docx",
                    "page_number": None,
                    "metadata": {"heading": current_heading}
                })
                current_paragraphs = []
            current_heading = text
        else:
            current_paragraphs.append(text)
            
    if current_paragraphs:
        chunks.append({
            "content": f"## {current_heading}\n" + "\n\n".join(current_paragraphs),
            "modality": "docx",
            "page_number": None,
            "metadata": {"heading": current_heading}
        })
        
    # Extract tables
    for t_idx, table in enumerate(doc.tables):
        rows_data = []
        for row in table.rows:
            row_vals = [cell.text.strip() for cell in row.cells]
            rows_data.append(" | ".join(row_vals))
        if rows_data:
            table_md = "\n".join(rows_data)
            chunks.append({
                "content": f"### Table {t_idx + 1}\n" + table_md,
                "modality": "docx",
                "page_number": None,
                "metadata": {"table_index": t_idx + 1}
            })
            
    return chunks
