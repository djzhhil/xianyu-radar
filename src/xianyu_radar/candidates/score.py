"""Simple score helpers (MVP uses seller_count in detector)."""


def score_candidate(seller_count: int, appearance_count: int) -> float:
    return float(seller_count) + float(appearance_count) * 0.1
