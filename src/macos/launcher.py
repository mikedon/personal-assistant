"""Launcher script for the macOS menu bar application.

Handles:
- Starting the API server (if not running)
- Starting the menu bar app
- Managing process lifecycle
"""

import subprocess
import sys
import time

import httpx


def check_api_running(api_url: str = "http://localhost:8000", timeout: float = 2.0) -> bool:
    """Check if the API server is running.

    Args:
        api_url: Base URL of the API
        timeout: Timeout for health check

    Returns:
        True if API is running, False otherwise
    """
    try:
        response = httpx.get(f"{api_url}/health", timeout=timeout)
        return response.status_code == 200
    except Exception:
        return False


def start_api_server(port: int = 8000, reload: bool = False) -> subprocess.Popen:
    """Start the API server.

    Args:
        port: Port to run the server on
        reload: Enable auto-reload on file changes

    Returns:
        Subprocess handle

    Raises:
        RuntimeError: If server cannot be started
    """
    cmd = [sys.executable, "-m", "uvicorn", "src.api.main:app"]

    if reload:
        cmd.append("--reload")

    cmd.extend(["--host", "localhost", "--port", str(port)])

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return process
    except Exception as e:
        raise RuntimeError(f"Failed to start API server: {e}")


def wait_for_api(api_url: str = "http://localhost:8000", max_retries: int = 30) -> bool:
    """Wait for the API server to become available.

    Args:
        api_url: Base URL of the API
        max_retries: Maximum number of retry attempts

    Returns:
        True if API became available, False if timeout

    """
    for attempt in range(max_retries):
        if check_api_running(api_url):
            print(f"✓ API server is running at {api_url}")
            return True

        if attempt > 0:
            print(f"  Waiting for API... ({attempt}/{max_retries})")

        time.sleep(1)

    return False


def start_menu_app(api_url: str = "http://localhost:8000", refresh_interval: int = 300) -> None:
    """Start the menu bar application.

    Args:
        api_url: Base URL of the personal assistant API
        refresh_interval: How often to refresh task data (seconds)

    Raises:
        RuntimeError: If menu app cannot be started
    """
    try:
        from src.macos.menu_app import run_menu_app

        run_menu_app(api_url=api_url, refresh_interval=refresh_interval)
    except ImportError as e:
        raise RuntimeError(
            f"Failed to import menu app: {e}\n"
            "Make sure you're on macOS and PyObjC is installed: pip install pyobjc"
        )
    except Exception as e:
        raise RuntimeError(f"Failed to start menu app: {e}")


def launch(
    api_url: str = "http://localhost:8000",
    start_api: bool = True,
    refresh_interval: int = 300,
) -> None:
    """Launch the Personal Assistant with menu bar integration.

    Args:
        api_url: Base URL of the personal assistant API
        start_api: Whether to start the API server if not running
        refresh_interval: How often to refresh task data (seconds)
    """
    print("🚀 Personal Assistant - macOS Menu Bar")
    print("-" * 40)

    # Check if API is running
    if check_api_running(api_url):
        print(f"✓ API server is already running at {api_url}")
    elif start_api:
        print(f"Starting API server on {api_url}...")
        api_process = start_api_server()

        if not wait_for_api(api_url):
            print("✗ Failed to start API server")
            api_process.terminate()
            sys.exit(1)
    else:
        print(f"✗ API server is not running at {api_url}")
        print("  Start it manually or run with --start-api")
        sys.exit(1)

    # Start menu bar app
    print("Starting menu bar application...")
    try:
        start_menu_app(api_url=api_url, refresh_interval=refresh_interval)
    except RuntimeError as e:
        print(f"✗ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Launch Personal Assistant with macOS menu bar"
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Base URL of the personal assistant API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--start-api",
        action="store_true",
        default=True,
        help="Start the API server if not running (default: True)",
    )
    parser.add_argument(
        "--no-start-api",
        action="store_true",
        help="Don't start the API server automatically",
    )
    parser.add_argument(
        "--refresh-interval",
        type=int,
        default=300,
        help="How often to refresh task data in seconds (default: 300)",
    )

    args = parser.parse_args()

    launch(
        api_url=args.api_url,
        start_api=(not args.no_start_api),
        refresh_interval=args.refresh_interval,
    )
