from flask import Blueprint, jsonify, request
from backend.extensions import db
from backend.models import OneTimeReport  # Import model
import os
import logging
import stripe  # Added for Stripe API

# Blueprint setup
one_time_report_bp = Blueprint('one_time_report', __name__)
logger = logging.getLogger(__name__)

@one_time_report_bp.route('/one-time-report', methods=['GET'])
def get_one_time_report():
    """
    Fetch a one-time report based on session_id.
    Returns report details in a format expected by OneTimeReportPage.jsx.
    """
    session_id = request.args.get('session_id')
    if not session_id:
        logger.warning("Missing session_id in /api/one-time-report request")
        return jsonify({"error": "Missing session_id"}), 400

    try:
        # Query OneTimeReport for the session_id
        report = OneTimeReport.query.filter_by(session_id=session_id).first()
        if not report:
            logger.warning(f"No report found for session_id: {session_id}")
            return jsonify({"error": "Report not found"}), 404

        # Verify file exists
        report_filename = os.path.basename(report.report_url)
        report_file_path = os.path.join(API_CONFIG["REPORTS_DIR"], report_filename)
        if not os.path.exists(report_file_path):
            logger.error(f"Report file missing at: {report_file_path}")
            return jsonify({"error": "Report file not found"}), 404

        # Verify Stripe session (optional, for extra validation)
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status != 'paid':
            logger.warning(f"Payment not completed for session: {session_id}")
            return jsonify({"error": "Payment not completed"}), 400
        if session.status == 'expired' or session.canceled_at:
            logger.warning(f"Session expired or canceled: {session_id}")
            return jsonify({"error": "Checkout session expired or canceled"}), 410

        # Response for frontend
        report_data = {
            "title": f"One-Time Health Report - {report.user_id}",
            "content": "Your one-time health report is ready. Download it below.",
            "user_id": report.user_id,
            "payment_date": int(report.created_at.timestamp()),  # From DB
            "report_url": report.report_url
        }

        logger.info(f"Successfully fetched report for session_id: {session_id}")
        return jsonify(report_data), 200

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error fetching session {session_id}: {str(e)}")
        return jsonify({"error": "Failed to retrieve payment session", "details": str(e)}), 500
    except Exception as e:
        logger.error(f"Error fetching report for session_id {session_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

from app import API_CONFIG  # Adjusted for app.py at root