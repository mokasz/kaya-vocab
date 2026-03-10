import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from sm2 import sm2_update, quality_from_status, is_mastered


def test_incorrect_resets_interval_and_reps():
    ease, interval, reps = sm2_update(2.5, 6, 2, quality=0)
    assert interval == 1
    assert reps == 0


def test_incorrect_does_not_change_ease():
    ease, _, _ = sm2_update(2.5, 6, 2, quality=0)
    assert ease == 2.5


def test_correct_no_hint_first_rep():
    _, interval, reps = sm2_update(2.5, 0, 0, quality=4)
    assert interval == 1
    assert reps == 1


def test_correct_no_hint_second_rep():
    _, interval, reps = sm2_update(2.5, 1, 1, quality=4)
    assert interval == 6
    assert reps == 2


def test_correct_no_hint_third_rep():
    _, interval, reps = sm2_update(2.5, 6, 2, quality=4)
    # ease は先に更新される: 2.5 + 0.1 = 2.6 → interval = round(6 * 2.6) = 16
    assert interval == round(6 * 2.6)  # 16
    assert reps == 3


def test_ease_increases_with_quality4():
    ease, _, _ = sm2_update(2.5, 1, 1, quality=4)
    assert ease > 2.5


def test_ease_decreases_with_quality2():
    ease1, _, _ = sm2_update(2.5, 1, 1, quality=4)
    ease2, _, _ = sm2_update(2.5, 1, 1, quality=2)
    assert ease2 < ease1


def test_ease_minimum_is_1_3():
    ease, _, _ = sm2_update(1.3, 1, 1, quality=2)
    assert ease >= 1.3


def test_quality_from_status_green():
    assert quality_from_status('green') == 4


def test_quality_from_status_yellow():
    assert quality_from_status('yellow') == 2


def test_quality_from_status_red():
    assert quality_from_status('red') == 0


def test_quality_from_status_unknown():
    assert quality_from_status('unknown') == 0


def test_is_mastered_true():
    assert is_mastered(21) is True
    assert is_mastered(30) is True


def test_is_mastered_false():
    assert is_mastered(20) is False
    assert is_mastered(0) is False
