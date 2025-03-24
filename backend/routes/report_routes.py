from flask import Blueprint, request, jsonify
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from backend.models import Report, User, CareRecommendationEnum, UserTierEnum
from backend.extensions import db
from backend.utils.openai_utils import call_openai_api
from backend.utils.pdf_generator import generate_pdf_report
from backend.utils.access_control import can_access_assessment_details
from datetime import datetime
import logging

logger = logging.getLogger("report_routes")
report_routes = Blueprint("report_routes", __name__, url_prefix="/api/reports")

def determine_triage_level(symptoms, timeline):
    """Determine the triage level using OpenAI based on symptoms and timeline."""
    symptom_text = ", ".join(symptoms) if symptoms else "Not specified"
    prompt = [
        {"role": "system", "content": "You are a medical assistant. Based on the symptoms and timeline, determine the triage level (AT_HOME, MODERATE, SEVERE). Respond with only the triage level in uppercase."},
        {"role": "user", "content": f"Symptoms: {symptom_text}\nTimeline: {timeline}"}
    ]
    try:
        triage_level = call_openai_api(prompt, max_tokens=10).strip()
        if triage_level not in ["AT_HOME", "MODERATE", "SEVERE"]:
            logger.warning(f"Invalid triage level received: {triage_level}, defaulting to MODERATE")
            return "MODERATE"
        return triage_level
    except Exception as e:
        logger.error(f"Failed to determine triage level: {str(e)}", exc_info=True)
        return "MODERATE"  # Default to MODERATE if assessment fails

@report_routes.route("/", methods=["POST"])
def generate_report():
    """Generate a medical report based on symptoms and timeline."""
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        temp_user_id = data.get("temp_user_id")
        symptoms = data.get("symptoms", [])
        timeline = data.get("timeline", "")
        generate_pdf = data.get("generate_pdf", False)

        if not (user_id or temp_user_id):
            return jsonify({"error": "user_id or temp_user_id is required."}), 400

        user = None
        if user_id:
            user = User.query.get(user_id)
            if not user:
                return jsonify({"error": "User not found."}), 404

        triage_level = determine_triage_level(symptoms, timeline)
        logger.info(f"Determined triage_level: {triage_level} for symptoms: {symptoms}")

        symptom_text = ", ".join(symptoms) if symptoms else "Not specified"
        prompt = [
            {"role": "system", "content": "You are a medical assistant. Generate a concise medical report based on the user's symptoms and timeline. Respond as plain text with sections: Summary, Possible Conditions, Recommendations."},
            {"role": "user", "content": f"Symptoms: {symptom_text}\nTimeline: {timeline}"}
        ]
        content = call_openai_api(prompt, max_tokens=500)

        possible_conditions = "Unknown"
        for line in content.split("\n"):
            if "Possible Conditions:" in line:
                possible_conditions = line.split(":", 1)[1].strip()
                break

        report_data = {
            "id": None,
            "user_id": user_id,
            "temp_user_id": temp_user_id,
            "title": f"Report - {datetime.utcnow().strftime('%Y-%m-%d')}",
            "content": content,
            "status": "COMPLETED",
            "care_recommendation": CareRecommendationEnum.SEE_DOCTOR.value,
            "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        }

        report_url = None
        if generate_pdf:
            pdf_data = {
                "user_id": user_id or temp_user_id,
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "symptom": symptom_text,
                "condition_common": possible_conditions,
                "condition_medical": "N/A",
                "confidence": "N/A",
                "triage_level": triage_level
            }
            logger.info(f"Generating PDF report with triage_level: {triage_level}, symptoms: {symptom_text}")
            report_url = generate_pdf_report(pdf_data)

        if user_id and user and can_access_assessment_details(user):
            new_report = Report(
                user_id=user_id,
                temp_user_id=temp_user_id,
                title=report_data["title"],
                content=content,
                status="COMPLETED",
                care_recommendation=CareRecommendationEnum.SEE_DOCTOR,
                report_url=report_url,
                created_at=datetime.utcnow()
            )
            db.session.add(new_report)
            db.session.commit()
            report_data["id"] = new_report.id
            report_data["report_url"] = new_report.report_url
            logger.info(f"Report saved for user {user_id}: {report_data['title']}, report_url: {report_url}")
        else:
            logger.info(f"Report generated but not saved (non-subscriber): user_id={user_id}, temp_user_id={temp_user_id}")

        return jsonify({
            "message": "Report generated successfully.",
            "report": report_data,
            "report_url": report_url if generate_pdf else None
        }), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to generate report: {str(e)}", exc_info=True)
        return jsonify({"error": "Error generating report."}), 500

@report_routes.route("/<int:user_id>", methods=["GET"])
def get_reports(user_id):
    """Retrieve all reports for a specific user."""
    try:
        verify_jwt_in_request()
        authenticated_user_id = get_jwt_identity()

        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found."}), 404

        if str(user_id) != authenticated_user_id:
            logger.warning(f"Unauthorized access attempt by user {authenticated_user_id} for user {user_id}")
            return jsonify({"error": "Unauthorized access."}), 403

        reports = Report.query.filter_by(user_id=user_id).all()
        if not reports:
            return jsonify({"message": "No reports found for this user."}), 200

        logger.info(f"Retrieved {len(reports)} reports for user {user_id}")
        return jsonify({"reports": [report.to_dict() for report in reports]}), 200
    except Exception as e:
        logger.error(f"Error fetching reports for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Error fetching reports."}), 500

@report_routes.route("/<int:report_id>", methods=["DELETE"])
def delete_report(report_id):
    """Delete a specific report."""
    try:
        verify_jwt_in_request()
        authenticated_user_id = get_jwt_identity()

        report = Report.query.get(report_id)
        if not report:
            return jsonify({"error": "Report not found."}), 404

        if report.user_id and str(report.user_id) != authenticated_user_id:
            logger.warning(f"Unauthorized access attempt by user {authenticated_user_id} for report {report_id}")
            return jsonify({"error": "Unauthorized access."}), 403

        db.session.delete(report)
        db.session.commit()
        logger.info(f"Report {report_id} deleted by user {authenticated_user_id}")
        return jsonify({"message": "Report deleted successfully.", "deleted_id": report_id}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete report {report_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Error deleting report."}), 500