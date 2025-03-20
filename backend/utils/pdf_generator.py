from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
import os
import uuid
import re
import json
import logging

from backend.utils.openai_utils import call_openai_api

logger = logging.getLogger(__name__)

def generate_pdf_report(report_data):
    """Generate a PDF report with OpenAI-enhanced content and return its accessible URL."""
    
    filename = f"report_{uuid.uuid4()}.pdf"
    reports_dir = "/opt/render/project/src/backend/static/reports"
    os.makedirs(reports_dir, exist_ok=True)
    filepath = os.path.join(reports_dir, filename)
    
    symptoms = str(report_data.get('symptom', 'Not specified'))
    condition_common = str(report_data.get('condition_common', 'Unknown'))
    condition_medical = str(report_data.get('condition_medical', 'N/A'))
    confidence = str(report_data.get('confidence', 'N/A'))
    triage_level = str(report_data.get('triage_level', 'N/A'))
    
    logger.info(f"Generating PDF with report_data: symptoms={symptoms}, condition_common={condition_common}")
    
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
        "Respond in plain text, with each section clearly labeled (e.g., '### User-Friendly Summary...', '### Detailed Clinical Report...', etc.). Replace 'GPT-40' with 'GPT-4o' in any output."
    )
    
    response = call_openai_api([{"role": "user", "content": prompt}], response_format={"type": "text"})
    logger.info(f"OpenAI response: {response[:200]}...")
    
    sections = re.split(r"###\s+", response.strip())
    section_dict = {}
    for section in sections:
        if section.strip():
            header, *body = section.split("\n", 1)
            section_dict[header.strip()] = "\n".join(body) if body else ""
    
    summary = section_dict.get("User-Friendly Summary", "")
    clinical_report = section_dict.get("Detailed Clinical Report", "")
    doctor_comm = section_dict.get("Doctor Communication Guide", "")
    pubmed_links = section_dict.get("PubMed Research Links", "")
    action_plan = section_dict.get("Immediate Action Plan", "")
    visual_desc = section_dict.get("Visual Aids Description", "")
    doctor_email = section_dict.get("Doctor Contact Template", "")
    
    diff_table_raw = ""
    clinical_lines = clinical_report.split("\n")
    json_start = -1
    for i, line in enumerate(clinical_lines):
        if "Differential Diagnosis Table (JSON):" in line:
            json_start = i + 1
            break
    if json_start != -1:
        json_lines = clinical_lines[json_start:]
        diff_table_raw = "\n".join(json_lines).strip()
        diff_table_raw = re.sub(r"```json|```", "", diff_table_raw).strip()
    logger.info(f"Raw differential diagnosis JSON: {diff_table_raw}")
    
    try:
        diff_data = json.loads(diff_table_raw) if diff_table_raw else []
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse differential diagnosis JSON: {diff_table_raw}, error: {str(e)}")
        diff_data = [{"condition": condition_common, "confidence": str(confidence) + "%"}] if confidence != "N/A" else []
    diff_conditions = [item["condition"] for item in diff_data]
    diff_confidences = [float(item["confidence"].replace("%", "")) for item in diff_data]
    logger.info(f"Parsed differential diagnosis: conditions={diff_conditions}, confidences={diff_confidences}")
    
    c = canvas.Canvas(filepath, pagesize=letter)
    c.setFont("Helvetica", 10)
    
    # Header with Logo
    logo_path = "/opt/render/project/src/backend/static/dist/doctor-avatar.png"
    if os.path.exists(logo_path):
        c.drawImage(logo_path, 50, 710, width=40, height=40)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(100, 735, "HealthTracker Michele Report")
    c.setFont("Helvetica", 10)
    c.drawString(100, 715, f"Generated: {report_data['timestamp']}")
    c.drawString(100, 700, f"User ID: {report_data['user_id'] if 'user_id' in report_data else 'Guest Report #ABC123'}")
    c.line(50, 685, 550, 685)
    y = 665
    
    def draw_wrapped_text(text, x, y_start, max_width, line_height):
        nonlocal y
        words = text.split()
        line = ""
        y = y_start
        for word in words:
            if c.stringWidth(line + " " + word, "Helvetica", 10) < max_width:
                line += " " + word if line else word
            else:
                c.drawString(x, y, line)
                y -= line_height
                check_page_overflow()
                line = word
        if line:
            c.drawString(x, y, line)
            y -= line_height
            check_page_overflow()
        return y
    
    def check_page_overflow(extra_space=0):
        nonlocal y
        if y - extra_space < 60:  # Increased buffer
            c.showPage()
            y = 750
            c.setFont("Helvetica", 10)
            c.line(50, 740, 550, 740)
    
    # User-Friendly Summary
    c.setFont("Helvetica-Bold", 12)
    c.drawString(100, y, "User-Friendly Summary")
    y -= 20
    c.setFont("Helvetica", 10)
    y = draw_wrapped_text(summary, 100, y, 450, 15)
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
    y = draw_wrapped_text(symptoms, 100, y, 450, 15)
    y -= 20
    c.setFont("Helvetica-Bold", 10)
    c.drawString(100, y, "AI Reasoning:")
    y -= 15
    c.setFont("Helvetica", 10)
    reasoning_text = "\n".join([line for line in clinical_lines if "Differential Diagnosis Table" not in line])
    y = draw_wrapped_text(reasoning_text, 100, y, 450, 15)
    y -= 20
    c.setFont("Helvetica-Bold", 10)
    c.drawString(100, y, "Differential Diagnosis:")
    y -= 15
    c.setFont("Helvetica", 10)
    logger.info(f"Drawing differential diagnosis at y={y}, items={len(diff_conditions)}")
    for condition, conf in zip(diff_conditions, diff_confidences):
        logger.info(f"Drawing: {condition}: {conf}% at y={y}")
        c.setFont("Helvetica", 10)
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
    y = draw_wrapped_text(doctor_comm, 100, y, 450, 15)
    y -= 10
    c.line(50, y, 550, y)
    
    # PubMed Research Links
    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(100, y, "Trusted Medical Sources")
    y -= 20
    c.setFont("Helvetica", 10)
    y = draw_wrapped_text(pubmed_links, 100, y, 450, 15)
    y -= 10
    c.line(50, y, 550, y)
    
    # Immediate Action Plan
    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(100, y, "Immediate Action Plan")
    y -= 20
    c.setFont("Helvetica", 10)
    text_obj = c.beginText(100, y)
    text_obj.setFont("Helvetica", 10)
    text_obj.setLeading(15)
    for line in action_plan.split('\n'):
        text_obj.textLine(line)
        y -= 15
        if y < 60:  # Match buffer
            c.drawText(text_obj)
            c.showPage()
            y = 750
            c.setFont("Helvetica", 10)
            c.line(50, 740, 550, 740)
            text_obj = c.beginText(100, y)
            text_obj.setFont("Helvetica", 10)
            text_obj.setLeading(15)
    c.drawText(text_obj)
    y -= 10
    c.line(50, y, 550, y)
    
    # Visual Aids (Confidence Bar Chart)
    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(100, y, "Visual Aids")
    y -= 20
    c.setFont("Helvetica", 10)
    y = draw_wrapped_text(visual_desc, 100, y, 450, 15)
    y -= 20
    check_page_overflow(120)
    bar_width = 80
    max_height = 100
    x_start = 100
    logger.info(f"Drawing bar chart at y={y}, conditions={diff_conditions}")
    for i, conf in enumerate(diff_confidences):
        bar_height = (conf / 100) * max_height
        c.setFillGray(0.8)
        c.rect(x_start + i * (bar_width + 20), y, bar_width, bar_height, fill=1)
        c.setFillColor("black")
        c.drawString(x_start + i * (bar_width + 20), y - 15, diff_conditions[i][:12])
        c.drawString(x_start + i * (bar_width + 20) + 30, y + bar_height + 5, f"{conf}%")
    y -= 120
    c.line(50, y, 550, y)
    
    # Doctor Contact Template
    y -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(100, y, "Doctor Contact Template")
    y -= 20
    c.setFont("Helvetica", 10)
    y = draw_wrapped_text(doctor_email, 100, y, 450, 15)
    y -= 10
    c.line(50, y, 550, y)
    
    # Disclaimer
    y -= 10
    c.setFont("Helvetica-Oblique", 10)
    y = draw_wrapped_text("Disclaimer: This AI-generated report is for informational purposes only and not a substitute for professional medical advice. Consult a licensed physician.", 100, y, 450, 15)
    y -= 20
    
    # Footer
    c.setFont("Helvetica", 8)
    y = draw_wrapped_text("Powered by HealthTracker AI (GPT-4o powered). Questions? Visit healthtrackermichele.com/support.", 100, y, 450, 12)
    c.drawString(100, y - 10, "Report generated with data current as of March 18, 2025.")
    
    c.save()
    file_url = f"https://healthtrackermichele.onrender.com/static/reports/{filename}"
    return file_url