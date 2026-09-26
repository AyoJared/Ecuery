import { AuthButtons } from "@/components/auth/AuthButtons";
import { Logo } from "./Logo";

export function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-canvas/70 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <Logo />
        <nav className="flex items-center gap-2">
          <AuthButtons />
        </nav>
      </div>
    </header>
  );
}
