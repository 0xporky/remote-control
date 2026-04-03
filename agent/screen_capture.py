import asyncio
import logging
import time
from typing import Optional, AsyncGenerator

import mss
import mss.tools
from PIL import Image

logger = logging.getLogger(__name__)


class ScreenCapture:
    """Efficient screen capture using mss library."""

    def __init__(self, monitor: int = 1, scale: float = 1.0, fps: int = 30):
        """
        Initialize screen capture.

        Args:
            monitor: Monitor number (0 = all monitors, 1 = primary, 2+ = secondary)
            scale: Scale factor for resolution (0.5 = half size, 1.0 = full size)
            fps: Target frames per second
        """
        self.monitor = monitor
        self.scale = scale
        self.fps = fps
        self.frame_interval = 1.0 / fps

        self._sct: Optional[mss.mss] = None
        self._running = False

        # Stats
        self._frame_count = 0
        self._start_time = 0.0
        self._last_frame_time = 0.0

    def _get_sct(self) -> mss.mss:
        """Get or create mss instance."""
        if self._sct is None:
            self._sct = mss.mss()
        return self._sct

    @property
    def monitor_info(self) -> dict:
        """Get information about the selected monitor."""
        sct = self._get_sct()
        if self.monitor < len(sct.monitors):
            return sct.monitors[self.monitor]
        return sct.monitors[1]  # Fallback to primary

    @property
    def monitors(self) -> list[dict]:
        """Get list of all available monitors."""
        sct = self._get_sct()
        return sct.monitors

    def capture_frame(self) -> Image.Image:
        """
        Capture a single frame from the screen.

        Returns:
            PIL Image of the captured frame
        """
        sct = self._get_sct()
        monitor = self.monitor_info

        # Capture the screen
        screenshot = sct.grab(monitor)

        # Convert to PIL Image (BGRA -> RGB)
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

        # Scale if needed
        if self.scale != 1.0:
            new_width = int(img.width * self.scale)
            new_height = int(img.height * self.scale)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        return img

    def capture_frame_bytes(self, format: str = "JPEG", quality: int = 85) -> bytes:
        """
        Capture a frame and return as bytes.

        Args:
            format: Image format (JPEG, PNG, etc.)
            quality: JPEG quality (1-100)

        Returns:
            Image bytes
        """
        import io

        img = self.capture_frame()
        buffer = io.BytesIO()

        if format.upper() == "JPEG":
            img.save(buffer, format="JPEG", quality=quality, optimize=True)
        else:
            img.save(buffer, format=format)

        return buffer.getvalue()

    async def capture_frames(self) -> AsyncGenerator[Image.Image, None]:
        """
        Async generator that yields screen frames at the target FPS.

        Yields:
            PIL Image for each frame
        """
        self._running = True
        self._frame_count = 0
        self._start_time = time.time()

        logger.info(f"Starting screen capture: monitor={self.monitor}, "
                   f"scale={self.scale}, fps={self.fps}")

        try:
            while self._running:
                frame_start = time.time()

                # Capture frame
                frame = self.capture_frame()
                self._frame_count += 1
                self._last_frame_time = time.time()

                yield frame

                # Calculate sleep time to maintain FPS
                elapsed = time.time() - frame_start
                sleep_time = max(0, self.frame_interval - elapsed)

                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except Exception as e:
            logger.error(f"Screen capture error: {e}")
            raise
        finally:
            self._running = False
            logger.info(f"Screen capture stopped. "
                       f"Captured {self._frame_count} frames")

    async def capture_frames_bytes(
        self,
        format: str = "JPEG",
        quality: int = 85
    ) -> AsyncGenerator[bytes, None]:
        """
        Async generator that yields screen frames as bytes.

        Args:
            format: Image format (JPEG, PNG)
            quality: JPEG quality (1-100)

        Yields:
            Image bytes for each frame
        """
        async for frame in self.capture_frames():
            import io
            buffer = io.BytesIO()

            if format.upper() == "JPEG":
                frame.save(buffer, format="JPEG", quality=quality, optimize=True)
            else:
                frame.save(buffer, format=format)

            yield buffer.getvalue()

    def stop(self):
        """Stop the capture loop."""
        self._running = False

    def get_stats(self) -> dict:
        """Get capture statistics."""
        elapsed = time.time() - self._start_time if self._start_time else 0
        actual_fps = self._frame_count / elapsed if elapsed > 0 else 0

        return {
            "frame_count": self._frame_count,
            "elapsed_time": elapsed,
            "actual_fps": round(actual_fps, 2),
            "target_fps": self.fps,
            "monitor": self.monitor,
            "scale": self.scale,
        }

    def close(self):
        """Clean up resources."""
        if self._sct:
            self._sct.close()
            self._sct = None


# Utility function to list monitors
def list_monitors() -> list[dict]:
    """List all available monitors."""
    with mss.mss() as sct:
        monitors = []
        for i, mon in enumerate(sct.monitors):
            monitors.append({
                "index": i,
                "left": mon["left"],
                "top": mon["top"],
                "width": mon["width"],
                "height": mon["height"],
                "is_primary": i == 1,
                "is_all": i == 0,
            })
        return monitors


if __name__ == "__main__":
    # Test screen capture
    import sys

    logging.basicConfig(level=logging.INFO)

    print("Available monitors:")
    for mon in list_monitors():
        print(f"  {mon}")

    print("\nCapturing 10 frames...")
    capture = ScreenCapture(monitor=1, scale=0.5, fps=10)

    async def test_capture():
        count = 0
        async for frame in capture.capture_frames():
            count += 1
            print(f"Frame {count}: {frame.size}")
            if count >= 10:
                capture.stop()

        print(f"\nStats: {capture.get_stats()}")

    asyncio.run(test_capture())
    capture.close()
