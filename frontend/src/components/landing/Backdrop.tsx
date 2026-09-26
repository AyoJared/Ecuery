// Decorative background for the hero: a soft top glow over a faded grid.
export function Backdrop() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      <div
        className="absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            "linear-gradient(to right, rgb(214 235 222 / 0.05) 1px, transparent 1px), linear-gradient(to bottom, rgb(214 235 222 / 0.05) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          maskImage: "radial-gradient(ellipse 70% 55% at 50% 30%, black 20%, transparent 75%)",
          WebkitMaskImage: "radial-gradient(ellipse 70% 55% at 50% 30%, black 20%, transparent 75%)",
        }}
      />
      <div className="absolute left-1/2 top-[-18rem] h-[36rem] w-[56rem] max-w-[160vw] -translate-x-1/2 rounded-full bg-[radial-gradient(closest-side,rgb(143_214_165/0.16),transparent)] blur-2xl" />
      <div className="absolute left-1/2 top-[-6rem] h-[18rem] w-[28rem] max-w-[100vw] -translate-x-1/2 rounded-full bg-[radial-gradient(closest-side,rgb(242_192_120/0.08),transparent)] blur-2xl" />
    </div>
  );
}
