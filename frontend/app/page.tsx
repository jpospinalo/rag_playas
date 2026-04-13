import { Hero } from "@/components/landing/Hero";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { LandingFooter } from "@/components/landing/LandingFooter";
import { LandingNav } from "@/components/landing/LandingNav";
import { WhyRag } from "@/components/landing/WhyRag";

export default function LandingPage() {
  return (
    <>
      <LandingNav />
      <main id="main-content" className="flex flex-1 flex-col">
        <Hero />
        <hr className="mx-auto w-full max-w-5xl border-border px-6" />
        <HowItWorks />
        <hr className="mx-auto w-full max-w-5xl border-border px-6" />
        <WhyRag />
      </main>
      <LandingFooter />
    </>
  );
}
