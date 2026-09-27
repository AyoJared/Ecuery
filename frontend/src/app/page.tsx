import { Providers } from "@/components/Providers";
import { AskSection } from "@/components/ask/AskSection";
import { VideoHero } from "@/components/hero/VideoHero";
import { ClosingCta } from "@/components/landing/ClosingCta";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { ScrollProgress } from "@/components/landing/ScrollProgress";
import { ScrollStatement } from "@/components/landing/ScrollStatement";
import { StatsBand } from "@/components/landing/StatsBand";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { ShowcaseSection } from "@/components/showcase/ShowcaseSection";

export default function Home() {
  return (
    <Providers>
      <ScrollProgress />
      <Header />
      <main className="flex flex-1 flex-col">
        <VideoHero />
        <ScrollStatement />
        <AskSection />
        <StatsBand />
        <ShowcaseSection />
        <HowItWorks />
        <ClosingCta />
      </main>
      <Footer />
    </Providers>
  );
}
