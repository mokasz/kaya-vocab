# kaya-vocab/scripts/sm2.py

MASTERED_INTERVAL = 21  # この日数以上で習得済み

def sm2_update(ease: float, interval: int, repetitions: int, quality: int):
    """
    SM-2 アルゴリズム。
    quality: 4=正解ヒントなし, 2=正解ヒントあり, 0=不正解
    returns: (ease, interval, repetitions)
    """
    if quality < 2:  # 不正解 → リセット
        return ease, 1, 0

    ease = max(1.3, ease + 0.1 - (4 - quality) * 0.08)
    repetitions += 1
    if repetitions == 1:
        interval = 1
    elif repetitions == 2:
        interval = 6
    else:
        interval = round(interval * ease)
    return ease, interval, repetitions


def quality_from_review_log(ratings: list[int]) -> int:
    """
    当日の review_log の rating リストから SM-2 quality を決定する。
    rating: green=4, yellow=2, red=1
    - red が1件でもある → 0
    - yellow が1件でもある（red なし）→ 2
    - 全部 green → 4
    """
    if not ratings:
        return 0
    if 1 in ratings:
        return 0
    if 2 in ratings:
        return 2
    return 4


def is_mastered(interval: int) -> bool:
    """interval が閾値以上なら習得済み"""
    return interval >= MASTERED_INTERVAL
