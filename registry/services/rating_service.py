"""
Shared rating service utilities for servers and agents.

This module provides common rating functionality to avoid code duplication
between server_service.py and agent_service.py.
"""

import logging
from typing import List, Dict, Tuple, Any


logger = logging.getLogger(__name__)


# Rating configuration constants
MAX_RATINGS_PER_RESOURCE = 100
MIN_RATING_VALUE = 1
MAX_RATING_VALUE = 5


def validate_rating(rating: int) -> None:
    """
    Validate rating value with detailed logging.

    Args:
        rating: The rating value to validate

    Raises:
        ValueError: If rating is not an integer or not in valid range
    """
    if not isinstance(rating, int):
        logger.error(f"Invalid rating type: {rating} (type={type(rating)})")
        raise ValueError("Rating must be an integer")

    if rating < MIN_RATING_VALUE or rating > MAX_RATING_VALUE:
        logger.error(
            f"Invalid rating value: {rating}. Must be between {MIN_RATING_VALUE} and {MAX_RATING_VALUE}."
        )
        raise ValueError(
            f"Rating must be between {MIN_RATING_VALUE} and {MAX_RATING_VALUE} (inclusive)"
        )


def update_rating_details(
    rating_details: List[Dict[str, Any]],
    username: str,
    rating: int,
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Update rating details list with new or updated user rating.

    This function handles:
    - Updating existing user ratings
    - Adding new user ratings
    - Maintaining a rotating buffer of max ratings

    Args:
        rating_details: Current list of rating detail dicts
        username: Username submitting the rating
        rating: Rating value (already validated)

    Returns:
        Tuple of (updated_rating_details, is_new_rating)
        - updated_rating_details: Modified list
        - is_new_rating: True if this was a new rating, False if update
    """
    if rating_details is None:
        rating_details = []

    # Check if user has already rated
    user_found = False
    for entry in rating_details:
        if entry.get("user") == username:
            entry["rating"] = rating
            user_found = True
            logger.info(f"Updated existing rating for user {username} to {rating}")
            break

    # If no existing rating from this user, append a new one
    if not user_found:
        rating_details.append({
            "user": username,
            "rating": rating,
        })
        logger.info(f"Added new rating for user {username}: {rating}")

        # Maintain a rotating buffer of MAX_RATINGS_PER_RESOURCE entries
        if len(rating_details) > MAX_RATINGS_PER_RESOURCE:
            # Remove the oldest entry to maintain the limit
            rating_details.pop(0)
            logger.info(
                f"Removed oldest rating to maintain {MAX_RATINGS_PER_RESOURCE} entries limit"
            )

    return rating_details, not user_found


def calculate_average_rating(rating_details: List[Dict[str, Any]]) -> float:
    """
    Calculate average rating from rating details.

    Args:
        rating_details: List of rating detail dicts with 'rating' key

    Returns:
        Average rating as float

    Raises:
        ValueError: If rating_details is empty
    """
    if not rating_details:
        raise ValueError("Cannot calculate average from empty rating details")

    all_ratings = [entry["rating"] for entry in rating_details]
    average = float(sum(all_ratings) / len(all_ratings))

    logger.debug(
        f"Calculated average rating: {average:.2f} from {len(all_ratings)} ratings"
    )

    return average
