import os
from src.ingestion.parsers.base import BaseParser
from src.ingestion.parsers.markdown import MarkdownDocumentParser
from src.ingestion.parsers.pdf import PDFDocumentParser
from src.ingestion.parsers.docx import DocxDocumentParser
from src.ingestion.parsers.xlsx import ExcelCSVDocumentParser

def get_parser(file_path: str) -> BaseParser:
    """
    Factory function to safely route documents to their dedicated formats parser.
    """
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.md':
        return MarkdownDocumentParser()
    elif ext == '.pdf':
        return PDFDocumentParser()
    elif ext in ['.docx', '.doc']:
        return DocxDocumentParser()
    elif ext in ['.xlsx', '.xls', '.csv']:
        return ExcelCSVDocumentParser()
    else:
        raise ValueError(f"Unsupported file extension: '{ext}'")