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
import json

subscription_routes = Blueprint('subscription_routes', __name__)

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
BASE_URL = os.getenv('BASE_URL', 'https://healthtrackermichele.onrender.com')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        assessment_data = data.get('assessment_data')

        if not plan:
            return jsonify({'error': 'Plan is required'}), 400

        user_id = None
        is_authenticated_user = False
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                verify_jwt_in_request(optional=True)
                user_id = get_jwt_identity()
                if user_id and str(user_id).startswith('user_'):
                    user_id = int(user_id.replace('user_', ''))
                    is_authenticated_user = True
            except Exception as e:
                logger.warning(f"Invalid token: {str(e)}")

        user_id = user_id or generate_temp_user_id(request)
        user = User.query.get(user_id) if is_authenticated_user else None

        if plan == 'one_time':
            if is_authenticated_user:
                if not assessment_id:
                    logger.error(f"Assessment ID required for one-time report purchase, user_id={user_id}")
                    return jsonify({'error': 'An assessment is required before purchasing a one-time report'}), 400

                symptom_log = SymptomLog.query.get(assessment_id)
                if not symptom_log or (user and symptom_log.user_id != user_id):
                    return jsonify({'error': 'Invalid or unauthorized assessment'}), 400

                notes = json.loads(symptom_log.notes) if symptom_log.notes and symptom_log.notes.startswith('{') else {}
                assessment_data = {
                    'symptom': symptom_log.symptom_name,
                    'condition_common': notes.get('condition_common', 'Unknown'),
                    'condition_medical': notes.get('condition_medical', 'N/A'),
                    'confidence': notes.get('confidence', 0),
                    'triage_level': notes.get('triage_level', 'MODERATE'),
                    'care_recommendation': notes.get('care_recommendation', 'Consult a healthcare provider')
                }
            else:
                if not assessment_id and not assessment_data:
                    logger.error(f"Assessment data required for one-time report purchase for unauthenticated user, user_id={user_id}")
                    return jsonify({'error': 'Assessment data is required for one-time report purchase'}), 400

            report = Report(
                user_id=user_id if is_authenticated_user else None,
                temp_user_id=user_id if not is_authenticated_user else None,
                assessment_id=assessment_id if is_authenticated_user else None,
                status='PENDING',
                created_at=datetime.utcnow(),
                report_url=None
            )
            db.session.add(report)
            db.session.commit()

            success_url = f"{BASE_URL}/chat?session_id={{CHECKOUT_SESSION_ID}}"
            logger.info(f"Stripe success URL set to: {success_url}")
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {'name': 'One-Time Health Report'},
                        'unit_amount': 499,
                    },
                    'quantity': 1,
                }],
                mode='payment',
                metadata={
                    'user_id': str(user_id),
                    'plan': 'one_time',
                    'assessment_id': str(assessment_id) if assessment_id else 'none',
                    'assessment_data': json.dumps(assessment_data) if assessment_data else 'none',
                    'report_id': report.id
                },
                success_url=success_url,
                cancel_url=f"{BASE_URL}/chat",
            )
            logger.info(f"Stripe checkout session created with ID: {checkout_session.id}")
            logger.info(f"Checkout URL provided to client: {checkout_session.url}")
            return jsonify({'checkout_url': checkout_session.url}), 200

        elif plan == 'subscription':
            if not user:
                return jsonify({'error': 'Authentication required for subscription purchase'}), 401

            success_url = f"{BASE_URL}/chat?session_id={{CHECKOUT_SESSION_ID}}"
            logger.info(f"Stripe success URL set to: {success_url}")
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {'name': 'HealthTracker Subscription'},
                        'unit_amount': 999,
                        'recurring': {'interval': 'month'},
                    },
                    'quantity': 1,
                }],
                mode='subscription',
                metadata={
                    'user_id': str(user_id),
                    'plan': 'subscription',
                    'assessment_id': str(assessment_id) if assessment_id else 'none'
                },
                success_url=success_url,
                cancel_url=f"{BASE_URL}/chat",
            )
            logger.info(f"Stripe checkout session created with ID: {checkout_session.id}")
            logger.info(f"Checkout URL provided to client: {checkout_session.url}")
            return jsonify({'checkout_url': checkout_session.url}), 200

        return jsonify({'error': 'Invalid plan specified'}), 400

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error initiating checkout: user_id={user_id}, plan={plan}, error={str(e)}")
        return jsonify({'error': f'Failed to initiate checkout: {str(e)}'}), 500

@subscription_routes.route('/confirm', methods=['GET'])
def confirm_payment():
    session_id = request.args.get('session_id')
    logger.info(f"Received confirm request with session_id: {session_id}")

    try:
        if not session_id:
            logger.error("No session_id provided in query parameters")
            return jsonify({'error': 'Session ID is required'}), 400

        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status != 'paid':
            logger.error(f"Payment not completed for session {session_id}")
            return jsonify({'error': 'Payment not completed'}), 400

        user_id = session.metadata.get('user_id')
        if not user_id:
            logger.error(f"User ID not found in metadata for session {session_id}")
            return jsonify({'error': 'User ID not found in metadata'}), 400

        plan = session.metadata.get('plan')
        if not plan:
            logger.error(f"Plan not found in metadata for session {session_id}")
            return jsonify({'error': 'Plan not found in metadata'}), 400

        current_user = None
        is_authenticated_user = False
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                verify_jwt_in_request(optional=True)
                current_user = get_jwt_identity()
                if current_user and str(current_user).startswith('user_'):
                    current_user = int(current_user.replace('user_', ''))
                    is_authenticated_user = True
            except Exception as e:
                logger.warning(f"Invalid token in /confirm: {str(e)}")

        if user_id and str(user_id).startswith('user_'):
            user_id = int(user_id.replace('user_', ''))
        user = User.query.get(user_id) if str(user_id).startswith('user_') else None

        if plan == 'one_time':
            report_id = session.metadata.get('report_id')
            if not report_id:
                logger.error(f"Report ID not found in metadata for session {session_id}")
                return jsonify({'error': 'Report ID not found in metadata'}), 400

            report = Report.query.get(report_id)
            if not report:
                logger.error(f"Report not found for report_id {report_id}")
                return jsonify({'error': 'Report not found'}), 404

            if is_authenticated_user and report.user_id != user_id:
                logger.error(f"Unauthorized access to report for user_id {user_id}, report_id {report_id}")
                return jsonify({'error': 'Unauthorized access to report'}), 403

            if not is_authenticated_user and report.temp_user_id != user_id:
                logger.error(f"Unauthorized access to report for temp_user_id {user_id}, report_id {report_id}")
                return jsonify({'error': 'Unauthorized access to report'}), 403

            assessment_id = session.metadata.get('assessment_id')
            assessment_data = session.metadata.get('assessment_data')

            if assessment_id and assessment_id != 'none':
                symptom_log = SymptomLog.query.get(assessment_id)
                if not symptom_log:
                    logger.error(f"Associated assessment not found for assessment_id {assessment_id}")
                    return jsonify({'error': 'Associated assessment not found'}), 400

                notes = json.loads(symptom_log.notes) if symptom_log.notes and symptom_log.notes.startswith('{') else {}
                report_data = {
                    'user_id': user_id,
                    'timestamp': datetime.utcnow().isoformat(),
                    'condition_common': notes.get('condition_common', 'Unknown'),
                    'condition_medical': notes.get('condition_medical', 'N/A'),
                    'confidence': notes.get('confidence', 0),
                    'triage_level': notes.get('triage_level', 'MODERATE'),
                    'care_recommendation': notes.get('care_recommendation', 'Consult a healthcare provider')
                }
            elif assessment_data and assessment_data != 'none':
                assessment_data = json.loads(assessment_data)
                report_data = {
                    'user_id': user_id,
                    'timestamp': datetime.utcnow().isoformat(),
                    'condition_common': assessment_data.get('condition_common', 'Unknown'),
                    'condition_medical': assessment_data.get('condition_medical', 'N/A'),
                    'confidence': assessment_data.get('confidence', 0),
                    'triage_level': assessment_data.get('triage_level', 'MODERATE'),
                    'care_recommendation': assessment_data.get('care_recommendation', 'Consult a healthcare provider')
                }
            else:
                logger.error(f"Assessment data not found in metadata for session {session_id}")
                return jsonify({'error': 'Assessment data not found in metadata'}), 400

            report_url = generate_pdf_report(report_data)
            logger.info(f"Generated report URL for session {session_id}: {report_url}")

            report.status = 'COMPLETED'
            report.report_url = report_url
            report.updated_at = datetime.utcnow()
            db.session.commit()

            if user:
                user.subscription_tier = UserTierEnum.ONE_TIME.value
                db.session.commit()

            logger.info(f"Successfully confirmed one-time report for session {session_id}, report_id {report_id}")
            return jsonify({'success': True, 'report_url': report_url}), 200

        elif plan == 'subscription':
            if not is_authenticated_user:
                logger.error(f"Authentication required for subscription confirmation, session {session_id}")
                return jsonify({'error': 'Authentication required for subscription confirmation'}), 401

            if current_user != user_id:
                logger.error(f"User ID mismatch: token user_id={current_user}, metadata user_id={user_id}")
                return jsonify({'error': 'User ID mismatch between token and metadata'}), 403

            user = User.query.get(user_id)
            if not user:
                logger.error(f"User not found for user_id {user_id}")
                return jsonify({'error': 'User not found'}), 404

            user.subscription_tier = UserTierEnum.PAID.value
            user.updated_at = datetime.utcnow()
            db.session.commit()

            logger.info(f"Successfully confirmed subscription for session {session_id}, user_id {user_id}")
            return jsonify({'success': True, 'message': 'Subscription activated successfully'}), 200

        logger.error(f"Invalid plan specified in metadata: {plan}")
        return jsonify({'error': 'Invalid plan specified in metadata'}), 400

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error confirming payment: session_id={session_id}, error={str(e)}", exc_info=True)
        return jsonify({'error': f'Failed to confirm payment: {str(e)}'}), 500

@subscription_routes.route('/status', methods=['GET'])
@token_required
def subscription_status(current_user=None):
    if not current_user:
        return jsonify({'error': 'Authentication required'}), 401

    user_id = current_user.get("user_id")
    if user_id and str(user_id).startswith('user_'):
        user_id = int(user_id.replace('user_', ''))
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    return jsonify({'subscription_tier': user.subscription_tier.value}), 200

@subscription_routes.route('/test', methods=['GET'])
def test_endpoint():
    logger.info("Test endpoint hit")
    return jsonify({'message': 'Test successful'}), 200