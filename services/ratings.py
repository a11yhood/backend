"""Shared rating math utilities."""


def compute_display_rating(
    user_average: float | None,
    source_rating: float | None,
    user_rating_count: int = 0,
) -> float | None:
    """Blend internal and external ratings into one display rating.

    Internal ratings are weighted by the number of A11yhood ratings.
    External source rating contributes one blended vote.
    """
    if user_average is not None and source_rating is not None:
        weight = max(int(user_rating_count or 0), 1)
        return ((user_average * weight) + source_rating) / (weight + 1)
    if user_average is not None:
        return user_average
    if source_rating is not None:
        return source_rating
    return None
