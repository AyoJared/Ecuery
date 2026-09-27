import { Show, SignInButton, SignUpButton, UserButton } from "@clerk/nextjs";
import { isClerkEnabled } from "@/lib/clerk-config";

const secondaryButton =
  "rounded-full px-3.5 py-1.5 text-sm text-ink-muted transition-colors hover:text-ink";
const primaryButton =
  "rounded-full bg-sun px-4 py-1.5 text-sm font-medium text-canvas transition-colors hover:bg-sun-soft";

export function AuthButtons() {
  if (!isClerkEnabled) {
    // Same look, inert, so the layout is identical before keys are added.
    return (
      <>
        <button className={secondaryButton} title="Add Clerk keys to .env.local to enable">
          Sign in
        </button>
        <button className={primaryButton} title="Add Clerk keys to .env.local to enable">
          Get started
        </button>
      </>
    );
  }

  return (
    <>
      <Show when="signed-out">
        <SignInButton mode="modal">
          <button className={secondaryButton}>Sign in</button>
        </SignInButton>
        <SignUpButton mode="modal">
          <button className={primaryButton}>Get started</button>
        </SignUpButton>
      </Show>
      <Show when="signed-in">
        <UserButton />
      </Show>
    </>
  );
}
