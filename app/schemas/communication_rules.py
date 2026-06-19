from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

CommunicationEvent = Literal[
    "on_transition",
    "on_comment",
    "on_record_created",
    "on_state_entered",
]

RecipientType = Literal[
    "capability",
    "role",
    "record_field",
    "author",
    "thread_participants",
]


class CommunicationRecipient(BaseModel):
    type: RecipientType
    value: str | None = None


class CommunicationDelivery(BaseModel):
    recipients: CommunicationRecipient
    notification: dict[str, Any] = Field(default_factory=dict)
    deep_link: dict[str, Any] = Field(default_factory=dict)


class CommunicationRuleMatch(BaseModel):
    entity_type: str | None = None
    record_type: str | None = None
    action_id: str | None = None
    to_state: str | None = None
    from_state: str | None = None
    comment_entity_type: str | None = None


class CommunicationRule(BaseModel):
    id: str
    enabled: bool = True
    event: CommunicationEvent
    match: CommunicationRuleMatch = Field(default_factory=CommunicationRuleMatch)
    deliveries: list[CommunicationDelivery] = Field(default_factory=list)


class CommunicationRulesRead(BaseModel):
    project_id: UUID
    rules: list[CommunicationRule]


class CommunicationRulesUpdate(BaseModel):
    rules: list[CommunicationRule]


class CommunicationSimulateRequest(BaseModel):
    event: CommunicationEvent
    entity_type: str | None = None
    record_type: str | None = None
    entity_id: UUID | None = None
    action_id: str | None = None
    from_state: str | None = None
    to_state: str | None = None
    comment_entity_type: str | None = None
    sandbox: bool = True


class CommunicationSimulateDelivery(BaseModel):
    rule_id: str
    recipient_ids: list[UUID]
    notification_tipo: str
    deep_link: dict[str, Any] = Field(default_factory=dict)


class CommunicationSimulateRead(BaseModel):
    matched: list[CommunicationSimulateDelivery]
