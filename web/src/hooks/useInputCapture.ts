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
