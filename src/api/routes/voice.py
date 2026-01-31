"""Voice input API routes for task creation."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from src.api.routes.tasks import _task_to_response
from src.api.schemas import TaskResponse, VoiceTaskResponse, TranscriptionResponse
from src.models import get_db
from src.services.task_service import TaskService
from src.services.voice_service import (
    MicrophoneNotFoundError,
    TranscriptionError,
    VoiceError,
    VoiceService,
)
from src.utils.config import get_config

router = APIRouter(prefix="/tasks/voice", tags=["voice"])


def get_voice_service() -> VoiceService:
    """Dependency to get voice service."""
    config = get_config()
    return VoiceService(
        voice_config=config.voice,
        llm_config=config.llm,
    )


def get_task_service(db: Session = Depends(get_db)) -> TaskService:
    """Dependency to get task service."""
    return TaskService(db)


@router.post("", response_model=VoiceTaskResponse, status_code=201)
async def create_task_from_voice(
    audio: UploadFile = File(..., description="Audio file (WAV, MP3, etc.)"),
    language: str | None = Query(default=None, description="Language hint (e.g., 'en', 'es')"),
    voice_service: Annotated[VoiceService, Depends(get_voice_service)] = None,
    task_service: Annotated[TaskService, Depends(get_task_service)] = None,
) -> VoiceTaskResponse:
    """Create a task from uploaded audio.

    Upload an audio file, which will be:
    1. Transcribed using Whisper API
    2. Analyzed by LLM to extract task details
    3. Created as a new task

    Supported formats: WAV, MP3, M4A, WEBM, MP4, MPEG, OGG, FLAC
    """
    config = get_config()
    if not config.voice.enabled:
        raise HTTPException(
            status_code=400,
            detail="Voice features are disabled in configuration"
        )

    try:
        # Read audio data from upload
        audio_data = await audio.read()

        if len(audio_data) == 0:
            raise HTTPException(status_code=400, detail="Empty audio file")

        # Create task from audio
        result = await voice_service.create_task_from_audio(
            audio_data=audio_data,
            task_service=task_service,
            language=language,
        )

        return VoiceTaskResponse(
            transcription=result.transcription,
            task=_task_to_response(result.created_task) if result.created_task else None,
            extracted_tasks_count=len(result.extracted_tasks),
        )

    except HTTPException:
        raise
    except TranscriptionError as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")
    except VoiceError as e:
        raise HTTPException(status_code=500, detail=f"Voice processing error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    audio: UploadFile = File(..., description="Audio file (WAV, MP3, etc.)"),
    language: str | None = Query(default=None, description="Language hint (e.g., 'en', 'es')"),
    voice_service: Annotated[VoiceService, Depends(get_voice_service)] = None,
) -> TranscriptionResponse:
    """Transcribe audio without creating a task.

    Use this endpoint to transcribe audio and see the result before
    deciding to create a task.

    Supported formats: WAV, MP3, M4A, WEBM, MP4, MPEG, OGG, FLAC
    """
    config = get_config()
    if not config.voice.enabled:
        raise HTTPException(
            status_code=400,
            detail="Voice features are disabled in configuration"
        )

    try:
        # Read audio data from upload
        audio_data = await audio.read()

        if len(audio_data) == 0:
            raise HTTPException(status_code=400, detail="Empty audio file")

        # Transcribe only
        result = voice_service.transcribe_audio(audio_data, language)

        return TranscriptionResponse(
            text=result.text,
            language=result.language,
            duration_seconds=result.duration_seconds,
        )

    except HTTPException:
        raise
    except TranscriptionError as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")
    except VoiceError as e:
        raise HTTPException(status_code=500, detail=f"Voice processing error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@router.get("/status")
def voice_status() -> dict:
    """Check voice feature status.

    Returns information about voice capabilities including:
    - Whether voice features are enabled
    - Microphone availability
    """
    config = get_config()
    voice_service = VoiceService(
        voice_config=config.voice,
        llm_config=config.llm,
    )

    return {
        "enabled": config.voice.enabled,
        "microphone_available": voice_service.check_microphone_available(),
        "whisper_model": config.voice.whisper_model,
        "default_duration_seconds": config.voice.recording_duration_seconds,
        "sample_rate": config.voice.sample_rate,
    }
