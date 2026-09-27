import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Providers } from "@/components/Providers";
import { Footer } from "@/components/layout/Footer";
import { Header } from "@/components/layout/Header";
import { ResultsExperience } from "@/components/results/ResultsExperience";

async function readQuestion(searchParams: PageProps<"/search">["searchParams"]) {
  const { q } = await searchParams;
  return (Array.isArray(q) ? q[0] : q)?.trim().slice(0, 500) ?? "";
}

export async function generateMetadata({ searchParams }: PageProps<"/search">): Promise<Metadata> {
  const question = await readQuestion(searchParams);
  return { title: question ? `${question} · Ecuery` : "Search · Ecuery" };
}

export default async function SearchPage({ searchParams }: PageProps<"/search">) {
  const question = await readQuestion(searchParams);
  if (!question) redirect("/#ask");

  return (
    <Providers>
      <Header />
      <main className="flex flex-1 flex-col">
        {/* Keyed by the question so a new search starts a fresh conversation */}
        <ResultsExperience key={question} question={question} />
      </main>
      <Footer />
    </Providers>
  );
}
