from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os
import uuid

def generate_pdf_report(report_data):
    """Generate a PDF report and return its URL (simulated)."""
    # Simulate PDF generation (in a real app, this would save to a file system or cloud storage)
    filename = f"report_{uuid.uuid4()}.pdf"
    filepath = os.path.join("/tmp", filename)

    c = canvas.Canvas(filepath, pagesize=letter)
    c.drawString(100, 750, "HealthTracker Doctor Report")
    c.drawString(100, 730, f"User ID: {report_data['user_id']}")
    c.drawString(100, 710, f"Timestamp: {report_data['timestamp']}")
    c.drawString(100, 690, f"Condition: {report_data['condition_common']} ({report_data['condition_medical']})")
    c.drawString(100, 670, f"Confidence: {report_data['confidence']}%")
    c.drawString(100, 650, f"Triage Level: {report_data['triage_level']}")
    c.drawString(100, 630, f"Care Recommendation: {report_data['care_recommendation']}")
    c.save()

    # In a real app, upload this file to cloud storage (e.g., AWS S3) and return a URL
    # For now, return a fake URL
    fake_url = f"https://healthtrackermichele.onrender.com/reports/{filename}"
    return fake_url