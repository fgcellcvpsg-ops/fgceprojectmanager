# export_tools.py
import io
from datetime import datetime

try:
    from weasyprint import HTML, CSS
except ImportError:
    HTML = None
    CSS = None

def build_report_filename(prefix="BAOCAO", fmt="pdf"):
    now = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}-{now}.{fmt}"

def generate_dashboard_pdf_weasy(html, base_url=None, stylesheets=None):
    if HTML is None:
        return None
    return HTML(string=html, base_url=base_url).write_pdf(stylesheets=stylesheets)

def generate_project_detail_pdf_weasy(html, base_url=None, stylesheets=None):
    if HTML is None:
        return None
    return HTML(string=html, base_url=base_url).write_pdf(stylesheets=stylesheets)

def merge_pdfs(pdf_list):
    # Nếu muốn merge nhiều PDF, dùng PyPDF2
    try:
        from PyPDF2 import PdfMerger
        merger = PdfMerger()
        for pdf_bytes in pdf_list:
            merger.append(io.BytesIO(pdf_bytes))
        buf = io.BytesIO()
        merger.write(buf)
        merger.close()
        buf.seek(0)
        return buf.read()
    except ImportError:
        return None

def save_pdf_preview(html, filename="preview.pdf"):
    if HTML is None:
        return None
    pdf_bytes = HTML(string=html).write_pdf()
    with open(filename, "wb") as f:
        f.write(pdf_bytes)
    return filename
