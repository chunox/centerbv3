"""Estados canónicos Scrum — kanban 7 columnas."""

SCRUM_PIPELINE_STATES = ("backlog", "to_do", "in_progress", "in_review", "done")

SCRUM_KANBAN_STATES = SCRUM_PIPELINE_STATES + ("blocked", "cancelled")

SCRUM_TERMINAL_STATES = frozenset({"done", "cancelled"})

SCRUM_LATERAL_STATES = frozenset({"blocked"})

# Pipeline activo que exige parent sprint (historia) o sprint_id (épica)
SCRUM_PIPELINE_SPRINT_REQUIRED_STATUSES = frozenset(
    {"to_do", "in_progress", "in_review", "done"}
)

# Comprometidas en sprint (incluye bloqueadas)
SCRUM_SPRINT_CAPACITY_STATUSES = SCRUM_PIPELINE_SPRINT_REQUIRED_STATUSES | frozenset({"blocked"})

# Alias histórico usado en membership
SCRUM_ACTIVE_SPRINT_STATUSES = SCRUM_SPRINT_CAPACITY_STATUSES

EXTRA_STATUS_BEFORE_BLOCK = "status_before_block"
EXTRA_BLOCKED_BY_INHERITANCE = "blocked_by_inheritance"
