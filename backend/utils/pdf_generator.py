from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os
import uuid

def generate_pdf_report(report_data):
    """Generate a PDF report and return its accessible URL."""
    
    # Generate unique filename
    filename = f"report_{uuid.uuid4()}.pdf"
    
    # Define directory to save PDF (persistent)
    reports_dir = "/opt/render/project/src/backend/static/reports"
    os.makedirs(reports_dir, exist_ok=True)  # Ensure folder exists
    
    # Full path to save the PDF
    filepath = os.path.join(reports_dir, filename)
    
    # Generate PDF content
    c = canvas.Canvas(filepath, pagesize=letter)
    c.drawString(100, 750, "HealthTracker Doctor Report")
    c.drawString(100, 730, f"User ID: {report_data['user_id']}")
    c.drawString(100, 710, f"Timestamp: {report_data['timestamp']}")
    c.drawString(100, 690, f"Condition: {report_data['condition_common']} ({report_data['condition_medical']})")
    c.drawString(100, 670, f"Confidence: {report_data['confidence']}%")
    c.drawString(100, 650, f"Triage Level: {report_data['triage_level']}")
    c.drawString(100, 630, f"Care Recommendation: {report_data['care_recommendation']}")
    c.save()

    # Return public URL (adjusted to point to static folder)
    file_url = f"https://healthtrackermichele.onrender.com/static/reports/{filename}"
    
    return file_url