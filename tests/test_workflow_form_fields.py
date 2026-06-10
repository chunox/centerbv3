"""Validación de form_fields en transiciones de workflow."""

import pytest
from fastapi import HTTPException

from app.services.workflow.engine import validate_transition_form_fields


def test_validate_form_fields_rejects_missing_required():
    transition = {
        "form_fields": [
            {"id": "motivo", "label": "Motivo", "type": "textarea", "required": True},
        ],
    }
    with pytest.raises(HTTPException) as exc:
        validate_transition_form_fields(transition, {})
    assert exc.value.status_code == 422
    assert "Motivo" in str(exc.value.detail)


def test_validate_form_fields_accepts_provided_required():
    transition = {
        "form_fields": [
            {"id": "motivo", "label": "Motivo", "type": "textarea", "required": True},
        ],
    }
    validate_transition_form_fields(transition, {"motivo": "Detalle del cambio"})


def test_validate_form_fields_ignores_empty_spec():
    validate_transition_form_fields({"form_fields": []}, None)
