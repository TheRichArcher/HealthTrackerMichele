from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from backend.models import db, User, Report, SymptomLog
from backend.utils.auth import token_required, generate_temp_user_id
from backend.utils.pdf_generator import generate_pdf_report
from datetime import datetime
import stripe
import os
from urllib.parse import urljoin
from enum import Enum
import logging

# Define Blueprint without url_prefix
subscription_routes = Blueprint('subscription_routes', __name__)

# Configure Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
BASE_URL = os.getenv('BASE_URL', 'https://healthtrackermichele.onrender.com')

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Enum for user tiers
class UserTierEnum(Enum):
    FREE = "FREE"
    ONE_TIME = "ONE_TIME"
    PAID = "PAID"

@subscription_routes.route('/upgrade', methods=['POST'])
def upgrade():
    try:
        data = request.get_json()
        plan = data.get('plan')
        assessment_id = data.get('assessment_id')

        if not plan:
            return jsonify({'error': 'Plan is required'}), 400

        # Handle authentication (optional)
        auth_header = request.headers.get("Authorization")
        user_id = None
        if auth_header and auth_header.startswith("Bearer "):
            try:
                verify_jwt_in_request(optional=True)
                user_id = get_jwt_identity()
            except Exception as e:
                logger.warning(f"Invalid token: {str(e)}")
        user_id = user_id or generate_temp_user_id(request)
        user = User.query.get(user_id) if user_id and user_id.startswith('user_') else None

        # Fallback if assessment_id is missing (log and proceed)
        if not assessment_id:
            logger.warning(f"Assessment ID missing for user_id={user_id}, plan={plan}")
            assessment_id = None

        # Validate assessment_id
        if assessment_id:
            symptom_log = SymptomLog.query.get(assessment_id)
            if not symptom_log or (user and symptom_log.user_id != user_id):
                return jsonify({'error': 'Invalid or unauthorized assessment'}), 400

        if plan == 'one_time':
            report = Report(
                user_id=user_id,
                assessment_id=assessment_id or None,
                status='PENDING',
                created_at=datetime.utcnow(),
                report_url=None
            )
            db.session.add(report)
            db.session.commit()

            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[
                    {
                        'price_data': {
                            'currency': 'usd',
                            'product_data': {
                                'name': 'One-Time Health Report',
                            },
                            'unit_amount': 499,  # $4.99
                        },
                        'quantity': 1,
                    },
                ],
                mode='payment',
                metadata={
                    'user_id': user_id,
                    'plan': 'one_time',
                    'assessment_id': assessment_id or 'none',
                    'report_id': report.id
                },
                success_url=f"{BASE_URL}/chat?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{BASE_URL}/chat",
            )
            return jsonify({'checkout_url': checkout_session.url}), 200

        elif plan == 'subscription':
            if not user:  # Require authenticated user for subscription
                return jsonify({'error': 'Authentication required for subscription'}), 401

            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[
                    {
                        'price_data': {
                            'currency': 'usd',
                            'product_data': {
                                'name': 'HealthTracker Subscription',
                            },
                            'unit_amount': 999,  # $9.99
                            'recurring': {
                                'interval': 'month',
                            },
                        },
                        'quantity': 1,
                    },
                ],
                mode='subscription',
                metadata={
                    'user_id': user_id,
                    'plan': 'subscription',
                    'assessment_id': assessment_id or 'none'
                },
                success_url=f"{BASE_URL}/chat?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{BASE_URL}/chat",
            )
            return jsonify({'checkout_url': checkout_session.url}), 200

        return jsonify({'error': 'Invalid plan'}), 400

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error initiating checkout: user_id={user_id}, plan={plan}, error={str(e)}")
        return jsonify({'error': 'Failed to initiate checkout'}), 500

@subscription_routes.route('/confirm', methods=['POST'])
@token_required
def confirm_payment(current_user=None):
    try:
        data = request.get_json()
        session_id = data.get('session_id')

        if not session_id:
            return jsonify({'error': 'Session ID is required'}), 400

        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status != 'paid':
            return jsonify({'error': 'Payment not completed'}), 400

        user_id = session.metadata.get('user_id')
        if not user_id:
            return jsonify({'error': 'User ID not found in metadata'}), 400

        user = User.query.get(user_id) if user_id.startswith('user_') else None
        plan = session.metadata.get('plan')
        if not plan:
            return jsonify({'error': 'Plan not found in metadata'}), 400

        if plan == 'one_time':
            report_id = session.metadata.get('report_id')
            if not report_id:
                return jsonify({'error': 'Report ID not found in metadata'}), 400

            report = Report.query.get(report_id)
            if not report or report.user_id != user_id:
                return jsonify({'error': 'Report not found or unauthorized'}), 403

            assessment_id = session.metadata.get('assessment_id')
            symptom_log = SymptomLog.query.get(assessment_id) if assessment_id != 'none' else None

            report_data = {
                'user_id': user_id,
                'timestamp': datetime.utcnow().isoformat(),
                'condition_common': symptom_log.condition_common if symptom_log else 'Unknown',
                'condition_medical': symptom_log.condition_medical if symptom_log else 'N/A',
                'confidence': symptom_log.confidence if symptom_log else 0,
                'triage_level': symptom_log.triage_level if symptom_log else 'N/A',
                'care_recommendation': symptom_log.care_recommendation if symptom_log else 'N/A'
            }
            report_url = generate_pdf_report(report_data)

            report.status = 'COMPLETED'
            report.report_url = report_url
            report.updated_at = datetime.utcnow()
            db.session.commit()

            if user:
                user.subscription_tier = UserTierEnum.ONE_TIME.value
                db.session.commit()

            return jsonify({'report_url': report_url}), 200

        elif plan == 'subscription':
            if not current_user:
                return jsonify({'error': 'Authentication required for subscription'}), 401

            user = User.query.get(current_user['user_id'])
            if not user:
                return jsonify({'error': 'User not found'}), 404

            user.subscription_tier = UserTierEnum.PAID.value
            user.updated_at = datetime.utcnow()
            db.session.commit()

            return jsonify({'message': 'Subscription activated successfully'}), 200

        return jsonify({'error': 'Invalid plan'}), 400

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error confirming payment: session_id={session_id}, error={str(e)}")
        return jsonify({'error': 'Failed to confirm payment'}), 500