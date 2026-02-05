"""Unit tests for Initiative model."""

import pytest

from src.models.initiative import Initiative, InitiativePriority, InitiativeStatus


def test_initiative_status_enum():
    """Test InitiativeStatus enum values."""
    assert InitiativeStatus.ACTIVE.value == "active"
    assert InitiativeStatus.COMPLETED.value == "completed"
    assert InitiativeStatus.PAUSED.value == "paused"


def test_initiative_priority_enum():
    """Test InitiativePriority enum values."""
    assert InitiativePriority.HIGH.value == "high"
    assert InitiativePriority.MEDIUM.value == "medium"
    assert InitiativePriority.LOW.value == "low"


def test_initiative_creation(test_db_session):
    """Test creating an initiative."""
    initiative = Initiative(
        title="Test Initiative",
        description="Test description",
        priority=InitiativePriority.HIGH,
    )
    test_db_session.add(initiative)
    test_db_session.commit()

    assert initiative.id is not None
    assert initiative.title == "Test Initiative"
    assert initiative.description == "Test description"
    assert initiative.priority == InitiativePriority.HIGH
    assert initiative.status == InitiativeStatus.ACTIVE  # default
    assert initiative.target_date is None
    assert initiative.created_at is not None
    assert initiative.updated_at is not None


def test_initiative_default_values(test_db_session):
    """Test initiative default values."""
    initiative = Initiative(title="Minimal Initiative")
    test_db_session.add(initiative)
    test_db_session.commit()

    assert initiative.status == InitiativeStatus.ACTIVE
    assert initiative.priority == InitiativePriority.MEDIUM
    assert initiative.description is None
    assert initiative.target_date is None


def test_initiative_repr(test_db_session):
    """Test initiative string representation."""
    initiative = Initiative(
        title="A very long initiative title that exceeds thirty characters",
        status=InitiativeStatus.ACTIVE,
    )
    test_db_session.add(initiative)
    test_db_session.commit()

    repr_str = repr(initiative)
    assert "Initiative" in repr_str
    assert str(initiative.id) in repr_str
    assert "active" in repr_str
