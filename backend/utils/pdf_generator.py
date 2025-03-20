from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os
import uuid
import re
import json
from backend.utils.openai_utils import call_openai_api

def generate_pdf_report(report_data):
    """Generate a PDF report with OpenAI-enhanced content and return its accessible URL."""
    
    # Generate unique filename
    filename = f"report_{uuid.uuid4()}.pdf"
    
    # Define directory to save PDF (persistent)
    reports_dir = "/opt/render/project/src/backend/static/reports"
    os.makedirs(reports_dir, exist_ok=True)
    
    # Full path to save the PDF
    filepath = os.path.join(reports_dir, filename)
    
    # Prepare data for OpenAI prompts, safely handling types
    symptoms = str(report_data.get('symptoms', 'Not specified'))
    condition_common = str(report_data.get('condition_common', 'Unknown'))
    condition_medical = str(report_data.get('condition_medical', 'N/A'))
    confidence = str(report_data.get('confidence', 'N/A'))
    triage_level = str(report_data.get('triage_level', 'N/A'))
    
    # Generate dynamic content using OpenAI with safe string formatting
    prompt = (
        "You are a medical AI assistant. Based on the following report data, generate content for a premium health report:\n"
        f"- Symptoms: {symptoms}\n"
        f"- Condition (Common): {condition_common}\n"
        f"- Condition (Medical): {condition_medical}\n"
        f"- Confidence: {confidence}%\n"
        f"- Triage Level: {triage_level}\n\n"
        "Provide the following sections:\n"
        "1. User-Friendly Summary (100 words max): Summarize the symptoms and condition in simple, empathetic language suitable for a patient.\n"
        "2. Detailed Clinical Report (300 words max):\n"
        "   - AI Reasoning: Explain how these symptoms lead to the condition, emphasizing differential diagnosis and confidence levels.\n"
        "   - Differential Diagnosis Table (JSON): Output as a JSON array, e.g., [{\"condition\": \"Tension Headache\", \"confidence\": \"75%\"}, {\"condition\": \"Migraine\", \"confidence\": \"20%\"}, {\"condition\": \"Sinusitis\", \"confidence\": \"5%\"}].\n"
        "3. Doctor Communication Guide (150 words max): Suggest polite, effective ways a patient can explain these symptoms to a doctor, including 3-5 specific questions to ask about the condition.\n"
        "4. PubMed Research Links (100 words max): List three recent PubMed articles relevant to the condition with brief descriptions and placeholder links (e.g., https://pubmed.ncbi.nlm.nih.gov/placeholder/).\n"
        "5. Immediate Action Plan (150 words max): Provide a short list of safe self-care steps for someone experiencing the condition. Also, list emergency warning signs.\n"
        "6. Visual Aids Description (50 words max): Describe a confidence bar chart for the differential diagnosis percentages.\n"
        "7. Doctor Contact Template (100 words max): Write a short email template where a patient summarizes their symptoms and attaches this report for a doctor visit.\n\n"
        "Respond in plain text, with each section clearly labeled (e.g., '### User-Friendly Summary...', '### Detailed Clinical Report...', etc.)."
    )
    
    response = call_openai_api([{"role": "user", "content": prompt}], max_tokens=800)
    
    # Robustly parse OpenAI response using regex
    sections = re.split(r"###\s+", response)
    section_dict = {}
    for section in sections:
        if section.strip():
            header, *body = section.strip().split("\n", 1)
            section_dict[header.strip()] = body[0].strip() if body else ""
    
    # Extract sections
    summary = section_dict.get("User-Friendly Summary", "")
    clinical_report = section_dict.get("Detailed Clinical Report", "")
    doctor_comm = section_dict.get("Doctor Communication Guide", "")
    pubmed_links = section_dict.get("PubMed Research Links", "")
    action_plan = section_dict.get("Immediate Action Plan", "")
    visual_desc = section_dict.get("Visual Aids Description", "")
    doctor_email = section_dict.get("Doctor Contact Template", "")
    
    # Parse differential diagnosis JSON
    diff_table_raw = ""
    for line in clinical_report.split("\n"):
        if "Differential Diagnosis Table" in line:
            diff_table_raw = line.replace("Differential Diagnosis Table (JSON):", "").strip()
            break
    try:
        diff_data = json.loads(diff_table_raw) if diff_table_raw else []
    except json.JSONDecodeError:
        diff_data = []
    diff_conditions = [item["condition"] for item in diff_data]
    diff_confidences = [float(item["confidence"].replace("%", "")) for item in diff_data]
    
    # Generate PDF content
    c = canvas.Canvas(filepath, pagesize=letter)
    c.setFont("Helvetica", 10)
    
    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(100, 750, "HealthTracker Michele Report")
    c.setFont("Helvetica", 10)
    c.drawString(100, 730, f"Generated: {report_data['timestamp']}")
    c.drawString(100, 715, f"User ID: {report_data['user_id'] if 'user_id' in report_data else 'Guest Report #ABC123'}")
    c.line(50, 700, 550, 700)
    y = 680
    
    # Function to handle page overflow
    def check_page_overflow():
        nonlocal y
        if y < 50:
            c.showPage()
            y = 750
            c.setFont("Helvetica", 10)
            c.line(50, 740, 550, 740)
    
    # User-Friendly Summary
    c.setFont("Helvetica-Bold", 12)
    c.drawString(100, y, "User-Friendly Summary")
    y -= 20
    c.setFont("Helvetica", 10)
    for line in summary.split("\n"):
        if line.strip():
            c.drawString(100, y, line.strip()[:80])
            y -= 15
            check_page_overflow()
    y -= 10
    c.line(50, y, 550, y)
    
    # Detailed Clinical Report
    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(100, y, "Detailed Clinical Report")
    y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(100, y, "Symptoms Reported:")
    y -= 15
    c.drawString(100, y, symptoms)
    y -= 20
    c.setFont("Helvetica-Bold", 10)
    c.drawString(100, y, "AI Reasoning:")
    y -= 15
    c.setFont("Helvetica", 10)
    for line in clinical_report.split("\n"):
        if "AI Reasoning" not in line and line.strip():
            c.drawString(100, y, line.strip()[:80])
            y -= 15
            check_page_overflow()
    y -= 20
    c.setFont("Helvetica-Bold", 10)
    c.drawString(100, y, "Differential Diagnosis:")
    y -= 15
    c.setFont("Helvetica", 10)
    for condition, conf in zip(diff_conditions, diff_confidences):
        c.drawString(100, y, f"{condition}: {conf}%")
        y -= 15
        check_page_overflow()
    y -= 10
    c.line(50, y, 550, y)
    
    # Doctor Communication Guide
    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(100, y, "Doctor Communication Guide")
    y -= 20
    c.setFont("Helvetica", 10)
    for line in doctor_comm.split("\n"):
        if line.strip():
            c.drawString(100, y, line.strip()[:80])
            y -= 15
            check_page_overflow()
    y -= 10
    c.line(50, y, 550, y)
    
    # PubMed Research Links
    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(100, y, "Trusted Medical Sources")
    y -= 20
    c.setFont("Helvetica", 10)
    for line in pubmed_links.split("\n"):
        if line.strip():
            c.drawString(100, y, line.strip()[:80])
            y -= 15
            check_page_overflow()
    y -= 10
    c.line(50, y, 550, y)
    
    # Immediate Action Plan
    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(100, y, "Immediate Action Plan")
    y -= 20
    c.setFont("Helvetica", 10)
    for line in action_plan.split("\n"):
        if line.strip():
            c.drawString(100, y, line.strip()[:80])
            y -= 15
            check_page_overflow()
    y -= 10
    c.line(50, y, 550, y)
    
    # Visual Aids (Confidence Bar Chart)
    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(100, y, "Visual Aids")
    y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(100, y, visual_desc[:80])
    y -= 20
    bar_width = 100
    max_height = 50
    x_start = 100
    for i, conf in enumerate(diff_confidences):
        bar_height = (conf / 100) * max_height
        c.rect(x_start + i * (bar_width + 10), y, bar_width, bar_height, fill=1)
        c.drawString(x_start + i * (bar_width + 10), y - 15, diff_conditions[i][:10])
        c.drawString(x_start + i * (bar_width + 10) + 30, y + bar_height + 10, f"{conf}%")
    y -= 80
    c.line(50, y, 550, y)
    
    # Doctor Contact Template
    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(100, y, "Doctor Contact Template")
    y -= 20
    c.setFont("Helvetica", 10)
    for line in doctor_email.split("\n"):
        if line.strip():
            c.drawString(100, y, line.strip()[:80])
            y -= 15
            check_page_overflow()
    y -= 10
    c.line(50, y, 550, y)
    
    # Disclaimer
    y -= 10
    c.setFont("Helvetica-Italic", 10)
    c.drawString(100, y, "Disclaimer: This AI-generated report is for informational purposes only and not a substitute for professional medical advice. Consult a licensed physician.")
    y -= 20
    
    # Footer
    c.setFont("Helvetica", 8)
    c.drawString(100, y, "Powered by HealthTracker AI (GPT-4o powered). Questions? Visit healthtrackermichele.com/support.")
    c.drawString(100, y - 10, "Report generated with data current as of March 18, 2025.")
    
    c.save()

    file_url = f"https://healthtrackermichele.onrender.com/static/reports/{filename}"
    return file_url