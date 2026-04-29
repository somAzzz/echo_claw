export default function StatusBadge({ status }) {
  const styles = {
    idle: 'bg-ac-idle/20 text-ac-idle border-ac-idle/30',
    listening: 'bg-ac-active/20 text-ac-active border-ac-active/40',
    processing: 'bg-ac-processing/20 text-ac-amber border-ac-processing/40',
    speaking: 'bg-ac-sky/20 text-ac-sky border-ac-sky/40',
  };

  return (
    <div className={`px-5 py-2 rounded-full border-2 text-sm font-body font-bold tracking-wide flex items-center gap-2 transition-colors duration-300 ${styles[status] || styles.idle}`}>
      <span className={`w-2.5 h-2.5 rounded-full ${status !== 'idle' ? 'animate-bounce-soft' : ''}`}
        style={{ backgroundColor: 'currentColor' }} />
      {status.toUpperCase()}
    </div>
  );
}
