export default function StatusBadge({ status }) {
  const colors = {
    idle: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
    listening: 'bg-neon-cyan/20 text-neon-cyan border-neon-cyan/30 animate-pulse',
    processing: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30 animate-pulse',
    speaking: 'bg-neon-purple/20 text-neon-purple border-neon-purple/30 animate-pulse',
  };

  return (
    <div className={`px-4 py-2 rounded-full border text-xs font-mono font-semibold ${colors[status] || colors.idle}`}>
      <span className="inline-block w-2 h-2 rounded-full bg-current mr-2 animate-pulse" />
      {status.toUpperCase()}
    </div>
  );
}
