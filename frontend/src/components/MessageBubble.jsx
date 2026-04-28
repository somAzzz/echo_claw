export default function MessageBubble({ message }) {
  return (
    <div className={`animate-slide-up ${message.role === 'user' ? 'text-right' : ''}`}>
      <div
        className={`inline-block max-w-[80%] px-4 py-2 rounded-lg text-sm font-mono ${
          message.role === 'user'
            ? 'bg-neon-cyan/10 border border-neon-cyan/30 text-neon-cyan'
            : 'bg-neon-purple/10 border border-neon-purple/30 text-gray-200'
        }`}
      >
        <span className="text-xs opacity-50 block mb-1">
          {message.role === 'user' ? 'USER' : 'ASSISTANT'}
        </span>
        {message.text}
        {!message.complete && message.role === 'assistant' && (
          <span className="inline-block w-2 h-3 bg-neon-purple ml-1 animate-pulse" />
        )}
      </div>
    </div>
  );
}
