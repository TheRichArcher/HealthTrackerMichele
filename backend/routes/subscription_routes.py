from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from backend.models import User, SymptomLog, Report, UserTierEnum, CareRecommendationEnum
from backend.extensions import db
from backend.utils.auth import generate_temp_user_id, token_required
from backend.utils.pdf_generator import generate_pdf_report
import openai
import os
import json
import logging
from datetime import datetime
import time
import stripe
from typing import Optional

subscription_routes = Blueprint("subscription_routes", __name__, url_prefix="/api/subscription")

# Configure logging
logger = logging.getLogger(__name__)

# Stripe setup
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
if not stripe.api_key:
    raise ValueError("STRIPE_SECRET_KEY environment variable not set.")

# Constants
PLAN_PRICES = {
    "one_time": 499,  # $4.99 in cents
    "paid": 999       # $9.99/month in cents
}

def is_premium_user(user: Optional[User]) -> bool:
    """Check if the user has a premium subscription tier."""
    return getattr(user, "subscription_tier", UserTierEnum.FREE.value) in [
        UserTierEnum.PAID.value,
        UserTierEnum.ONE_TIME.value
    ]

@subscription_routes.route("/status", methods=["GET"])
@token_required
def get_subscription_status(current_user=None):
    """Retrieve the current user's subscription status."""
    if not current_user:
        return jsonify({"error": "Authentication required"}), 401
    user_id = current_user.get("user_id")
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"subscription_tier": user.subscription_tier}), 200

@subscription_routes.route("/upgrade", methods=["POST"])
def upgrade_subscription():
    """Initiate a subscription upgrade via Stripe Checkout."""
    auth_header = request.headers.get("Authorization")
    user_id = None
    current_user = None

    if auth_header and auth_header.startswith("Bearer "):
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
            if user_id and user_id.startswith('user_'):
                user_id = int(user_id.replace('user_', ''))
            current_user = User.query.get(user_id)
        except Exception as e:
            logger.warning(f"Invalid token during upgrade: {str(e)}")

    user_id = user_id if user_id is not None else generate_temp_user_id(request)
    data = request.get_json() or {}
    plan = data.get("plan")
    assessment_id = data.get("assessment_id")
    assessment_data = data.get("assessment_data")

    if not plan or plan not in PLAN_PRICES:
        return jsonify({"error": "Invalid or missing plan"}), 400

    try:
        # Create Stripe Checkout session
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": f"HealthTracker {plan.capitalize()} Plan"},
                        "unit_amount": PLAN_PRICES[plan],
                    },
                    "quantity": 1,
                }
            ],
            mode="payment" if plan == "one_time" else "subscription",
            success_url=current_app.config["FRONTEND_URL"] + "/subscription?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=current_app.config["FRONTEND_URL"] + "/subscription/cancel",
            metadata={
                "user_id": str(user_id),
                "plan": plan,
                "assessment_id": str(assessment_id) if assessment_id else "none",
                "assessment_data": json.dumps(assessment_data) if assessment_data else "none"
            },
        )
        return jsonify({"checkout_url": checkout_session.url}), 200
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error during checkout: {str(e)}")
        return jsonify({"error": "Failed to initiate payment"}), 500
    except Exception as e:
        logger.error(f"Unexpected error during upgrade: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@subscription_routes.route("/confirm", methods=["POST"])
def confirm_subscription():
    """Confirm subscription payment and generate report if applicable."""
    auth_header = request.headers.get("Authorization")
    user_id = None
    current_user = None

    if auth_header and auth_header.startswith("Bearer "):
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_jwt_identity()
            if user_id and user_id.startswith('user_'):
                user_id = int(user_id.replace('user_', ''))
            current_user = User.query.get(user_id)
        except Exception as e:
            logger.warning(f"Invalid token during confirmation: {str(e)}")

    user_id = user_id if user_id is not None else generate_temp_user_id(request)
    data = request.get_json() or {}
    session_id = data.get("session_id")

    if not session_id:
        return jsonify({"error": "Session ID is required"}), 400

    try:
        # Verify payment with Stripe
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status != "paid":
            return jsonify({"error": "Payment not confirmed"}), 400

        customer_id = session.customer
        plan = session.metadata.get("plan")
        assessment_id = session.metadata.get("assessment_id")
        assessment_data = session.metadata.get("assessment_data")

        # Update user subscription tier if authenticated
        if user_id and isinstance(user_id, int):
            user = User.query.get(user_id)
            if user:
                if plan == "paid":
                    user.subscription_tier = UserTierEnum.PAID.value
                elif plan == "one_time":
                    user.subscription_tier = UserTierEnum.ONE_TIME.value
                db.session.commit()
                logger.info(f"Updated subscription tier for user {user_id} to {user.subscription_tier}")

        # Generate report for one-time purchases
        report_url = None
        if plan == "one_time":
            if assessment_id and assessment_id != "none":
                symptom_log = SymptomLog.query.get(int(assessment_id))
                if symptom_log and symptom_log.notes:
                    notes = json.loads(symptom_log.notes)
                    report_data = {
                        'user_id': user_id,
                        'timestamp': datetime.utcnow().isoformat(),
                        'condition_common': notes.get('condition_common', 'Unknown'),
                        'condition_medical': notes.get('condition_medical', 'N/A'),
                        'confidence': float(str(notes.get('confidence', 0)).rstrip('%')) if '%' in str(notes.get('confidence', 0)) else float(notes.get('confidence', 0)),
                        'triage_level': notes.get('triage_level', 'MODERATE'),
                        'care_recommendation': notes.get('care_recommendation', 'Consult a healthcare provider'),
                        'symptoms': symptom_log.symptom_name
                    }
                    report_url = generate_pdf_report(report_data)
            elif assessment_data and assessment_data != "none":
                try:
                    assessment_data_dict = json.loads(assessment_data)
                    if not isinstance(assessment_data_dict, dict):
                        raise ValueError("Invalid assessment data format")
                    report_data = {
                        'user_id': user_id,
                        'timestamp': datetime.utcnow().isoformat(),
                        'condition_common': assessment_data_dict.get('condition_common', 'Unknown'),
                        'condition_medical': assessment_data_dict.get('condition_medical', 'N/A'),
                        'confidence': float(str(assessment_data_dict.get('confidence', 0)).rstrip('%')) if '%' in str(assessment_data_dict.get('confidence', 0)) else float(assessment_data_dict.get('confidence', 0)),
                        'triage_level': assessment_data_dict.get('triage_level', 'MODERATE'),
                        'care_recommendation': assessment_data_dict.get('care_recommendation', 'Consult a healthcare provider')
                    }
                    report_url = generate_pdf_report(report_data)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON in assessment_data for session {session_id}: Malformed data")
                    return jsonify({'error': 'Invalid assessment data format'}), 400
                except ValueError as e:
                    logger.error(f"Validation error in assessment_data for session {session_id}: {str(e)}")
                    return jsonify({'error': 'Invalid assessment data format'}), 400

            if report_url:
                report = Report(
                    user_id=user_id if isinstance(user_id, int) else None,
                    title=f"One-Time Report - {datetime.utcnow().strftime('%Y-%m-%d')}",
                    content=json.dumps(report_data),
                    care_recommendation=CareRecommendationEnum.SEE_DOCTOR,
                    created_at=datetime.utcnow(),
                    report_url=report_url
                )
                db.session.add(report)
                db.session.commit()
                logger.info(f"Generated report for user {user_id} with URL: {report_url}")

        return jsonify({
            "message": "Subscription confirmed",
            "subscription_tier": user.subscription_tier if user else "guest",
            "report_url": report_url
        }), 200
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error during confirmation: {str(e)}")
        return jsonify({"error": "Payment confirmation failed"}), 500
    except Exception as e:
        logger.error(f"Unexpected error during confirmation: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Internal server error"}), 500

@subscription_routes.route("/logout", methods=["POST"])
@token_required
def logout(current_user=None):
    """Log out the current user and clear their JWT."""
    if not current_user:
        return jsonify({"error": "Authentication required"}), 401
    response = jsonify({"message": "Logged out successfully"})
    response.set_cookie("access_token", "", expires=0)
    response.set_cookie("refresh_token", "", expires=0)
    return response, 200