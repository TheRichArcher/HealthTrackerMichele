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
                'assessment_data': json.dumps(assessment_data) if assessment_data else None,
                'plan': plan
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
    logger.info("Received request to /api/subscription/confirm")
    try:
        # Safely handle Authorization header
        auth_header = request.headers.get("Authorization", "")
        user_id = None
        if auth_header.startswith("Bearer "):
            try:
                verify_jwt_in_request(optional=True)
                user_id = get_jwt_identity()
                if user_id and user_id.startswith('user_'):
                    user_id = int(user_id.replace('user_', ''))
                logger.info(f"Authenticated user_id from JWT: {user_id}")
            except Exception as e:
                logger.warning(f"JWT parsing failed, proceeding without auth: {str(e)}")

        # Get session_id from POST body or GET query
        if request.method == 'GET':
            session_id = request.args.get('session_id')
        else:
            data = request.get_json() or {}
            session_id = data.get('session_id')

        if not session_id:
            logger.warning("Missing session_id in request")
            return jsonify({"error": "Session ID required"}), 400

        # Retrieve Stripe session
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status != 'paid':
            logger.warning(f"Payment not completed for session: {session_id}")
            return jsonify({"error": "Payment not completed"}), 400

        # Extract metadata
        metadata_user_id = session.metadata.get('user_id')
        assessment_id = session.metadata.get('assessment_id')
        assessment_data = session.metadata.get('assessment_data')
        plan = session.metadata.get('plan')

        # Determine user context
        temp_user_id = None
        if user_id and isinstance(user_id, int):
            user = User.query.get(user_id)
            if not user:
                logger.warning(f"Authenticated user not found: {user_id}")
                return jsonify({"error": "User not found"}), 404
        elif metadata_user_id and metadata_user_id.startswith('temp_'):
            temp_user_id = metadata_user_id
        else:
            temp_user_id = metadata_user_id or f"temp_{os.urandom(8).hex()}"

        # Process based on plan
        report_url = None
        subscription_tier = UserTierEnum.PAID.value if plan == 'paid' else UserTierEnum.ONE_TIME.value

        if plan == 'one_time':
            # Handle one-time report (no auth required)
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
            logger.info(f"Report generated: {report_url}")

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

        elif plan == 'paid':
            # Handle subscription (auth required)
            if not user_id or not isinstance(user_id, int):
                logger.warning("Authentication required for paid plan but no valid user_id")
                return jsonify({"error": "Authentication required for subscription"}), 401
            user = User.query.get(user_id)
            if not user:
                logger.warning(f"User not found for subscription: {user_id}")
                return jsonify({"error": "User not found"}), 404
            user.subscription_tier = UserTierEnum.PAID.value
            db.session.commit()

        # Prepare response
        response = {
            "message": "Subscription confirmed",
            "subscription_tier": subscription_tier,
            "report_url": report_url
        }

        # Issue JWT for authenticated users or temp users
        if user_id and isinstance(user_id, int):
            access_token = create_access_token(identity=f"user_{user_id}")
            response['access_token'] = access_token
        elif temp_user_id and not user_id:
            access_token = create_access_token(identity=temp_user_id, expires_delta=timedelta(hours=1))
            response['access_token'] = access_token

        logger.info(f"Subscription confirmed for plan: {plan}, user_id: {user_id or temp_user_id}")
        return jsonify(response), 200

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error in confirm_subscription: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Stripe processing error"}), 500
    except Exception as e:
        logger.error(f"Unexpected error in confirm_subscription: {str(e)}", exc_info=True)
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