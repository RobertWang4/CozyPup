import { useState, useCallback } from 'react';
import { Capacitor } from '@capacitor/core';

interface Location {
  lat: number;
  lng: number;
}

export function useLocation() {
  const [lastLocation, setLastLocation] = useState<Location | null>(null);

  const requestLocation = useCallback(async (): Promise<Location | null> => {
    try {
      if (Capacitor.isNativePlatform()) {
        const { Geolocation } = await import('@capacitor/geolocation');
        const pos = await Geolocation.getCurrentPosition();
        const loc = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        setLastLocation(loc);
        return loc;
      } else if ('geolocation' in navigator) {
        return new Promise((resolve) => {
          navigator.geolocation.getCurrentPosition(
            (pos) => {
              const loc = { lat: pos.coords.latitude, lng: pos.coords.longitude };
              setLastLocation(loc);
              resolve(loc);
            },
            () => resolve(null)
          );
        });
      }
      return null;
    } catch {
      return null;
    }
  }, []);

  return { lastLocation, requestLocation };
}
