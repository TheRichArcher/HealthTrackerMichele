from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from backend.extensions import db
from backend.models import User, UserTierEnum
import stripe
import logging
import os

# Logger setup
logger = logging.getLogger("subscription_routes")

# Create Flask Blueprint
subscription_bp = Blueprint("subscription_bp", __name__)

# Stripe configuration
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
BASE_URL = os.getenv('APP_URL', 'http://localhost:5000')  # Use environment variable for flexibility
PAID_PRICE_ID = "price_1R1uhXFYtRpVxUhsuwbBhzQJ"  # $9.99/month
ONE_TIME_PRICE_ID = "price_1R1uiSFYtRpVxUhskAuZxjKO"  # $4.99 one-time

@subscription_bp.route("/status", methods=["GET"])
@jwt_required()
def get_subscription_status():
    """Return the current subscription tier of the authenticated user."""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user:
            logger.error(f"User not found for ID: {user_id}")
            return jsonify({"error": "User not found"}), 404
        return jsonify({"subscription_tier": user.subscription_tier.value}), 200
    except Exception as e:
        logger.error(f"Error fetching subscription status for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": f"Failed to fetch subscription status: {str(e)}"}), 500

@subscription_bp.route("/upgrade", methods=["POST"])
@jwt_required()
def upgrade_subscription():
    """Create a Stripe Checkout session for subscription upgrade."""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user:
            logger.error(f"User not found for ID: {user_id}")
            return jsonify({"error": "User not found"}), 404

        data = request.get_json()
        if not data:
            logger.warning("No JSON data provided in upgrade request")
            return jsonify({"error": "Request must contain JSON data"}), 400

        plan = data.get("plan")
        if not plan or plan not in ["paid", "one_time"]:
            logger.warning(f"Invalid plan received: {plan}")
            return jsonify({"error": "Invalid plan. Must be 'paid' or 'one_time'"}), 400

        # Determine price ID and mode based on plan
        if plan == "paid":
            price_id = PAID_PRICE_ID
            mode = "subscription"
        else:  # one_time
            price_id = ONE_TIME_PRICE_ID
            mode = "payment"

        # Create Stripe Checkout session
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price": price_id,
                "quantity": 1,
            }],
            mode=mode,
            success_url=f"{BASE_URL}/subscription?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{BASE_URL}/subscription",
            metadata={"user_id": str(user_id), "plan": plan},
        )

        logger.info(f"Created Stripe Checkout session {session.id} for user {user_id}, plan: {plan}")
        return jsonify({"checkout_url": session.url}), 200

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error during checkout for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": f"Payment processing error: {str(e)}"}), 500
    except Exception as e:
        logger.error(f"Error creating checkout session for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": f"Failed to initiate upgrade: {str(e)}"}), 500

@subscription_bp.route("/confirm", methods=["POST"])
@jwt_required()
def confirm_subscription():
    """Confirm the Stripe Checkout session and update user's subscription tier."""
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user:
            logger.error(f"User not found for ID: {user_id}")
            return jsonify({"error": "User not found"}), 404

        data = request.get_json()
        if not data:
            logger.warning("No JSON data provided in confirm request")
            return jsonify({"error": "Request must contain JSON data"}), 400

        session_id = data.get("session_id")
        if not session_id:
            logger.warning("No session_id provided in confirm request")
            return jsonify({"error": "Session ID is required"}), 400

        # Retrieve the Stripe Checkout session
        session = stripe.checkout.Session.retrieve(session_id)
        
        # Verify the session belongs to this user and is completed
        if session.metadata.get("user_id") != str(user_id):
            logger.warning(f"Session {session_id} does not belong to user {user_id}")
            return jsonify({"error": "Invalid payment session"}), 403
        if session.status != "complete":
            logger.warning(f"Session {session_id} is not complete for user {user_id}")
            return jsonify({"error": "Payment session is not complete"}), 400
        if session.payment_status != "paid":
            logger.warning(f"Session {session_id} is unpaid for user {user_id}")
            return jsonify({"error": "Payment not completed"}), 403

        # Update subscription tier based on plan
        plan = session.metadata.get("plan")
        if plan == "paid":
            user.subscription_tier = UserTierEnum.PAID
        elif plan == "one_time":
            user.subscription_tier = UserTierEnum.ONE_TIME
        else:
            logger.error(f"Unknown plan in session metadata: {plan}")
            return jsonify({"error": "Invalid plan in payment session"}), 400

        db.session.commit()
        logger.info(f"Subscription updated for user {user_id} to {user.subscription_tier.value} via session {session_id}")
        return jsonify({"subscription_tier": user.subscription_tier.value}), 200

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error during confirmation for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": f"Payment confirmation error: {str(e)}"}), 500
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error confirming subscription for user {user_id}: {str(e)}", exc_info=True)
        return jsonify({"error": f"Failed to confirm subscription: {str(e)}"}), 500