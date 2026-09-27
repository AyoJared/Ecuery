import { palette } from "./palette";

// Dark theme for Clerk's hosted UI (sign-in / sign-up modals, user menu), matched to the site palette.
export const clerkAppearance = {
  variables: {
    colorPrimary: palette.ocean,
    colorPrimaryForeground: palette.canvas,
    colorBackground: palette.surface,
    colorForeground: palette.ink,
    colorMutedForeground: palette.inkMuted,
    colorInput: palette.surfaceRaised,
    colorInputForeground: palette.ink,
    colorNeutral: palette.ink,
    colorBorder: "rgba(196, 216, 236, 0.12)",
    colorModalBackdrop: "rgba(5, 9, 14, 0.75)",
    borderRadius: "0.75rem",
    fontFamily: "var(--font-geist-sans)",
  },
};
