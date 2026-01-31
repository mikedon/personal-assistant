"""Integration tests for voice API endpoints."""

import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from src.api.routes import tasks_router, voice_router
from src.models.database import get_db, reset_engine
from src.services.llm_service import ExtractedTask
from src.services.voice_service import TranscriptionResult
from src.utils.config import Config, VoiceConfig, reset_config


@pytest.fixture(scope="function")
def voice_client(test_db_engine, monkeypatch):
    """Create a test client with voice routes."""
    from src import __version__

    # Reset global state
    reset_config()
    reset_engine()

    # Create a fresh connection for this test
    connection = test_db_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)

    # Create config with voice enabled
    test_config = Config(
        database={"url": "sqlite:///:memory:", "echo": False},
        llm={"api_key": "test-key", "model": "gpt-4"},
        voice={"enabled": True, "recording_duration_seconds": 10, "sample_rate": 16000},
    )

    # Create a test app
    app = FastAPI(
        title="Personal Assistant API (Test)",
        version=__version__,
    )
    app.include_router(tasks_router, prefix="/api")
    app.include_router(voice_router, prefix="/api")

    # Override get_db dependency to use the test session
    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    # Override get_config
    def override_get_config():
        return test_config

    monkeypatch.setattr("src.utils.config.get_config", override_get_config)
    monkeypatch.setattr("src.api.routes.voice.get_config", override_get_config)

    with TestClient(app) as test_client:
        yield test_client

    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def voice_disabled_client(test_db_engine, monkeypatch):
    """Create a test client with voice disabled."""
    from src import __version__

    # Reset global state
    reset_config()
    reset_engine()

    # Create a fresh connection for this test
    connection = test_db_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)

    # Create config with voice disabled
    test_config = Config(
        database={"url": "sqlite:///:memory:", "echo": False},
        llm={"api_key": "test-key", "model": "gpt-4"},
        voice={"enabled": False},
    )

    # Create a test app
    app = FastAPI(
        title="Personal Assistant API (Test)",
        version=__version__,
    )
    app.include_router(tasks_router, prefix="/api")
    app.include_router(voice_router, prefix="/api")

    # Override get_db dependency to use the test session
    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    # Override get_config
    def override_get_config():
        return test_config

    monkeypatch.setattr("src.utils.config.get_config", override_get_config)
    monkeypatch.setattr("src.api.routes.voice.get_config", override_get_config)

    with TestClient(app) as test_client:
        yield test_client

    transaction.rollback()
    connection.close()


class TestVoiceStatus:
    """Tests for voice status endpoint."""

    def test_voice_status_enabled(self, voice_client):
        """Test voice status when enabled."""
        with patch(
            "src.api.routes.voice.VoiceService.check_microphone_available",
            return_value=True,
        ):
            response = voice_client.get("/api/tasks/voice/status")
            assert response.status_code == 200

            data = response.json()
            assert data["enabled"] is True
            assert "whisper_model" in data
            assert "default_duration_seconds" in data

    def test_voice_status_disabled(self, voice_disabled_client):
        """Test voice status when disabled."""
        response = voice_disabled_client.get("/api/tasks/voice/status")
        assert response.status_code == 200

        data = response.json()
        assert data["enabled"] is False


class TestTranscribeAudio:
    """Tests for audio transcription endpoint."""

    def test_transcribe_audio_success(self, voice_client):
        """Test successful audio transcription."""
        # Create mock audio file
        audio_content = b"fake wav audio data"
        audio_file = io.BytesIO(audio_content)

        mock_transcription = TranscriptionResult(
            text="Buy groceries tomorrow",
            language="en",
            duration_seconds=3.5,
        )

        with patch(
            "src.api.routes.voice.VoiceService.transcribe_audio",
            return_value=mock_transcription,
        ):
            response = voice_client.post(
                "/api/tasks/voice/transcribe",
                files={"audio": ("test.wav", audio_file, "audio/wav")},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["text"] == "Buy groceries tomorrow"
            assert data["language"] == "en"
            assert data["duration_seconds"] == 3.5

    def test_transcribe_audio_with_language(self, voice_client):
        """Test transcription with language hint."""
        audio_content = b"fake wav audio data"
        audio_file = io.BytesIO(audio_content)

        mock_transcription = TranscriptionResult(
            text="Comprar comestibles",
            language="es",
            duration_seconds=2.0,
        )

        with patch(
            "src.api.routes.voice.VoiceService.transcribe_audio",
            return_value=mock_transcription,
        ):
            response = voice_client.post(
                "/api/tasks/voice/transcribe",
                files={"audio": ("test.wav", audio_file, "audio/wav")},
                params={"language": "es"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["language"] == "es"

    def test_transcribe_audio_empty_file(self, voice_client):
        """Test transcription with empty file."""
        audio_file = io.BytesIO(b"")

        response = voice_client.post(
            "/api/tasks/voice/transcribe",
            files={"audio": ("test.wav", audio_file, "audio/wav")},
        )

        assert response.status_code == 400
        assert "Empty audio file" in response.json()["detail"]

    def test_transcribe_audio_voice_disabled(self, voice_disabled_client):
        """Test transcription when voice is disabled."""
        audio_content = b"fake wav audio data"
        audio_file = io.BytesIO(audio_content)

        response = voice_disabled_client.post(
            "/api/tasks/voice/transcribe",
            files={"audio": ("test.wav", audio_file, "audio/wav")},
        )

        assert response.status_code == 400
        assert "disabled" in response.json()["detail"].lower()


class TestCreateTaskFromVoice:
    """Tests for voice task creation endpoint."""

    def test_create_task_from_voice_success(self, voice_client):
        """Test successful task creation from voice."""
        audio_content = b"fake wav audio data"
        audio_file = io.BytesIO(audio_content)

        mock_transcription = TranscriptionResult(
            text="Call John about the project",
            language="en",
            duration_seconds=3.0,
        )

        mock_extracted_task = ExtractedTask(
            title="Call John",
            description="About the project",
            priority="high",
            confidence=0.9,
        )

        with patch(
            "src.api.routes.voice.VoiceService.transcribe_audio",
            return_value=mock_transcription,
        ):
            with patch(
                "src.api.routes.voice.VoiceService.extract_task_from_transcription",
                new_callable=AsyncMock,
                return_value=[mock_extracted_task],
            ):
                response = voice_client.post(
                    "/api/tasks/voice",
                    files={"audio": ("test.wav", audio_file, "audio/wav")},
                )

                assert response.status_code == 201
                data = response.json()
                assert data["transcription"] == "Call John about the project"
                assert data["task"] is not None
                assert data["task"]["title"] == "Call John"
                assert data["task"]["source"] == "voice"
                assert data["extracted_tasks_count"] == 1

    def test_create_task_from_voice_fallback(self, voice_client):
        """Test task creation when no task is extracted (uses transcription)."""
        audio_content = b"fake wav audio data"
        audio_file = io.BytesIO(audio_content)

        mock_transcription = TranscriptionResult(
            text="Something vague that needs doing",
            language="en",
            duration_seconds=2.0,
        )

        with patch(
            "src.api.routes.voice.VoiceService.transcribe_audio",
            return_value=mock_transcription,
        ):
            with patch(
                "src.api.routes.voice.VoiceService.extract_task_from_transcription",
                new_callable=AsyncMock,
                return_value=[],  # No tasks extracted
            ):
                response = voice_client.post(
                    "/api/tasks/voice",
                    files={"audio": ("test.wav", audio_file, "audio/wav")},
                )

                assert response.status_code == 201
                data = response.json()
                assert data["transcription"] == "Something vague that needs doing"
                assert data["task"] is not None
                # Fallback uses transcription as title
                assert data["task"]["title"] == "Something vague that needs doing"
                assert data["task"]["source"] == "voice"

    def test_create_task_from_voice_empty_transcription(self, voice_client):
        """Test task creation with empty transcription."""
        audio_content = b"fake wav audio data"
        audio_file = io.BytesIO(audio_content)

        mock_transcription = TranscriptionResult(
            text="",
            language="en",
            duration_seconds=1.0,
        )

        with patch(
            "src.api.routes.voice.VoiceService.transcribe_audio",
            return_value=mock_transcription,
        ):
            response = voice_client.post(
                "/api/tasks/voice",
                files={"audio": ("test.wav", audio_file, "audio/wav")},
            )

            assert response.status_code == 201
            data = response.json()
            assert data["transcription"] == ""
            assert data["task"] is None

    def test_create_task_from_voice_empty_file(self, voice_client):
        """Test task creation with empty file."""
        audio_file = io.BytesIO(b"")

        response = voice_client.post(
            "/api/tasks/voice",
            files={"audio": ("test.wav", audio_file, "audio/wav")},
        )

        assert response.status_code == 400
        assert "Empty audio file" in response.json()["detail"]

    def test_create_task_from_voice_disabled(self, voice_disabled_client):
        """Test task creation when voice is disabled."""
        audio_content = b"fake wav audio data"
        audio_file = io.BytesIO(audio_content)

        response = voice_disabled_client.post(
            "/api/tasks/voice",
            files={"audio": ("test.wav", audio_file, "audio/wav")},
        )

        assert response.status_code == 400
        assert "disabled" in response.json()["detail"].lower()

    def test_create_task_with_language_hint(self, voice_client):
        """Test task creation with language hint."""
        audio_content = b"fake wav audio data"
        audio_file = io.BytesIO(audio_content)

        mock_transcription = TranscriptionResult(
            text="Llamar a Juan mañana",
            language="es",
            duration_seconds=2.5,
        )

        mock_extracted_task = ExtractedTask(
            title="Llamar a Juan",
            priority="medium",
            confidence=0.85,
        )

        with patch(
            "src.api.routes.voice.VoiceService.transcribe_audio",
            return_value=mock_transcription,
        ) as mock_transcribe:
            with patch(
                "src.api.routes.voice.VoiceService.extract_task_from_transcription",
                new_callable=AsyncMock,
                return_value=[mock_extracted_task],
            ):
                response = voice_client.post(
                    "/api/tasks/voice",
                    files={"audio": ("test.wav", audio_file, "audio/wav")},
                    params={"language": "es"},
                )

                assert response.status_code == 201
                # Verify language was passed to transcribe
                call_args = mock_transcribe.call_args
                assert call_args[1].get("language") == "es" or (
                    len(call_args[0]) > 1 and call_args[0][1] == "es"
                )
