from datetime import date, timedelta

from nachhilfe.fsrs import Again, Card, Easy, Good, Hard, mastery_bucket, review


def test_new_card_first_review_moves_to_review_state():
    card = Card()
    today = date(2026, 1, 1)
    review(card, Good, today)

    assert card.state == "review"
    assert card.reps == 1
    assert card.lapses == 0
    assert card.stability is not None and card.stability > 0
    assert card.difficulty is not None
    assert card.due is not None and card.due > today


def test_first_rating_orders_initial_stability_again_lt_easy():
    stabilities = {}
    for rating in (Again, Hard, Good, Easy):
        card = Card()
        review(card, rating, date(2026, 1, 1))
        stabilities[rating] = card.stability

    assert stabilities[Again] < stabilities[Hard] < stabilities[Good] < stabilities[Easy]


def test_easy_first_review_schedules_further_out_than_again():
    today = date(2026, 1, 1)
    again_card = Card()
    review(again_card, Again, today)
    easy_card = Card()
    review(easy_card, Easy, today)

    assert easy_card.due > again_card.due


def test_lapse_only_counted_on_an_existing_card_not_a_brand_new_one():
    today = date(2026, 1, 1)
    card = Card()
    review(card, Good, today)
    assert card.lapses == 0

    review(card, Again, card.due)
    assert card.lapses == 1
    assert card.state == "review"


def test_consecutive_good_reviews_grow_stability():
    today = date(2026, 1, 1)
    card = Card()
    review(card, Good, today)
    first_stability = card.stability

    review(card, Good, card.due)
    assert card.stability > first_stability


def test_reviewing_same_day_as_last_review_does_not_grow_stability():
    today = date(2026, 1, 1)
    card = Card()
    review(card, Good, today)
    stability_after_first = card.stability

    review(card, Good, today)  # zero elapsed days
    assert card.stability == stability_after_first


def test_difficulty_stays_within_bounds_under_repeated_lapses():
    today = date(2026, 1, 1)
    card = Card()
    review(card, Again, today)
    for _ in range(20):
        today += timedelta(days=1)
        review(card, Again, today)

    assert 1.0 <= card.difficulty <= 10.0


def test_mastery_bucket_thresholds():
    card = Card(state="review", stability=25)
    assert mastery_bucket(card, very_good_days=21, good_days=7) == "very_good"

    card.stability = 10
    assert mastery_bucket(card, 21, 7) == "good"

    card.stability = 3
    assert mastery_bucket(card, 21, 7) == "in_learning"


def test_mastery_bucket_new_card_is_in_learning():
    assert mastery_bucket(Card(), 21, 7) == "in_learning"
