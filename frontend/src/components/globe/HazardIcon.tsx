import { hazardIconMarkup, type HazardKind } from "@/lib/hazard-icons";

type HazardIconProps = {
  type: HazardKind;
  className?: string;
  /** Mirror the cyclone so it spins clockwise (southern hemisphere). */
  south?: boolean;
  paused?: boolean;
};

export function HazardIcon({ type, className = "", south, paused }: HazardIconProps) {
  const classes = ["hz", south && "hz--south", paused && "hz-paused", className].filter(Boolean).join(" ");
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden
      className={classes}
      // Static, trusted markup shared with the globe's DOM markers.
      dangerouslySetInnerHTML={{ __html: hazardIconMarkup[type] }}
    />
  );
}
