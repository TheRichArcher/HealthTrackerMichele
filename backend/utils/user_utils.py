def is_temp_user(user):
    """
    Check if a user is temporary based on their ID.
    Returns True if user is None or their ID starts with 'temp_'.
    """
    return user is None or (hasattr(user, 'id') and str(user.id).startswith("temp_"))