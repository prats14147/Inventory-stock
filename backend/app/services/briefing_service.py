"""backend/app/services/briefing_service.py

Proactive morning briefing (Upgrade #4): the system tells you what matters
without being asked.

Assembled from the same services the pages use (alerts, stockout, reorder),
so it cannot drift from them. Deterministic templates phrase it -- no LLM is
needed or involved, which keeps it testable and free to call on every
dashboard load.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories import product_repository, realtime_repository
from app.services import reorder_service, stockout_service
from app.services.errors import NotFoundError

BRIEFING_RISK_LIMIT = 3


def build_morning_briefing(db: Session) -> dict:
    """Top risks, open critical alerts, and suggested draft orders."""
    open_alerts = realtime_repository.get_alerts(db, acknowledged=False, limit=50)
    critical = [alert for alert in open_alerts if alert.severity == "CRITICAL"]

    risks = []
    for product_id in product_repository.list_product_ids(db):
        try:
            risks.append(stockout_service.calculate_stockout_risk(db, product_id))
        except NotFoundError:
            continue
    risks.sort(key=lambda r: (r.risk.value != "HIGH", r.current_inventory - r.required_inventory))
    top_risks = risks[:BRIEFING_RISK_LIMIT]

    suggestions = []
    for risk in top_risks:
        if risk.risk.value == "LOW":
            continue
        try:
            reorder = reorder_service.calculate_reorder(db, risk.product_id, risk.lead_time_days)
            quantity = max(1, int(round(reorder.recommended_reorder_quantity)))
        except (NotFoundError, ValueError):
            continue
        suggestions.append({
            "product_id": risk.product_id,
            "name": risk.name,
            "risk": risk.risk.value,
            "suggested_quantity": quantity,
        })

    if not top_risks and not critical:
        headline = "All clear. Every product covers its forecast demand plus the safety-stock buffer."
    else:
        parts = []
        if critical:
            parts.append(f"{len(critical)} critical live alert{'s' if len(critical) != 1 else ''} open")
        at_risk = [r for r in top_risks if r.risk.value != "LOW"]
        if at_risk:
            parts.append(f"{at_risk[0].product_id} ({at_risk[0].name}) needs attention first")
        headline = "Morning briefing: " + "; ".join(parts) + "."

    return {
        "headline": headline,
        "open_alerts": len(open_alerts),
        "critical_alerts": len(critical),
        "top_risks": [
            {
                "product_id": risk.product_id,
                "name": risk.name,
                "risk": risk.risk.value,
                "current_inventory": risk.current_inventory,
                "required_inventory": risk.required_inventory,
            }
            for risk in top_risks
        ],
        "suggested_orders": suggestions,
    }
