export default function MessageBubble({ message }) {
  const isUser = message.role === 'user';

  return (
    <div className={`animate-pop-in ${isUser ? 'flex justify-end' : ''}`}>
      <div
        className={`bubble-${isUser ? 'user' : 'assistant'} max-w-[80%] px-5 py-3 ${
          isUser
            ? 'rounded-bubble rounded-tr-md bg-[#E8F5E9] border-2 border-ac-leaf/30 text-ac-brown-dark shadow-sm'
            : 'rounded-bubble rounded-tl-md bg-[#FFF3E0] border-2 border-ac-gold/20 text-ac-brown-dark shadow-sm'
        }`}
      >
        <span className="text-xs font-body font-bold uppercase tracking-wide mb-1 block"
          style={{ color: isUser ? '#5EA862' : '#E8A838' }}>
          {isUser ? '你' : '肚肚'}
        </span>
        <span className="font-body text-sm leading-relaxed whitespace-pre-wrap">
          {message.text}
        </span>
        {!message.complete && !isUser && (
          <span className="inline-flex gap-1 ml-1">
            <span className="w-1.5 h-1.5 rounded-full bg-ac-amber animate-bounce" style={{ animationDelay: '0ms' }} />
            <span className="w-1.5 h-1.5 rounded-full bg-ac-amber animate-bounce" style={{ animationDelay: '150ms' }} />
            <span className="w-1.5 h-1.5 rounded-full bg-ac-amber animate-bounce" style={{ animationDelay: '300ms' }} />
          </span>
        )}
      </div>
    </div>
  );
}
