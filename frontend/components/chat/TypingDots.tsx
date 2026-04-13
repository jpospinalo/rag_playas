const DELAYS = [0, 200, 400] as const;

export function TypingDots() {
  return (
    <div className="flex items-end gap-[5px] py-0.5" aria-hidden="true">
      {DELAYS.map((delay) => (
        <span
          key={delay}
          className="block h-[7px] w-[7px] rounded-full bg-muted animate-typing-dot"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  );
}
