interface UserBubbleProps {
  text: string;
}

export function UserBubble({ text }: UserBubbleProps) {
  return (
    <div className="flex justify-end animate-message-in">
      <div className="max-w-[68%] min-w-0 break-words rounded-2xl rounded-tr-sm bg-navy px-4 py-3 text-sm leading-relaxed text-white shadow-sm">
        {text}
      </div>
    </div>
  );
}
