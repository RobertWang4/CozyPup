import { useEffect } from 'react';

interface UseSwipeOptions {
  onSwipeRight?: () => void;  // swipe right from left edge → open calendar
  onSwipeLeft?: () => void;   // swipe left from right edge → open settings
  edgeThreshold?: number;     // default 30px — how close to edge touch must start
  minDistance?: number;        // default 50px — minimum swipe distance
}

export function useSwipe(options: UseSwipeOptions) {
  const {
    onSwipeRight,
    onSwipeLeft,
    edgeThreshold = 30,
    minDistance = 50,
  } = options;

  useEffect(() => {
    let startX = 0;
    let startY = 0;
    let fromLeftEdge = false;
    let fromRightEdge = false;

    function handleTouchStart(e: TouchEvent) {
      const touch = e.touches[0];
      startX = touch.clientX;
      startY = touch.clientY;
      fromLeftEdge = startX <= edgeThreshold;
      fromRightEdge = startX >= window.innerWidth - edgeThreshold;
    }

    function handleTouchEnd(e: TouchEvent) {
      if (!fromLeftEdge && !fromRightEdge) return;

      const touch = e.changedTouches[0];
      const dx = touch.clientX - startX;
      const dy = touch.clientY - startY;

      // Must be more horizontal than vertical
      if (Math.abs(dx) < Math.abs(dy)) return;

      // Must meet minimum distance
      if (Math.abs(dx) < minDistance) return;

      if (fromLeftEdge && dx > 0 && onSwipeRight) {
        onSwipeRight();
      } else if (fromRightEdge && dx < 0 && onSwipeLeft) {
        onSwipeLeft();
      }
    }

    document.addEventListener('touchstart', handleTouchStart, { passive: true });
    document.addEventListener('touchend', handleTouchEnd, { passive: true });

    return () => {
      document.removeEventListener('touchstart', handleTouchStart);
      document.removeEventListener('touchend', handleTouchEnd);
    };
  }, [onSwipeRight, onSwipeLeft, edgeThreshold, minDistance]);
}
