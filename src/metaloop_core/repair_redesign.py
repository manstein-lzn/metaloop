from __future__ import annotations


def classify_dissatisfaction(feedback: str) -> str:
    """Conservative first-pass repair/redesign classifier.

    This helper is intentionally simple. It should not replace user/reviewer
    judgment; it gives wrappers a stable vocabulary for routing feedback.
    """

    text = feedback.lower()
    if any(term in text for term in ["scope", "验收", "acceptance", "wrong goal", "目标不对", "重设计", "redesign"]):
        return "redesign"
    if any(term in text for term in ["继续", "resume", "incomplete", "没做完"]):
        return "resume"
    if any(term in text for term in ["完成", "complete", "满意", "ok"]):
        return "complete"
    return "repair"
