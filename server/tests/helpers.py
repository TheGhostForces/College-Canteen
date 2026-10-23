from datetime import timedelta

from app.core.timeutils import today_local


def plan_params(world, days_ahead: int = 1) -> dict:
    return {"institution_id": world.inst1, "target_date": (today_local() + timedelta(days=days_ahead)).isoformat()}
