from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import FeatureStateTransition, TaskStateTransition
from app.schemas.transitions import (
    FeatureStateTransitionRead,
    FeatureTransitionTipoProyecto,
    TaskStateTransitionRead,
)

router = APIRouter(prefix="/transitions", tags=["transitions"])


@router.get("/features", response_model=list[FeatureStateTransitionRead])
def list_feature_transitions(
    tipo_proyecto: FeatureTransitionTipoProyecto | None = Query(default=None),
    db: Session = Depends(get_db),
):
    stmt = select(FeatureStateTransition).order_by(
        FeatureStateTransition.estado_desde,
        FeatureStateTransition.estado_hasta,
    )
    if tipo_proyecto is not None:
        stmt = stmt.where(
            or_(
                FeatureStateTransition.tipo_proyecto == tipo_proyecto,
                FeatureStateTransition.tipo_proyecto == "ambos",
            )
        )
    return list(db.scalars(stmt))


@router.get("/tasks", response_model=list[TaskStateTransitionRead])
def list_task_transitions(db: Session = Depends(get_db)):
    stmt = select(TaskStateTransition).order_by(
        TaskStateTransition.estado_desde,
        TaskStateTransition.estado_hasta,
    )
    return list(db.scalars(stmt))
