"""
services/pdf_generator.py
─────────────────────────
Template-based PDF generation for bank-compliant rebuttal letters.

Design: Jinja2 renders backend/templates/rebuttal_letter.html with conditional
sections (only non-null evidence). ReportLab converts the evidence_packet into a
formal PDF. No free-form LLM generation — zero hallucination.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)

logger = logging.getLogger(__name__)

# Resolve paths relative to this file: backend/app/services -> backend/templates & backend/data
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_REBUTTALS_DIR = _DATA_DIR / "rebuttals"


def _ensure_dirs() -> None:
    _REBUTTALS_DIR.mkdir(parents=True, exist_ok=True)


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def render_html(
    dispute_id: str,
    payment_id: str,
    merchant_id: str,
    reason_code: str,
    amount_paise: int,
    evidence_packet: dict,
) -> str:
    """Render the Jinja2 HTML template with conditional sections."""
    env = _jinja_env()
    template = env.get_template("rebuttal_letter.html")
    html = template.render(
        dispute_id=dispute_id,
        payment_id=payment_id,
        merchant_id=merchant_id,
        reason_code=reason_code,
        amount_paise=amount_paise,
        evidence=evidence_packet,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
    return html


def _build_pdf(
    output_path: Path,
    dispute_id: str,
    payment_id: str,
    merchant_id: str,
    reason_code: str,
    amount_paise: int,
    evidence_packet: dict,
) -> int:
    """
    Build a formal rebuttal PDF using ReportLab Platypus.
    Returns word count of the PDF body.
    Sections only appear if corresponding evidence is present — mirrors Jinja template.
    """
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"Rebuttal {dispute_id}",
        author="AutoDefend",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title2", parent=styles["Title"], fontSize=16, textColor=colors.HexColor("#0f2b46"),
        alignment=TA_CENTER, spaceAfter=6,
    )
    h2_style = ParagraphStyle(
        "H2", parent=styles["Heading2"], fontSize=11, textColor=colors.HexColor("#0f2b46"),
        spaceBefore=14, spaceAfter=6, borderPadding=(0, 0, 0, 6),
    )
    normal = ParagraphStyle(
        "Normal2", parent=styles["Normal"], fontSize=9, leading=13, alignment=TA_JUSTIFY, spaceAfter=4,
    )
    small = ParagraphStyle(
        "Small", parent=styles["Normal"], fontSize=7, textColor=colors.HexColor("#666666"),
        alignment=TA_CENTER, spaceBefore=10,
    )
    cell_label = ParagraphStyle("CellLabel", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#333333"))
    cell_value = ParagraphStyle("CellValue", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#111111"))

    story = []
    word_count = 0

    def add_para(text: str, style=normal):
        nonlocal word_count
        story.append(Paragraph(text, style))
        word_count += len(text.split())

    # Title
    add_para("CHARGEBACK REBUTTAL LETTER", title_style)
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0f2b46"), spaceAfter=10))

    # Header table
    header_data = [
        [Paragraph("<b>Dispute Reference</b>", cell_label), Paragraph(dispute_id, cell_value)],
        [Paragraph("<b>Payment ID</b>", cell_label), Paragraph(payment_id, cell_value)],
        [Paragraph("<b>Merchant ID</b>", cell_label), Paragraph(merchant_id, cell_value)],
        [Paragraph("<b>Reason Code</b>", cell_label), Paragraph(reason_code, cell_value)],
        [Paragraph("<b>Disputed Amount</b>", cell_label), Paragraph(f"Rs. {amount_paise/100:.2f} ({amount_paise} paise)", cell_value)],
        [Paragraph("<b>Date Generated</b>", cell_label), Paragraph(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), cell_value)],
    ]
    t = Table(header_data, colWidths=[42*mm, 110*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f4f6f9")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 6*mm))

    intro = (
        f"We respectfully submit this evidence packet in response to dispute <b>{dispute_id}</b> "
        f"for payment <b>{payment_id}</b> classified as <b>{reason_code}</b>. "
        "Each exhibit below directly addresses the evidence requirements for this reason code "
        "and contains only verified data retrieved from our systems."
    )
    add_para(intro)
    story.append(Spacer(1, 3*mm))

    # Exhibit A: Logistics DELIVERED
    logistics = evidence_packet.get("logistics")
    if logistics and logistics.get("status") == "DELIVERED":
        add_para("EXHIBIT A: PROOF OF DELIVERY", h2_style)
        add_para(f"Transaction <b>{payment_id}</b> was successfully fulfilled and delivered.")
        if logistics.get("delivery_date"):
            dt = logistics["delivery_date"]
            tm = logistics.get("delivery_time", "")
            add_para(f"<b>Delivery Date:</b> {dt} {tm}".strip())
        if logistics.get("provider"):
            add_para(f"<b>Delivery Provider:</b> {logistics['provider']}")
        if logistics.get("tracking_id"):
            add_para(f"<b>Tracking ID:</b> {logistics['tracking_id']}")
        if logistics.get("signature_available") and logistics.get("recipient_name"):
            add_para(f"<b>Recipient Acknowledgment on File:</b> {logistics['recipient_name']} (signature captured)")
        elif logistics.get("signature_available"):
            add_para("<b>Recipient Signature:</b> Available on file with delivery provider.")
        story.append(Spacer(1, 2*mm))

    # Exhibit B: 3DS Authentication
    security = evidence_packet.get("security")
    if security and security.get("three_ds_passed") is True:
        add_para("EXHIBIT B: TRANSACTION AUTHENTICATION (3D Secure)", h2_style)
        add_para("This transaction completed <b>3D Secure (3DS) authentication</b>, indicating the cardholder was verified at checkout.")
        if security.get("three_ds_reference"):
            add_para(f"<b>Authentication Reference:</b> {security['three_ds_reference']}")
        if security.get("device_fingerprint"):
            add_para(f"<b>Device Fingerprint:</b> {security['device_fingerprint']}")
        story.append(Spacer(1, 2*mm))

    # Exhibit C: Payment Verification (CVV / AVS / IP)
    if security and (security.get("cvv_match") is True or security.get("avs_result") == "Y" or security.get("billing_address_match") is not None):
        # Only render if at least one verification signal present; filter to passed signals
        has_signal = False
        if security.get("cvv_match") is True:
            has_signal = True
        if security.get("avs_result") == "Y":
            has_signal = True
        if security.get("billing_address_match") is True:
            has_signal = True
        # Still show IP consistency if available
        if has_signal or security.get("checkout_ip"):
            add_para("EXHIBIT C: PAYMENT INSTRUMENT VERIFICATION", h2_style)
            if security.get("cvv_match") is not None:
                add_para(f"<b>CVV Verification:</b> {'PASSED' if security['cvv_match'] else 'FAILED'}")
            if security.get("avs_result"):
                avs = security["avs_result"]
                label = "Billing address verified" if avs == "Y" else "No match" if avs == "N" else f"Result: {avs}"
                add_para(f"<b>Address Verification (AVS):</b> {avs} — {label}")
            if security.get("billing_address_match") is not None:
                if security["billing_address_match"]:
                    add_para("<b>IP / Billing Address Match:</b> CONSISTENT — Checkout IP geolocation matches billing region")
                else:
                    add_para("<b>IP / Billing Address Match:</b> NOT CONSISTENT")
            if security.get("checkout_ip"):
                add_para(f"<b>Checkout IP:</b> {security['checkout_ip']}")
            story.append(Spacer(1, 2*mm))

    # Exhibit D: CRM Order History
    crm = evidence_packet.get("crm")
    if crm and crm.get("customer_order_count") is not None:
        add_para("EXHIBIT D: CUSTOMER ORDER HISTORY", h2_style)
        add_para(f"<b>Customer Order Count:</b> {crm['customer_order_count']}")
        if crm.get("customer_since_days") is not None:
            add_para(f"<b>Customer Since:</b> {crm['customer_since_days']} days")
        if crm.get("delivery_success_rate") is not None:
            add_para(f"<b>Delivery Success Rate:</b> {crm['delivery_success_rate']*100:.0f}%")
        if crm.get("prior_disputes") is not None:
            add_para(f"<b>Prior Disputes:</b> {crm['prior_disputes']}")
        if crm.get("customer_avg_order_paise") is not None:
            add_para(f"<b>Average Order Value:</b> Rs. {crm['customer_avg_order_paise']/100:.2f}")
        story.append(Spacer(1, 2*mm))

    # Conclusion
    add_para("CONCLUSION", h2_style)
    add_para(
        "Based on the verified evidence attached, we respectfully request that this chargeback be reversed "
        "in the merchant's favour. All statements above are supported by system-generated evidence; no fields have been hallucinated. "
        "Evidence was gathered directly from logistics, payment authentication, and CRM systems."
    )
    add_para(f"<b>Merchant:</b> {merchant_id} &nbsp;|&nbsp; <b>Dispute:</b> {dispute_id}")

    story.append(Spacer(1, 6*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc"), spaceAfter=4))
    story.append(Paragraph(
        "AutoDefend — Autonomous Chargeback Defense Assembler | Razorpay Hackathon 2026 | This document was auto-generated and contains only verified evidence fields.",
        small,
    ))

    doc.build(story)
    return word_count


async def generate_rebuttal_pdf(
    dispute_id: str,
    payment_id: str,
    merchant_id: str,
    reason_code: str,
    amount_paise: int,
    evidence_packet: dict,
) -> dict:
    """
    Generate both HTML (debug) and PDF rebuttal letter.
    Returns dict with pdf_path, html_path, word_count.
    """
    _ensure_dirs()

    # 1. Render HTML (conditional, for audit/debug)
    html = render_html(dispute_id, payment_id, merchant_id, reason_code, amount_paise, evidence_packet)
    html_path = _REBUTTALS_DIR / f"{dispute_id}.html"
    html_path.write_text(html, encoding="utf-8")

    # 2. Build PDF via ReportLab
    pdf_path = _REBUTTALS_DIR / f"{dispute_id}.pdf"
    word_count = _build_pdf(pdf_path, dispute_id, payment_id, merchant_id, reason_code, amount_paise, evidence_packet)

    logger.info("PDF generated | dispute_id=%s | path=%s | words=%d", dispute_id, pdf_path, word_count)

    return {
        "pdf_path": str(pdf_path),
        "html_path": str(html_path),
        "word_count": word_count,
    }
