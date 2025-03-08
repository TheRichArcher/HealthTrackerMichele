from flask import Blueprint, request, jsonify, send_file
from backend.models import User, SymptomLog, Symptom
from backend.extensions import db
import logging
import io
import csv
from datetime import datetime

# Logger setup
logger = logging.getLogger("data_exporter")

# Create Blueprint without hardcoded prefix
data_exporter = Blueprint("data_exporter", __name__)

@data_exporter.route("/symptom-logs", methods=["GET"])
def export_symptom_logs():
    """Export user symptom logs as a CSV file."""
    try:
        user_id = request.args.get("user_id")
        if not user_id:
            logger.warning("Export attempt without user_id")
            return jsonify({"error": "User ID is required"}), 400

        # Verify user exists
        user = User.query.get(user_id)
        if not user:
            logger.warning(f"Export attempt for non-existent user ID: {user_id}")
            return jsonify({"error": "User not found"}), 404

        # Get all symptom logs for the user with joined symptom data
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

        # Create CSV in memory
        csv_output = io.StringIO()
        csv_writer = csv.writer(csv_output)
        
        # Write header row
        csv_writer.writerow(["Date", "Symptom", "Severity", "Notes"])
        
        # Write data rows
        for log_data in logs:
            log = log_data[0]  # The SymptomLog object
            symptom_name = log_data[1]  # The symptom name from the join
            
            csv_writer.writerow([
                log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                symptom_name,
                log.severity if log.severity is not None else "N/A",
                log.notes if log.notes else "N/A"
            ])

        # Reset pointer to start of file and convert to bytes
        csv_output.seek(0)
        byte_output = io.BytesIO(csv_output.getvalue().encode('utf-8'))
        
        # Generate a filename with timestamp
        filename = f"symptom_logs_{user.username}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        
        logger.info(f"Successfully generated symptom log export for user ID: {user_id}")
        
        # Send the file
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
def export_health_data():
    """Export user health data as a CSV file."""
    try:
        user_id = request.args.get("user_id")
        if not user_id:
            logger.warning("Health data export attempt without user_id")
            return jsonify({"error": "User ID is required"}), 400

        # Verify user exists
        user = User.query.get(user_id)
        if not user:
            logger.warning(f"Health data export attempt for non-existent user ID: {user_id}")
            return jsonify({"error": "User not found"}), 404

        # Get all health data for the user
        health_data = user.health_data
        
        if not health_data:
            logger.info(f"No health data found for user ID: {user_id}")
            return jsonify({"message": "No health data found for this user"}), 200

        # Create CSV in memory
        csv_output = io.StringIO()
        csv_writer = csv.writer(csv_output)
        
        # Write header row
        csv_writer.writerow(["Date", "Data Type", "Value"])
        
        # Write data rows
        for data in health_data:
            csv_writer.writerow([
                data.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                data.data_type,
                data.value
            ])

        # Reset pointer to start of file and convert to bytes
        csv_output.seek(0)
        byte_output = io.BytesIO(csv_output.getvalue().encode('utf-8'))
        
        # Generate a filename with timestamp
        filename = f"health_data_{user.username}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        
        logger.info(f"Successfully generated health data export for user ID: {user_id}")
        
        # Send the file
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
def export_all_data():
    """Export all user data (symptoms and health data) as a ZIP file."""
    try:
        user_id = request.args.get("user_id")
        if not user_id:
            logger.warning("Complete data export attempt without user_id")
            return jsonify({"error": "User ID is required"}), 400

        # This is a placeholder for a more complex export function
        # that would combine multiple data types into a ZIP file
        return jsonify({
            "message": "This feature is not yet implemented. Please use the individual export endpoints."
        }), 501
        
    except Exception as e:
        logger.error(f"Error during complete data export: {str(e)}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500