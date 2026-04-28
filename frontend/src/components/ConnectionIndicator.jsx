export default function ConnectionIndicator({ connected }) {
  return (
    <div className={`flex items-center gap-2 px-3 py-2 rounded-full border text-xs font-mono ${
      connected
        ? 'bg-neon-green/10 text-neon-green border-neon-green/30'
        : 'bg-red-500/10 text-red-400 border-red-500/30'
    }`}>
      <span className={`w-2 h-2 rounded-full ${connected ? 'bg-neon-green' : 'bg-red-400'} animate-pulse`} />
      {connected ? 'CONNECTED' : 'DISCONNECTED'}
    </div>
  );
}
