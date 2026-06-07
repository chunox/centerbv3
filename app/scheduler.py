"""Jobs programados en proceso (§4.4 — sync diario de hitos)."""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.database import SessionLocal
from app.services.milestones import sync_all_milestone_states

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def run_scheduled_milestone_sync() -> int:
    """Ejecuta sync de estados `*_con_bug` en todos los proyectos activos."""
    actor_id = settings.milestone_sync_actor_user_id
    if actor_id is None:
        logger.warning(
            "milestone_sync omitido: milestone_sync_actor_user_id no configurado"
        )
        return 0

    db = SessionLocal()
    try:
        updated = sync_all_milestone_states(db, actor_user_id=actor_id)
        db.commit()
        logger.info("milestone_sync completado: %s hitos actualizados", updated)
        return updated
    except Exception:
        db.rollback()
        logger.exception("milestone_sync falló")
        raise
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler | None:
    global _scheduler

    if not settings.milestone_sync_enabled:
        return None
    if settings.milestone_sync_actor_user_id is None:
        logger.warning(
            "Scheduler deshabilitado: milestone_sync_enabled=true pero "
            "falta milestone_sync_actor_user_id"
        )
        return None

    if _scheduler is not None and _scheduler.running:
        return _scheduler

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_scheduled_milestone_sync,
        CronTrigger(
            hour=settings.milestone_sync_hour,
            minute=settings.milestone_sync_minute,
        ),
        id="milestone_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "Scheduler iniciado: milestone_sync diario a las %02d:%02d",
        settings.milestone_sync_hour,
        settings.milestone_sync_minute,
    )
    return scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
