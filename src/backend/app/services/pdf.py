"""PDF generation service using WeasyPrint + Jinja2 templates."""

import os
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from app.config import settings

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
OUTPUT_DIR = Path("/app/generated_pdfs")

_jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))


def generate_receipt_pdf(booking_data: dict) -> str:
    """Generate a receipt PDF for a confirmed booking.

    Args:
        booking_data: dict with keys: booking_id, guest_name, room_number,
            check_in, check_out, nights, total_price, payment_date

    Returns:
        Absolute path to the generated PDF file.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    template = _jinja_env.get_template("receipt.html")
    html_content = template.render(
        villa_name=settings.villa_name,
        villa_address=settings.villa_address,
        villa_phone=settings.villa_phone,
        villa_tax_id=settings.villa_tax_id,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        **booking_data,
    )

    filename = f"receipt_{booking_data['booking_id']}_{datetime.now():%Y%m%d%H%M%S}.pdf"
    output_path = OUTPUT_DIR / filename

    HTML(string=html_content).write_pdf(str(output_path))
    return str(output_path)


def generate_confirmation_pdf(booking_data: dict) -> str:
    """Generate a booking confirmation PDF.

    Same interface as generate_receipt_pdf but uses confirmation template.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    template = _jinja_env.get_template("booking_confirmation.html")
    html_content = template.render(
        villa_name=settings.villa_name,
        villa_address=settings.villa_address,
        villa_phone=settings.villa_phone,
        villa_line_id=settings.villa_line_id,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        **booking_data,
    )

    filename = f"confirm_{booking_data['booking_id']}_{datetime.now():%Y%m%d%H%M%S}.pdf"
    output_path = OUTPUT_DIR / filename

    HTML(string=html_content).write_pdf(str(output_path))
    return str(output_path)
