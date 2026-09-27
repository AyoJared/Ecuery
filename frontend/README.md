# Ecuery — frontend

Next.js 16 (App Router) · React 19 · Tailwind CSS v4 · Clerk v7.

## Run locally

```bash
cd frontend
npm install
cp .env.example .env.local   # then paste your Clerk keys
npm run dev                  # http://localhost:3000, hot reload via Turbopack
```

Without Clerk keys the app still runs; the Sign in / Get started buttons are just inert.
Get keys from https://dashboard.clerk.com → API keys (enable Google under
User & Authentication → SSO connections).

## Structure

```
src/
  app/
    layout.tsx            root layout, fonts, ClerkProvider
    page.tsx              landing page (composes sections)
    globals.css           design tokens (@theme) — colors, fonts
  components/
    Providers.tsx         MotionConfig (respects reduce-motion) + SearchProvider
    layout/               Header, Footer, Logo
    hero/                 VideoHero (rotating background clips + captions), ClipLayer
    ask/                  AskSection — search bar + event globe side by side
    landing/              HowItWorks, ClosingCta, ScrollProgress, SectionHeading, Backdrop…
    globe/                EarthGlobe (react-globe.gl, client-only), EventCard, HazardIcon
    showcase/             ShowcaseSection, AnswerCard (typewriter → answer → chart), ShowcaseChart (Recharts)
    motion/               Reveal — wrap anything to fade it up on scroll
    search/               SearchContext (shared query + ask()), SearchPanel, SearchBar, ExampleQueries
    auth/                 AuthButtons (Clerk sign-in / sign-up / user menu)
  lib/
    events.ts             globe events (notable historical storms, fires, etc.)
    showcase.ts           sample Q&A + chart data for the showcase
    example-queries.ts    example chips + data source names
    clerk-appearance.ts   dark theme for Clerk's modals
    clerk-config.ts       isClerkEnabled flag
  proxy.ts                Clerk middleware (Next 16 renamed middleware → proxy)
```

## Hero videos

Clips are configured in `src/lib/hero-clips.ts`; files go in `public/videos/`. Clips without a
video show a styled placeholder. Target: 1280px-wide H.264 MP4, no audio, 6–10 s, under ~3 MB,
plus a `.webp` poster of the first frame. Only use footage you have rights to.

Search is UI-only for now: `SearchPanel.handleSubmit` is the hook point for the backend call.
