import { Capacitor } from '@capacitor/core';

export async function hapticLight() {
  if (!Capacitor.isNativePlatform()) return;
  const { Haptics, ImpactStyle } = await import('@capacitor/haptics');
  await Haptics.impact({ style: ImpactStyle.Light });
}

export async function hapticMedium() {
  if (!Capacitor.isNativePlatform()) return;
  const { Haptics, ImpactStyle } = await import('@capacitor/haptics');
  await Haptics.impact({ style: ImpactStyle.Medium });
}
