import { useEffect, useCallback, useState, type RefObject } from 'react';
import type { InputEvent } from '../types';

interface UseInputCaptureOptions {
  videoRef: RefObject<HTMLVideoElement | null>;
  onInput: (event: InputEvent) => void;
  enabled: boolean;
}

interface UseInputCaptureResult {
  isCapturing: boolean;
  requestCapture: () => void;
  releaseCapture: () => void;
}

export function useInputCapture({
  videoRef,
  onInput,
  enabled,
}: UseInputCaptureOptions): UseInputCaptureResult {
  const [isCapturing, setIsCapturing] = useState(false);

  const requestCapture = useCallback(() => {
    const video = videoRef.current;
    if (!video || !enabled) return;

    video.requestPointerLock();
  }, [videoRef, enabled]);

  const releaseCapture = useCallback(() => {
    if (document.pointerLockElement) {
      document.exitPointerLock();
    }
  }, []);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !enabled) return;

    // Pointer lock change handler
    const handlePointerLockChange = () => {
      const isLocked = document.pointerLockElement === video;
      setIsCapturing(isLocked);
    };

    // Pointer lock error handler
    const handlePointerLockError = () => {
      console.error('Pointer lock failed');
      setIsCapturing(false);
    };

    // Mouse move handler (only works when pointer is locked)
    const handleMouseMove = (e: MouseEvent) => {
      if (document.pointerLockElement !== video) return;

      onInput({
        type: 'mousemove',
        dx: e.movementX,
        dy: e.movementY,
      });
    };

    // Mouse button handlers
    const handleMouseDown = (e: MouseEvent) => {
      if (document.pointerLockElement !== video) return;

      e.preventDefault();
      onInput({
        type: 'mousedown',
        button: e.button,
      });
    };

    const handleMouseUp = (e: MouseEvent) => {
      if (document.pointerLockElement !== video) return;

      e.preventDefault();
      onInput({
        type: 'mouseup',
        button: e.button,
      });
    };

    // Wheel handler
    const handleWheel = (e: WheelEvent) => {
      if (document.pointerLockElement !== video) return;

      e.preventDefault();
      onInput({
        type: 'wheel',
        deltaX: e.deltaX,
        deltaY: e.deltaY,
      });
    };

    // Keyboard handlers
    const handleKeyDown = (e: KeyboardEvent) => {
      if (document.pointerLockElement !== video) return;

      // Prevent browser shortcuts
      e.preventDefault();

      // Escape releases pointer lock (handled by browser), don't send it
      if (e.key === 'Escape') return;

      onInput({
        type: 'keydown',
        key: e.key,
        code: e.code,
      });
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (document.pointerLockElement !== video) return;

      e.preventDefault();

      if (e.key === 'Escape') return;

      onInput({
        type: 'keyup',
        key: e.key,
        code: e.code,
      });
    };

    // Context menu prevention (right-click)
    const handleContextMenu = (e: MouseEvent) => {
      if (document.pointerLockElement === video) {
        e.preventDefault();
      }
    };

    // Convert a touch's client coordinates into normalized (0..1) coords
    // within the actual displayed video area, accounting for object-fit
    // letterboxing. Returns null if the touch is outside the video.
    const getNormalizedTouchCoords = (
      clientX: number,
      clientY: number,
    ): { nx: number; ny: number } | null => {
      const rect = video.getBoundingClientRect();
      const vw = video.videoWidth;
      const vh = video.videoHeight;
      if (!vw || !vh || !rect.width || !rect.height) return null;

      const elemAspect = rect.width / rect.height;
      const videoAspect = vw / vh;

      let displayedW: number;
      let displayedH: number;
      let offsetX: number;
      let offsetY: number;
      if (videoAspect > elemAspect) {
        displayedW = rect.width;
        displayedH = rect.width / videoAspect;
        offsetX = 0;
        offsetY = (rect.height - displayedH) / 2;
      } else {
        displayedH = rect.height;
        displayedW = rect.height * videoAspect;
        offsetX = (rect.width - displayedW) / 2;
        offsetY = 0;
      }

      const x = clientX - rect.left - offsetX;
      const y = clientY - rect.top - offsetY;
      if (x < 0 || x > displayedW || y < 0 || y > displayedH) return null;
      return { nx: x / displayedW, ny: y / displayedH };
    };

    // Touch handlers. Single-finger touch is treated as left-button input:
    // touchstart positions the cursor + presses, touchmove drags,
    // touchend releases. Multi-touch is ignored to avoid spurious clicks.
    let touchActive = false;

    const handleTouchStart = (e: TouchEvent) => {
      if (e.touches.length !== 1) return;
      const t = e.touches[0];
      const coords = getNormalizedTouchCoords(t.clientX, t.clientY);
      if (!coords) return;
      e.preventDefault();
      touchActive = true;
      onInput({ type: 'mouseabs', nx: coords.nx, ny: coords.ny });
      onInput({ type: 'mousedown', button: 0 });
    };

    const handleTouchMove = (e: TouchEvent) => {
      if (!touchActive || e.touches.length !== 1) return;
      const t = e.touches[0];
      const coords = getNormalizedTouchCoords(t.clientX, t.clientY);
      if (!coords) return;
      e.preventDefault();
      onInput({ type: 'mouseabs', nx: coords.nx, ny: coords.ny });
    };

    const handleTouchEnd = (e: TouchEvent) => {
      if (!touchActive) return;
      e.preventDefault();
      touchActive = false;
      onInput({ type: 'mouseup', button: 0 });
    };

    const handleTouchCancel = () => {
      if (!touchActive) return;
      touchActive = false;
      onInput({ type: 'mouseup', button: 0 });
    };

    // Add event listeners
    document.addEventListener('pointerlockchange', handlePointerLockChange);
    document.addEventListener('pointerlockerror', handlePointerLockError);
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mousedown', handleMouseDown);
    document.addEventListener('mouseup', handleMouseUp);
    document.addEventListener('wheel', handleWheel, { passive: false });
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('keyup', handleKeyUp);
    document.addEventListener('contextmenu', handleContextMenu);
    video.addEventListener('touchstart', handleTouchStart, { passive: false });
    video.addEventListener('touchmove', handleTouchMove, { passive: false });
    video.addEventListener('touchend', handleTouchEnd, { passive: false });
    video.addEventListener('touchcancel', handleTouchCancel);

    // Cleanup
    return () => {
      document.removeEventListener('pointerlockchange', handlePointerLockChange);
      document.removeEventListener('pointerlockerror', handlePointerLockError);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mousedown', handleMouseDown);
      document.removeEventListener('mouseup', handleMouseUp);
      document.removeEventListener('wheel', handleWheel);
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('keyup', handleKeyUp);
      document.removeEventListener('contextmenu', handleContextMenu);
      video.removeEventListener('touchstart', handleTouchStart);
      video.removeEventListener('touchmove', handleTouchMove);
      video.removeEventListener('touchend', handleTouchEnd);
      video.removeEventListener('touchcancel', handleTouchCancel);

      // Release pointer lock on cleanup
      if (document.pointerLockElement === video) {
        document.exitPointerLock();
      }
    };
  }, [videoRef, onInput, enabled]);

  // Release capture if disabled
  useEffect(() => {
    if (!enabled && isCapturing) {
      releaseCapture();
    }
  }, [enabled, isCapturing, releaseCapture]);

  return {
    isCapturing,
    requestCapture,
    releaseCapture,
  };
}
