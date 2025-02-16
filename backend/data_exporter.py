from flask import Blueprint, request, jsonify, send_file
from models import User, SymptomLog  # ✅ No unnecessary imports
import logging
import io
import csv

# Logger and Blueprint
logger = logging.getLogger("data_exporter")
data_exporter = Blueprint("data_exporter", __name__)

# Route to export symptom logs as CSV
@data_exporter.route("/export_logs", methods=["GET"])
def export_logs():
    try:
        user_id = request.args.get("user_id")
        if not user_id:
            return jsonify({"error": "User ID is required"}), 400

        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404

        symptom_logs = SymptomLog.query.filter_by(user_id=user_id).all()
        if not symptom_logs:
            return jsonify({"message": "No symptom logs found for this user"}), 200

        # Create CSV
        csv_output = io.StringIO()
        csv_writer = csv.writer(csv_output)
        csv_writer.writerow(["Date", "Symptom", "Severity", "Notes"])

        for log in symptom_logs:
            csv_writer.writerow([
                log.date.strftime("%Y-%m-%d %H:%M:%S"),
                log.symptom,
                log.severity or "N/A",  # ✅ Prevents NoneType errors
                log.notes or "N/A"
            ])

        csv_output.seek(0)
        byte_output = io.BytesIO(csv_output.getvalue().encode())  # ✅ Fix: Convert to BytesIO

        return send_file(
            byte_output,
            mimetype="text/csv",
            as_attachment=True,
            download_name="symptom_logs.csv"  # ✅ Fix: Use download_name instead of attachment_filename
        )
    except Exception as e:
        logger.error(f"Error during log export: {str(e)}")
        return jsonify({"error": "An unexpected error occurred while exporting logs"}), 500
