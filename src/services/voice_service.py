"""Voice input service for task creation.

Provides functionality for recording audio, transcribing speech to text,
and creating tasks from voice input using OpenAI Whisper API.
"""

import io
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np
import sounddevice as sd
import soundfile as sf
from openai import OpenAI

from src.models.task import Task, TaskPriority, TaskSource
from src.services.llm_service import ExtractedTask, LLMService
from src.services.task_service import TaskService
from src.utils.config import LLMConfig, VoiceConfig

logger = logging.getLogger(__name__)


class VoiceError(Exception):
    """Exception raised for voice service errors."""

    pass


class MicrophoneNotFoundError(VoiceError):
    """Exception raised when no microphone is available."""

    pass


class TranscriptionError(VoiceError):
    """Exception raised when transcription fails."""

    pass


@dataclass
class TranscriptionResult:
    """Result of audio transcription."""

    text: str
    language: str | None = None
    duration_seconds: float | None = None


@dataclass
class VoiceTaskResult:
    """Result of creating a task from voice input."""

    transcription: str
    extracted_tasks: list[ExtractedTask]
    created_task: Task | None = None


class VoiceService:
    """Service for voice-based task creation."""

    def __init__(
        self,
        voice_config: VoiceConfig,
        llm_config: LLMConfig,
        llm_service: LLMService | None = None,
    ):
        """Initialize the voice service.

        Args:
            voice_config: Voice configuration settings
            llm_config: LLM configuration for Whisper API access
            llm_service: Optional LLM service for task extraction (created if not provided)
        """
        self.voice_config = voice_config
        self.llm_config = llm_config
        self.llm_service = llm_service or LLMService(llm_config)

        # Initialize OpenAI client for Whisper (litellm doesn't support audio yet)
        self._openai_client: OpenAI | None = None

    def _get_openai_client(self) -> OpenAI:
        """Get or create OpenAI client for Whisper API."""
        if self._openai_client is None:
            self._openai_client = OpenAI(
                api_key=self.llm_config.api_key,
                base_url=self.llm_config.base_url if self.llm_config.base_url != "https://api.openai.com/v1" else None,
            )
        return self._openai_client

    def check_microphone_available(self) -> bool:
        """Check if a microphone is available.

        Returns:
            True if a microphone is available, False otherwise
        """
        try:
            devices = sd.query_devices()
            for device in devices:
                if device.get("max_input_channels", 0) > 0:
                    return True
            return False
        except Exception as e:
            logger.warning(f"Error checking for microphone: {e}")
            return False

    def record_audio(
        self,
        duration_seconds: int | None = None,
        sample_rate: int | None = None,
    ) -> bytes:
        """Record audio from the default microphone.

        Args:
            duration_seconds: Recording duration (uses config default if not provided)
            sample_rate: Audio sample rate (uses config default if not provided)

        Returns:
            Audio data as WAV bytes

        Raises:
            MicrophoneNotFoundError: If no microphone is available
            VoiceError: If recording fails
        """
        if not self.check_microphone_available():
            raise MicrophoneNotFoundError(
                "No microphone found. Please connect a microphone and try again."
            )

        duration = duration_seconds or self.voice_config.recording_duration_seconds
        rate = sample_rate or self.voice_config.sample_rate

        logger.info(f"Recording audio for {duration} seconds at {rate}Hz...")

        try:
            # Record audio
            audio_data = sd.rec(
                int(duration * rate),
                samplerate=rate,
                channels=1,
                dtype=np.float32,
            )
            sd.wait()  # Wait for recording to complete

            # Convert to WAV bytes
            buffer = io.BytesIO()
            sf.write(buffer, audio_data, rate, format="WAV")
            buffer.seek(0)

            logger.info(f"Recording complete: {len(buffer.getvalue())} bytes")
            return buffer.getvalue()

        except Exception as e:
            logger.error(f"Recording failed: {e}")
            raise VoiceError(f"Failed to record audio: {e}") from e

    def transcribe_audio(
        self,
        audio_data: bytes,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio to text using Whisper API.

        Args:
            audio_data: Audio data as bytes (WAV format)
            language: Optional language hint (e.g., "en", "es")

        Returns:
            TranscriptionResult with transcribed text

        Raises:
            TranscriptionError: If transcription fails
        """
        if not self.voice_config.enabled:
            raise VoiceError("Voice features are disabled in configuration")

        logger.info("Transcribing audio...")

        try:
            client = self._get_openai_client()

            # Create a temporary file for the audio (OpenAI API requires a file)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                tmp_file.write(audio_data)
                tmp_path = Path(tmp_file.name)

            try:
                # Transcribe using Whisper API
                with open(tmp_path, "rb") as audio_file:
                    kwargs = {
                        "model": self.voice_config.whisper_model,
                        "file": audio_file,
                        "response_format": "verbose_json",
                    }
                    if language:
                        kwargs["language"] = language

                    response = client.audio.transcriptions.create(**kwargs)

                text = response.text.strip()
                result_language = getattr(response, "language", None)
                duration = getattr(response, "duration", None)

                logger.info(f"Transcription complete: '{text[:100]}...' ({len(text)} chars)")

                return TranscriptionResult(
                    text=text,
                    language=result_language,
                    duration_seconds=duration,
                )

            finally:
                # Clean up temp file
                tmp_path.unlink(missing_ok=True)

        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise TranscriptionError(f"Failed to transcribe audio: {e}") from e

    def transcribe_audio_file(
        self,
        file: BinaryIO,
        language: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe audio from a file-like object.

        Args:
            file: File-like object containing audio data
            language: Optional language hint

        Returns:
            TranscriptionResult with transcribed text
        """
        audio_data = file.read()
        return self.transcribe_audio(audio_data, language)

    async def extract_task_from_transcription(
        self,
        transcription: str,
    ) -> list[ExtractedTask]:
        """Extract tasks from transcribed text using LLM.

        Args:
            transcription: Transcribed text from voice input

        Returns:
            List of extracted tasks
        """
        return await self.llm_service.extract_tasks_from_text(
            text=transcription,
            source="voice",
            context="This is a voice transcription from the user. Extract any tasks they mentioned.",
        )

    async def create_task_from_voice(
        self,
        task_service: TaskService,
        duration_seconds: int | None = None,
    ) -> VoiceTaskResult:
        """Record audio, transcribe, extract task, and create it.

        This is the main end-to-end method for voice task creation.

        Args:
            task_service: TaskService instance for creating the task
            duration_seconds: Recording duration (uses config default if not provided)

        Returns:
            VoiceTaskResult with transcription, extracted tasks, and created task
        """
        # Record audio
        audio_data = self.record_audio(duration_seconds)

        # Transcribe
        transcription_result = self.transcribe_audio(audio_data)

        if not transcription_result.text:
            return VoiceTaskResult(
                transcription="",
                extracted_tasks=[],
                created_task=None,
            )

        # Extract tasks
        extracted_tasks = await self.extract_task_from_transcription(
            transcription_result.text
        )

        # Create the first extracted task (or a simple task from transcription)
        created_task = None
        if extracted_tasks:
            task_data = extracted_tasks[0]
            created_task = task_service.create_task(
                title=task_data.title,
                description=task_data.description,
                priority=TaskPriority(task_data.priority),
                source=TaskSource.VOICE,
                due_date=task_data.due_date,
                tags=task_data.tags,
            )
        else:
            # If no task was extracted, create a simple task from the transcription
            created_task = task_service.create_task(
                title=transcription_result.text[:200],
                description=None,
                priority=TaskPriority.MEDIUM,
                source=TaskSource.VOICE,
            )

        return VoiceTaskResult(
            transcription=transcription_result.text,
            extracted_tasks=extracted_tasks,
            created_task=created_task,
        )

    async def create_task_from_audio(
        self,
        audio_data: bytes,
        task_service: TaskService,
        language: str | None = None,
    ) -> VoiceTaskResult:
        """Create a task from uploaded audio data.

        Args:
            audio_data: Audio data as bytes
            task_service: TaskService instance for creating the task
            language: Optional language hint for transcription

        Returns:
            VoiceTaskResult with transcription, extracted tasks, and created task
        """
        # Transcribe
        transcription_result = self.transcribe_audio(audio_data, language)

        if not transcription_result.text:
            return VoiceTaskResult(
                transcription="",
                extracted_tasks=[],
                created_task=None,
            )

        # Extract tasks
        extracted_tasks = await self.extract_task_from_transcription(
            transcription_result.text
        )

        # Create the first extracted task (or a simple task from transcription)
        created_task = None
        if extracted_tasks:
            task_data = extracted_tasks[0]
            created_task = task_service.create_task(
                title=task_data.title,
                description=task_data.description,
                priority=TaskPriority(task_data.priority),
                source=TaskSource.VOICE,
                due_date=task_data.due_date,
                tags=task_data.tags,
            )
        else:
            # If no task was extracted, create a simple task from the transcription
            created_task = task_service.create_task(
                title=transcription_result.text[:200],
                description=None,
                priority=TaskPriority.MEDIUM,
                source=TaskSource.VOICE,
            )

        return VoiceTaskResult(
            transcription=transcription_result.text,
            extracted_tasks=extracted_tasks,
            created_task=created_task,
        )
