from __future__ import annotations

from dataclasses import dataclass, field

from app.lola.classifier import classify


@dataclass(frozen=True)
class LolaAction:
    intent: str
    risk_tier: str
    confidence: float
    args: dict[str, str] = field(default_factory=dict)



def route_message(text: str) -> LolaAction:
    normalized = text.strip()
    intent, risk_tier, confidence = classify(normalized)
    return LolaAction(intent=intent.value, risk_tier=risk_tier.value, confidence=confidence)
