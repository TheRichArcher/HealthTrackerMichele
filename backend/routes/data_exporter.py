from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.models import User, SymptomLog, Symptom, UserTierEnum
from backend.extensions import db
import logging
import io
import csv
from datetime import datetime

logger = logging.getLogger("data_exporter")
data_exporter = Blueprint("data_exporter", __name__)

@data_exporter.route("/symptom-logs", methods=["GET"])
@jwt_required()
def export_symptom_logs():
    """Export user symptom logs as a CSV file for PAID users only."""
    try:
        user_id = request.args.get("user_id")
        if not user_id:
            logger.warning("Export attempt without user_id")
            return jsonify({"error": "User ID is required"}), 400

        authenticated_user_id = get_jwt_identity()
        if str(user_id) != str(authenticated_user_id):
            logger.warning(f"Unauthorized export attempt by {authenticated_user_id} for user {user_id}")
            return jsonify({"error": "Unauthorized access"}), 403

        user = User.query.filter(User.id == user_id, User.deleted_at.is_(None)).first()
        if not user:
            logger.warning(f"Export attempt for non-existent user ID: {user_id}")
            return jsonify({"error": "User not found"}), 404

        if user.subscription_tier != UserTierEnum.PAID.value:
            logger.info(f"Non-PAID user {user_id} attempted export")
            return jsonify({"error": "Health data export available for Premium subscribers only", "requires_upgrade": True}), 403

        logs = db.session.query(
            SymptomLog, Symptom.name.label('symptom_name')
        ).join(
            Symptom, SymptomLog.symptom_id == Symptom.id
        ).filter(
            SymptomLog.user_id == user_id
        ).all()

        if not logs:
            logger.info(f"No symptom logs found for user ID: {user_id}")
            return jsonify({"message": "No symptom logs found for this user"}), 200

        csv_output = io.StringIO()
        csv_writer = csv.writer(csv_output)
        csv_writer.writerow(["Date", "Symptom", "Severity", "Notes"])
        
        for log_data in logs:
            log = log_data[0]
            symptom_name = log_data[1]
            csv_writer.writerow([
                log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                symptom_name,
                log.severity if log.severity is not None else "N/A",
                log.notes if log.notes else "N/A"
            ])

        csv_output.seek(0)
        byte_output = io.BytesIO(csv_output.getvalue().encode('utf-8'))
        display_name = user.username or user.email.split('@')[0]
        filename = f"symptom_logs_{display_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        
        logger.info(f"Successfully generated symptom log export for user ID: {user_id}")
        return send_file(
            byte_output,
            mimetype="text/csv",
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        logger.error(f"Error during symptom log export: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": "An unexpected error occurred while exporting logs"}), 500

@data_exporter.route("/health-data", methods=["GET"])
@jwt_required()
def export_health_data():
    """Export user health data as a CSV file for PAID users only."""
    try:
        user_id = request.args.get("user_id")
        if not user_id:
            logger.warning("Health data export attempt without user_id")
            return jsonify({"error": "User ID is required"}), 400

        authenticated_user_id = get_jwt_identity()
        if str(user_id) != str(authenticated_user_id):
            logger.warning(f"Unauthorized export attempt by {authenticated_user_id} for user {user_id}")
            return jsonify({"error": "Unauthorized access"}), 403

        user = User.query.filter(User.id == user_id, User.deleted_at.is_(None)).first()
        if not user:
            logger.warning(f"Health data export attempt for non-existent user ID: {user_id}")
            return jsonify({"error": "User not found"}), 404

        if user.subscription_tier != UserTierEnum.PAID.value:
            logger.info(f"Non-PAID user {user_id} attempted export")
            return jsonify({"error": "Health data export available for Premium subscribers only", "requires_upgrade": True}), 403

        health_data = user.health_data
        
        if not health_data:
            logger.info(f"No health data found for user ID: {user_id}")
            return jsonify({"message": "No health data found for this user"}), 200

        csv_output = io.StringIO()
        csv_writer = csv.writer(csv_output)
        csv_writer.writerow(["Date", "Data Type", "Value"])
        
        for data in health_data:
            csv_writer.writerow([
                data.recorded_at.strftime("%Y-%m-%d %H:%M:%S"),
                data.data_type,
                data.value
            ])

        csv_output.seek(0)
        byte_output = io.BytesIO(csv_output.getvalue().encode('utf-8'))
        display_name = user.username or user.email.split('@')[0]
        filename = f"health_data_{display_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        
        logger.info(f"Successfully generated health data export for user ID: {user_id}")
        return send_file(
            byte_output,
            mimetype="text/csv",
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        logger.error(f"Error during health data export: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": "An unexpected error occurred while exporting health data"}), 500

@data_exporter.route("/all-data", methods=["GET"])
@jwt_required()
def export_all_data():
    """Export all user data (symptoms and health data) as a ZIP file for PAID users only."""
    try:
        user_id = request.args.get("user_id")
        if not user_id:
            logger.warning("Complete data export attempt without user_id")
            return jsonify({"error": "User ID is required"}), 400

        authenticated_user_id = get_jwt_identity()
        if str(user_id) != str(authenticated_user_id):
            logger.warning(f"Unauthorized export attempt by {authenticated_user_id} for user {user_id}")
            return jsonify({"error": "Unauthorized access"}), 403

        user = User.query.filter(User.id == user_id, User.deleted_at.is_(None)).first()
        if not user:
            logger.warning(f"All data export attempt for non-existent user ID: {user_id}")
            return jsonify({"error": "User not found"}), 404

        if user.subscription_tier != UserTierEnum.PAID.value:
            logger.info(f"Non-PAID user {user_id} attempted export")
            return jsonify({"error": "Health data export available for Premium subscribers only", "requires_upgrade": True}), 403

        # Placeholder for ZIP implementation
        return jsonify({
            "message": "This feature is not yet implemented. Please use the individual export endpoints."
        }), 501
        
    except Exception as e:
        logger.error(f"Error during complete data export: {str(e)}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500