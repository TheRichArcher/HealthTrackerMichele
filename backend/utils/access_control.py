from backend.models import UserTierEnum

def can_access_assessment_details(user):
    """
    Check if a user has access to detailed assessments and report storage.
    Returns True for PAID or ONE_TIME subscription tiers.
    """
    return hasattr(user, "subscription_tier") and user.subscription_tier in [
        UserTierEnum.PAID.value,
        UserTierEnum.ONE_TIME.value
    ]