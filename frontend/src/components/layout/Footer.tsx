export function Footer() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-4 py-6 text-xs text-ink-faint sm:flex-row sm:px-6">
        <p>© {new Date().getFullYear()} Ecuery</p>
        <p>Answers are generated from public environmental datasets.</p>
      </div>
    </footer>
  );
}
