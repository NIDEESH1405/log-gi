from pathlib import Path
import markdown2
from weasyprint import HTML
from datetime import datetime

def markdown_to_pdf(md_content: str, output_path: str):
    """Convert markdown report to PDF"""
    html_content = markdown2.markdown(md_content, extras=["tables", "fenced-code-blocks"])
    full_html = f"""
    <html>
    <head><style>body {{ font-family: Arial; margin: 40px; }}</style></head>
    <body>{html_content}</body>
    </html>
    """
    HTML(string=full_html).write_pdf(output_path)