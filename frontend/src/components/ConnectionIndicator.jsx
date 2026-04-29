export default function ConnectionIndicator({ connected }) {
  return (
    <div className={`flex items-center gap-2 px-4 py-2 rounded-full border-2 text-sm font-body font-semibold transition-colors duration-300 ${
      connected
        ? 'bg-ac-mint/30 text-ac-leaf-dark border-ac-leaf/40'
        : 'bg-ac-peach/30 text-ac-brown-light border-ac-tan'
    }`}>
      <span className={`w-2.5 h-2.5 rounded-full transition-colors duration-300 ${
        connected ? 'bg-ac-leaf animate-bounce-soft' : 'bg-ac-idle'
      }`} />
      {connected ? '已连接' : '离线中'}
    </div>
  );
}
