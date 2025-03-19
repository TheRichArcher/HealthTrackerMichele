from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required, verify_jwt_in_request, get_jwt
from datetime import timedelta, datetime
from backend.extensions import db
from backend.models import User, Report, UserTierEnum, CareRecommendationEnum, RevokedToken
from backend.utils.pdf_generator import generate_pdf_report
import stripe
import logging
import os
import json

subscription_routes = Blueprint('subscription_routes', __name__)

# Load environment variables
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
FRONTEND_URL = os.getenv('FRONTEND_URL', 'https://healthtrackermichele.onrender.com')
PRICE_PREMIUM_MONTHLY = os.getenv('PRICE_PREMIUM_MONTHLY', 'price_premium_monthly')
PRICE_ONE_TIME_REPORT = os.getenv('PRICE_ONE_TIME_REPORT', 'price_one_time_report')

logger = logging.getLogger(__name__)

# Log environment variables for debugging
logger.info(f"STRIPE_SECRET_KEY loaded: {os.getenv('STRIPE_SECRET_KEY')[:8] if os.getenv('STRIPE_SECRET_KEY') else 'Not set'}...")
logger.info(f"FRONTEND_URL: {FRONTEND_URL}")
logger.info(f"PRICE_PREMIUM_MONTHLY: {PRICE_PREMIUM_MONTHLY}")
logger.info(f"PRICE_ONE_TIME_REPORT: {PRICE_ONE_TIME_REPORT}")

@subscription_routes.route('/upgrade', methods=['POST'])
def upgrade_subscription():
    logger.info(f"Received request to /api/subscription/upgrade: {request.get_json()}")
    data = request.get_json()
    plan = data.get('plan')
    assessment_data = data.get('assessment_data', {})
    assessment_id = data.get('assessment_id')

    # Optional JWT verification to support both authenticated and guest users
    user_id = None
    try:
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
        logger.info(f"Authenticated user_id: {user_id}")
    except Exception as e:
        logger.debug(f"No valid token provided, proceeding as guest: {str(e)}")

    temp_user_id = None if user_id else f"temp_{os.urandom(8).hex()}"
    logger.info(f"Using user_id: {user_id or temp_user_id}")

    if plan not in ['paid', 'one_time']:
        logger.warning(f"Invalid plan received: {plan}")
        return jsonify({"error": "Invalid plan"}), 400

    price_id = PRICE_PREMIUM_MONTHLY if plan == 'paid' else PRICE_ONE_TIME_REPORT
    logger.info(f"Creating Stripe session for plan: {plan}, price_id: {price_id}")

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription' if plan == 'paid' else 'payment',
            success_url=f'{FRONTEND_URL}/subscription?session_id={{CHECKOUT_SESSION_ID}}',
            cancel_url=f'{FRONTEND_URL}/cancel',
            metadata={
                'user_id': user_id or temp_user_id,
                'assessment_id': assessment_id,
                'assessment_data': json.dumps(assessment_data) if assessment_data else None
            }
        )
        logger.info(f"Stripe session created: {session.id}")
        return jsonify({"checkout_url": session.url}), 200
    except stripe.error.StripeError as e:
        logger.error(f"Stripe checkout error: {str(e)}")
        return jsonify({"error": "Failed to create checkout session", "details": str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error in upgrade_subscription: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

@subscription_routes.route('/confirm', methods=['POST', 'GET'])
def confirm_subscription():
    if request.method == 'GET':
        session_id = request.args.get('session_id')
    else:
        data = request.get_json()
        session_id = data.get('session_id')

    if not session_id:
        return jsonify({"error": "Session ID required"}), 400

    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status != 'paid':
            return jsonify({"error": "Payment not completed"}), 400

        user_id = session.metadata.get('user_id')
        assessment_id = session.metadata.get('assessment_id')
        assessment_data = session.metadata.get('assessment_data')

        # Optional JWT verification
        verify_jwt_in_request(optional=True)
        authenticated_user_id = get_jwt_identity()
        temp_user_id = None

        if authenticated_user_id:
            user = User.query.get(authenticated_user_id)
            if not user:
                return jsonify({"error": "User not found"}), 404
            user_id = authenticated_user_id
        elif user_id and user_id.startswith('temp_'):
            temp_user_id = user_id
        else:
            user = User.query.get(user_id)
            if not user:
                temp_user_id = user_id

        # Use enums for subscription tier
        subscription_tier = UserTierEnum.PAID.value if session.mode == 'subscription' else UserTierEnum.ONE_TIME.value
        report_url = None

        if subscription_tier == UserTierEnum.ONE_TIME.value:
            # Safely parse assessment_data
            try:
                report_data = json.loads(assessment_data) if assessment_data else {}
            except json.JSONDecodeError as e:
                logger.error(f"Invalid assessment_data JSON: {str(e)}")
                report_data = {}
            report_data.update({
                'user_id': user_id or temp_user_id,
                'timestamp': datetime.utcnow().isoformat()
            })
            report_url = generate_pdf_report(report_data)

            report = Report(
                user_id=user_id if not temp_user_id else None,
                temp_user_id=temp_user_id,
                assessment_id=assessment_id,
                title=f"One-Time Report {datetime.utcnow().isoformat()}",
                report_url=report_url,
                status='COMPLETED'
            )
            db.session.add(report)
            db.session.commit()

        if user:
            user.subscription_tier = subscription_tier
            db.session.commit()

        response = {
            "message": "Subscription confirmed",
            "subscription_tier": subscription_tier,
            "report_url": report_url
        }

        # Issue temporary JWT for unauthenticated users
        if temp_user_id and not authenticated_user_id:
            access_token = create_access_token(identity=temp_user_id, expires_delta=timedelta(hours=1))
            response['access_token'] = access_token

        return jsonify(response), 200

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error in confirm_subscription: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Stripe processing error"}), 500
    except Exception as e:
        logger.error(f"Unexpected error in confirm_subscription: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Internal server error"}), 500

@subscription_routes.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """Log out the current user, revoke their JWT, and clear cookies."""
    user_id = get_jwt_identity()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    # Revoke the token by storing its JTI in RevokedToken table
    jwt = get_jwt()
    jti = jwt['jti']
    revoked_token = RevokedToken(jti=jti, revoked_at=datetime.utcnow())
    db.session.add(revoked_token)
    db.session.commit()

    response = jsonify({"message": "Logged out successfully"})
    response.set_cookie("access_token", "", expires=0)
    response.set_cookie("refresh_token", "", expires=0)
    return response, 200

@subscription_routes.route('/status', methods=['GET'])
@jwt_required()
def get_subscription_status():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"subscription_tier": user.subscription_tier.value}), 200