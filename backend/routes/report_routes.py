from flask import Blueprint, request, jsonify
from backend.extensions import db
from backend.models import Report, User
from datetime import datetime
import logging

# Logger setup
logger = logging.getLogger("report_routes")

# Create Flask Blueprint
report_routes = Blueprint("report_routes", __name__)

# Route to generate a report
@report_routes.route("/api/reports", methods=["POST"])
def generate_report():
    """Generates a new medical report for a user and logs it in the database."""
    try:
        data = request.get_json()
        user_id = data.get("user_id")
        symptoms = data.get("symptoms", [])
        timeline = data.get("timeline", "")

        logger.info(f"Generating report for user {user_id}")

        user = User.query.get(user_id)
        if not user:
            logger.warning(f"User {user_id} not found.")
            return jsonify({"error": "User not found."}), 404

        new_report = Report(
            user_id=user_id,
            symptoms=", ".join(symptoms),
            timeline=timeline,
            created_at=datetime.utcnow()
        )

        db.session.add(new_report)
        db.session.commit()

        logger.info(f"Report generated successfully for user {user_id} (Report ID: {new_report.id})")

        return jsonify({
            "message": "Report generated successfully.",
            "report": {
                "id": new_report.id,
                "user_id": new_report.user_id,
                "symptoms": new_report.symptoms,
                "timeline": new_report.timeline,
                "created_at": new_report.created_at.strftime("%Y-%m-%d %H:%M:%S")
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to generate report for user {user_id}: {str(e)}")
        return jsonify({"error": "Error generating report."}), 500

# Route to retrieve reports for a user
@report_routes.route("/api/reports/<int:user_id>", methods=["GET"])
def get_reports(user_id):
    """Fetches all reports for a specific user."""
    try:
        logger.info(f"Fetching reports for user {user_id}")

        user = User.query.get(user_id)
        if not user:
            logger.warning(f"User {user_id} not found.")
            return jsonify({"error": "User not found."}), 404

        reports = Report.query.filter_by(user_id=user_id).all()
        if not reports:
            logger.info(f"No reports found for user {user_id}.")
            return jsonify({"error": "No reports found for this user."}), 404

        logger.info(f"Reports retrieved successfully for user {user_id} (Total: {len(reports)})")

        return jsonify({"reports": [
            {
                "id": report.id,
                "user_id": report.user_id,
                "symptoms": report.symptoms,
                "timeline": report.timeline,
                "created_at": report.created_at.strftime("%Y-%m-%d %H:%M:%S")
            } for report in reports
        ]})

    except Exception as e:
        logger.error(f"Error fetching reports for user {user_id}: {str(e)}")
        return jsonify({"error": "Error fetching reports."}), 500

# Route to delete a report
@report_routes.route("/api/reports/<int:report_id>", methods=["DELETE"])
def delete_report(report_id):
    """Deletes a specific report entry by ID."""
    try:
        logger.info(f"Deleting report ID {report_id}")

        report = Report.query.get(report_id)
        if not report:
            logger.warning(f"Report {report_id} not found.")
            return jsonify({"error": "Report not found."}), 404

        db.session.delete(report)
        db.session.commit()

        logger.info(f"Report {report_id} deleted successfully.")
        return jsonify({"message": "Report deleted successfully.", "deleted_id": report_id})

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete report {report_id}: {str(e)}")
        return jsonify({"error": "Error deleting report."}), 500