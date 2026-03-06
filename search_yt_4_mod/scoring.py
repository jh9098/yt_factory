from __future__ import annotations


def classify_vs_ratio(vs_ratio):
    if not isinstance(vs_ratio, (int, float)):
        return "판독불가"
    if vs_ratio >= 2.0:
        return "초대박"
    if vs_ratio >= 1.0:
        return "대박"
    return "일반"


def compute_video_scores(view_count, subscriber_count, like_count, comment_count):
    vs_ratio = None
    like_rate = None
    comment_rate = None

    if isinstance(view_count, int) and isinstance(subscriber_count, int) and subscriber_count > 0:
        vs_ratio = view_count / subscriber_count

    if isinstance(view_count, int) and view_count > 0:
        if isinstance(like_count, int):
            like_rate = like_count / view_count
        if isinstance(comment_count, int):
            comment_rate = comment_count / view_count

    return {
        "vs_ratio": vs_ratio,
        "hit_grade": classify_vs_ratio(vs_ratio),
        "like_rate": like_rate,
        "comment_rate": comment_rate,
    }


def format_ratio(v):
    if not isinstance(v, (int, float)):
        return "-"
    return f"{v:.2f}"


def format_percent(v):
    if not isinstance(v, (int, float)):
        return "-"
    return f"{v*100:.2f}%"
