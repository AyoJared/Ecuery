import { useTransform, type MotionValue } from "motion/react";

/**
 * Like `useTransform(value, [inA, inB], [outA, outB])`, but always computed in JS and clamped.
 *
 * Motion offloads the array form of scroll-linked opacity to Chrome's native ScrollTimeline /
 * ViewTimeline, which mis-maps `useScroll({ target, offset })` ranges: values overshoot and
 * never settle (hero text stayed at ~26% instead of 0, pinned words re-dimmed). The function
 * form isn't offloaded, so it behaves the same in every browser.
 */
export function useClampedTransform(
  value: MotionValue<number>,
  [inA, inB]: [number, number],
  [outA, outB]: [number, number],
) {
  return useTransform(value, (v) => {
    const t = Math.min(Math.max((v - inA) / (inB - inA), 0), 1);
    return outA + t * (outB - outA);
  });
}
