"""Tests for Voice service."""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from src.services.voice_service import (
    MicrophoneNotFoundError,
    TranscriptionError,
    TranscriptionResult,
    VoiceError,
    VoiceService,
    VoiceTaskResult,
)
from src.utils.config import LLMConfig, VoiceConfig


@pytest.fixture
def voice_config():
    """Create a test voice config."""
    return VoiceConfig(
        enabled=True,
        recording_duration_seconds=5,
        sample_rate=16000,
        whisper_model="whisper-1",
    )


@pytest.fixture
def voice_config_disabled():
    """Create a disabled voice config."""
    return VoiceConfig(
        enabled=False,
        recording_duration_seconds=5,
        sample_rate=16000,
        whisper_model="whisper-1",
    )


@pytest.fixture
def llm_config():
    """Create a test LLM config."""
    return LLMConfig(
        base_url="https://api.openai.com/v1",
        api_key="test-api-key",
        model="gpt-4",
        temperature=0.7,
        max_tokens=2000,
    )


@pytest.fixture
def voice_service(voice_config, llm_config):
    """Create a voice service with test config."""
    return VoiceService(voice_config, llm_config)


@pytest.fixture
def voice_service_disabled(voice_config_disabled, llm_config):
    """Create a voice service with disabled config."""
    return VoiceService(voice_config_disabled, llm_config)


class TestVoiceServiceInit:
    """Tests for VoiceService initialization."""

    def test_init_with_config(self, voice_config, llm_config):
        """Test initialization with config."""
        service = VoiceService(voice_config, llm_config)
        assert service.voice_config == voice_config
        assert service.llm_config == llm_config
        assert service.llm_service is not None

    def test_init_with_custom_llm_service(self, voice_config, llm_config):
        """Test initialization with custom LLM service."""
        mock_llm_service = MagicMock()
        service = VoiceService(voice_config, llm_config, llm_service=mock_llm_service)
        assert service.llm_service == mock_llm_service


class TestCheckMicrophoneAvailable:
    """Tests for check_microphone_available."""

    def test_microphone_available(self, voice_service):
        """Test when microphone is available."""
        mock_devices = [
            {"name": "Built-in Microphone", "max_input_channels": 2},
            {"name": "Speakers", "max_input_channels": 0},
        ]
        with patch("src.services.voice_service.sd.query_devices", return_value=mock_devices):
            assert voice_service.check_microphone_available() is True

    def test_no_microphone_available(self, voice_service):
        """Test when no microphone is available."""
        mock_devices = [
            {"name": "Speakers", "max_input_channels": 0},
        ]
        with patch("src.services.voice_service.sd.query_devices", return_value=mock_devices):
            assert voice_service.check_microphone_available() is False

    def test_empty_device_list(self, voice_service):
        """Test when device list is empty."""
        with patch("src.services.voice_service.sd.query_devices", return_value=[]):
            assert voice_service.check_microphone_available() is False

    def test_query_devices_error(self, voice_service):
        """Test when query_devices raises an error."""
        with patch("src.services.voice_service.sd.query_devices", side_effect=Exception("Device error")):
            assert voice_service.check_microphone_available() is False


class TestRecordAudio:
    """Tests for record_audio."""

    def test_record_audio_success(self, voice_service):
        """Test successful audio recording."""
        # Mock device check
        mock_devices = [{"name": "Mic", "max_input_channels": 2}]
        
        # Create mock audio data
        mock_audio_data = np.zeros((16000 * 5, 1), dtype=np.float32)
        
        with patch("src.services.voice_service.sd.query_devices", return_value=mock_devices):
            with patch("src.services.voice_service.sd.rec", return_value=mock_audio_data) as mock_rec:
                with patch("src.services.voice_service.sd.wait"):
                    audio_bytes = voice_service.record_audio(duration_seconds=5)
                    
                    assert isinstance(audio_bytes, bytes)
                    assert len(audio_bytes) > 0
                    mock_rec.assert_called_once()

    def test_record_audio_no_microphone(self, voice_service):
        """Test recording when no microphone is available."""
        with patch("src.services.voice_service.sd.query_devices", return_value=[]):
            with pytest.raises(MicrophoneNotFoundError):
                voice_service.record_audio()

    def test_record_audio_uses_config_defaults(self, voice_service):
        """Test that recording uses config defaults."""
        mock_devices = [{"name": "Mic", "max_input_channels": 2}]
        mock_audio_data = np.zeros((16000 * 5, 1), dtype=np.float32)
        
        with patch("src.services.voice_service.sd.query_devices", return_value=mock_devices):
            with patch("src.services.voice_service.sd.rec", return_value=mock_audio_data) as mock_rec:
                with patch("src.services.voice_service.sd.wait"):
                    voice_service.record_audio()
                    
                    # Check that config defaults were used
                    call_kwargs = mock_rec.call_args
                    assert call_kwargs[1]["samplerate"] == 16000

    def test_record_audio_custom_duration(self, voice_service):
        """Test recording with custom duration."""
        mock_devices = [{"name": "Mic", "max_input_channels": 2}]
        mock_audio_data = np.zeros((16000 * 10, 1), dtype=np.float32)
        
        with patch("src.services.voice_service.sd.query_devices", return_value=mock_devices):
            with patch("src.services.voice_service.sd.rec", return_value=mock_audio_data) as mock_rec:
                with patch("src.services.voice_service.sd.wait"):
                    voice_service.record_audio(duration_seconds=10)
                    
                    # Check that custom duration was used (10 seconds * 16000 sample rate)
                    assert mock_rec.call_args[0][0] == 160000

    def test_record_audio_error(self, voice_service):
        """Test recording when an error occurs."""
        mock_devices = [{"name": "Mic", "max_input_channels": 2}]
        
        with patch("src.services.voice_service.sd.query_devices", return_value=mock_devices):
            with patch("src.services.voice_service.sd.rec", side_effect=Exception("Recording error")):
                with pytest.raises(VoiceError) as exc_info:
                    voice_service.record_audio()
                assert "Failed to record audio" in str(exc_info.value)


class TestTranscribeAudio:
    """Tests for transcribe_audio."""

    def test_transcribe_audio_success(self, voice_service):
        """Test successful transcription."""
        mock_response = MagicMock()
        mock_response.text = "Buy groceries tomorrow"
        mock_response.language = "en"
        mock_response.duration = 3.5
        
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_response
        
        with patch.object(voice_service, "_get_openai_client", return_value=mock_client):
            result = voice_service.transcribe_audio(b"fake audio data")
            
            assert result.text == "Buy groceries tomorrow"
            assert result.language == "en"
            assert result.duration_seconds == 3.5

    def test_transcribe_audio_disabled(self, voice_service_disabled):
        """Test transcription when voice is disabled."""
        with pytest.raises(VoiceError) as exc_info:
            voice_service_disabled.transcribe_audio(b"fake audio data")
        assert "disabled" in str(exc_info.value).lower()

    def test_transcribe_audio_with_language_hint(self, voice_service):
        """Test transcription with language hint."""
        mock_response = MagicMock()
        mock_response.text = "Comprar comestibles mañana"
        mock_response.language = "es"
        mock_response.duration = 4.0
        
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_response
        
        with patch.object(voice_service, "_get_openai_client", return_value=mock_client):
            result = voice_service.transcribe_audio(b"fake audio data", language="es")
            
            assert result.text == "Comprar comestibles mañana"
            # Verify language was passed to API
            call_kwargs = mock_client.audio.transcriptions.create.call_args[1]
            assert call_kwargs["language"] == "es"

    def test_transcribe_audio_error(self, voice_service):
        """Test transcription when API returns error."""
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.side_effect = Exception("API error")
        
        with patch.object(voice_service, "_get_openai_client", return_value=mock_client):
            with pytest.raises(TranscriptionError) as exc_info:
                voice_service.transcribe_audio(b"fake audio data")
            assert "Failed to transcribe" in str(exc_info.value)

    def test_transcribe_audio_strips_whitespace(self, voice_service):
        """Test that transcription strips whitespace."""
        mock_response = MagicMock()
        mock_response.text = "  Buy groceries tomorrow  \n"
        mock_response.language = "en"
        mock_response.duration = 3.5
        
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_response
        
        with patch.object(voice_service, "_get_openai_client", return_value=mock_client):
            result = voice_service.transcribe_audio(b"fake audio data")
            
            assert result.text == "Buy groceries tomorrow"


class TestTranscribeAudioFile:
    """Tests for transcribe_audio_file."""

    def test_transcribe_audio_file(self, voice_service):
        """Test transcribing from file-like object."""
        mock_response = MagicMock()
        mock_response.text = "Test transcription"
        mock_response.language = "en"
        mock_response.duration = 2.0
        
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_response
        
        # Create a mock file-like object
        audio_file = io.BytesIO(b"fake audio data")
        
        with patch.object(voice_service, "_get_openai_client", return_value=mock_client):
            result = voice_service.transcribe_audio_file(audio_file)
            
            assert result.text == "Test transcription"


class TestExtractTaskFromTranscription:
    """Tests for extract_task_from_transcription."""

    @pytest.mark.asyncio
    async def test_extract_task_success(self, voice_service):
        """Test successful task extraction."""
        from src.services.llm_service import ExtractedTask
        
        mock_tasks = [
            ExtractedTask(
                title="Buy groceries",
                description="Get milk and eggs",
                priority="medium",
                confidence=0.9,
            )
        ]
        
        with patch.object(
            voice_service.llm_service, 
            "extract_tasks_from_text", 
            new_callable=AsyncMock,
            return_value=mock_tasks
        ):
            tasks = await voice_service.extract_task_from_transcription("Buy groceries")
            
            assert len(tasks) == 1
            assert tasks[0].title == "Buy groceries"

    @pytest.mark.asyncio
    async def test_extract_task_uses_voice_source(self, voice_service):
        """Test that extraction uses 'voice' as source."""
        with patch.object(
            voice_service.llm_service, 
            "extract_tasks_from_text", 
            new_callable=AsyncMock,
            return_value=[]
        ) as mock_extract:
            await voice_service.extract_task_from_transcription("Test text")
            
            # Verify source was set to "voice"
            mock_extract.assert_called_once()
            call_kwargs = mock_extract.call_args[1]
            assert call_kwargs["source"] == "voice"


class TestCreateTaskFromAudio:
    """Tests for create_task_from_audio."""

    @pytest.mark.asyncio
    async def test_create_task_from_audio_with_extraction(self, voice_service):
        """Test creating task from audio with LLM extraction."""
        from src.services.llm_service import ExtractedTask
        from src.models.task import Task, TaskPriority, TaskSource
        
        mock_transcription = MagicMock()
        mock_transcription.text = "Remind me to call John tomorrow"
        mock_transcription.language = "en"
        mock_transcription.duration = 3.0
        
        mock_extracted_task = ExtractedTask(
            title="Call John",
            description="Follow up call",
            priority="high",
            confidence=0.9,
        )
        
        mock_created_task = MagicMock(spec=Task)
        mock_created_task.id = 1
        mock_created_task.title = "Call John"
        mock_created_task.priority = TaskPriority.HIGH
        mock_created_task.source = TaskSource.VOICE
        
        mock_task_service = MagicMock()
        mock_task_service.create_task.return_value = mock_created_task
        
        with patch.object(voice_service, "transcribe_audio", return_value=mock_transcription):
            with patch.object(
                voice_service,
                "extract_task_from_transcription",
                new_callable=AsyncMock,
                return_value=[mock_extracted_task]
            ):
                result = await voice_service.create_task_from_audio(
                    audio_data=b"fake audio",
                    task_service=mock_task_service,
                )
                
                assert result.transcription == "Remind me to call John tomorrow"
                assert result.created_task == mock_created_task
                assert len(result.extracted_tasks) == 1

    @pytest.mark.asyncio
    async def test_create_task_from_audio_fallback(self, voice_service):
        """Test creating task when no task is extracted."""
        from src.models.task import Task, TaskPriority, TaskSource
        
        mock_transcription = MagicMock()
        mock_transcription.text = "Something vague"
        mock_transcription.language = "en"
        mock_transcription.duration = 2.0
        
        mock_created_task = MagicMock(spec=Task)
        mock_created_task.id = 1
        mock_created_task.title = "Something vague"
        mock_created_task.priority = TaskPriority.MEDIUM
        mock_created_task.source = TaskSource.VOICE
        
        mock_task_service = MagicMock()
        mock_task_service.create_task.return_value = mock_created_task
        
        with patch.object(voice_service, "transcribe_audio", return_value=mock_transcription):
            with patch.object(
                voice_service,
                "extract_task_from_transcription",
                new_callable=AsyncMock,
                return_value=[]  # No extracted tasks
            ):
                result = await voice_service.create_task_from_audio(
                    audio_data=b"fake audio",
                    task_service=mock_task_service,
                )
                
                assert result.transcription == "Something vague"
                assert result.created_task == mock_created_task
                # Fallback uses transcription as title
                mock_task_service.create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_task_from_audio_empty_transcription(self, voice_service):
        """Test creating task when transcription is empty."""
        mock_transcription = MagicMock()
        mock_transcription.text = ""
        
        mock_task_service = MagicMock()
        
        with patch.object(voice_service, "transcribe_audio", return_value=mock_transcription):
            result = await voice_service.create_task_from_audio(
                audio_data=b"fake audio",
                task_service=mock_task_service,
            )
            
            assert result.transcription == ""
            assert result.created_task is None
            assert len(result.extracted_tasks) == 0


class TestDataclasses:
    """Tests for dataclasses."""

    def test_transcription_result(self):
        """Test TranscriptionResult dataclass."""
        result = TranscriptionResult(
            text="Hello world",
            language="en",
            duration_seconds=2.5,
        )
        assert result.text == "Hello world"
        assert result.language == "en"
        assert result.duration_seconds == 2.5

    def test_transcription_result_optional_fields(self):
        """Test TranscriptionResult with optional fields."""
        result = TranscriptionResult(text="Hello")
        assert result.text == "Hello"
        assert result.language is None
        assert result.duration_seconds is None

    def test_voice_task_result(self):
        """Test VoiceTaskResult dataclass."""
        from src.services.llm_service import ExtractedTask
        
        result = VoiceTaskResult(
            transcription="Test",
            extracted_tasks=[ExtractedTask(title="Task", priority="medium")],
            created_task=None,
        )
        assert result.transcription == "Test"
        assert len(result.extracted_tasks) == 1


class TestExceptions:
    """Tests for custom exceptions."""

    def test_voice_error(self):
        """Test VoiceError exception."""
        error = VoiceError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert isinstance(error, Exception)

    def test_microphone_not_found_error(self):
        """Test MicrophoneNotFoundError exception."""
        error = MicrophoneNotFoundError("No microphone found")
        assert str(error) == "No microphone found"
        assert isinstance(error, VoiceError)

    def test_transcription_error(self):
        """Test TranscriptionError exception."""
        error = TranscriptionError("Transcription failed")
        assert str(error) == "Transcription failed"
        assert isinstance(error, VoiceError)
