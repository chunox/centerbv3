from app.services.records.adapters.feature import FeatureAdapter
from app.services.records.adapters.milestone import MilestoneAdapter
from app.services.records.adapters.query import QueryAdapter
from app.services.records.adapters.report import ReportAdapter
from app.services.records.adapters.task import TaskAdapter

LEGACY_ADAPTERS = {
    "task": TaskAdapter(),
    "feature": FeatureAdapter(),
    "milestone": MilestoneAdapter(),
    "query": QueryAdapter(),
    "report": ReportAdapter(),
}

__all__ = ["LEGACY_ADAPTERS", "TaskAdapter", "FeatureAdapter", "MilestoneAdapter", "QueryAdapter", "ReportAdapter"]
