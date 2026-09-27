import { AssistantButton } from "@/components/assistant/AssistantButton";
import { Logo } from "./Logo";
import { SectionNavLinks, SectionNavMenu } from "./SectionNav";

export function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-canvas/70 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <Logo />
        <SectionNavLinks />
        <div className="flex items-center gap-2">
          <AssistantButton />
          <SectionNavMenu />
        </div>
      </div>
    </header>
  );
}
