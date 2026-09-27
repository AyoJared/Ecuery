// Clerk throws on every request when keys are missing. Until .env.local is
// filled in, we skip Clerk entirely so the UI still runs locally.
export const isClerkEnabled = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);
