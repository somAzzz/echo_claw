import { useState, useEffect, useRef, useCallback } from 'react';
import { Mic, MicOff, Square, Settings, MessageSquare, FileText, Zap, Volume2, Send, Trash2 } from 'lucide-react';
import * as api from './services/api';
import { connect, sendAudioStart, sendAudioEnd, sendCancel, disconnect, sendTextInput } from './services/websocket';

const STATES = {
  IDLE: 'idle',
  LISTENING: 'listening',
  PROCESSING: 'processing',
  SPEAKING: 'speaking',
};

function App() {
  const [status, setStatus] = useState(STATES.IDLE);
  const [prompts, setPrompts] = useState([]);
  const [selectedPrompt, setSelectedPrompt] = useState('');
  const [promptContent, setPromptContent] = useState('');
  const [config, setConfig] = useState({ voice: '', rate: '', pitch: '', volume: '' });
  const [messages, setMessages] = useState([]);
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [newPromptName, setNewPromptName] = useState('');
  const [manualInput, setManualInput] = useState('');
  const [hasAudio, setHasAudio] = useState(false);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioContextRef = useRef(null);
  const mountedRef = useRef(true);
  const audioDataRef = useRef(null);  // Complete audio data for non-streaming playback

  const sessionId = useRef(`session-${Date.now()}`);

  // Load initial data
  useEffect(() => {
    async function loadData() {
      try {
        const [promptsData, configData] = await Promise.all([
          api.fetchPrompts(),
          api.fetchConfig(),
        ]);
        setPrompts(promptsData);
        // Merge server config with localStorage overrides (localStorage takes precedence)
        const savedTtsSettings = localStorage.getItem('ttsSettings');
        if (savedTtsSettings) {
          const parsed = JSON.parse(savedTtsSettings);
          setConfig({
            ...configData.tts,
            ...parsed,
          });
        } else {
          setConfig(configData.tts);
        }
        if (promptsData.length > 0) {
          setSelectedPrompt(promptsData[0]);
          // Fetch content for first prompt
          const content = await api.fetchPrompt(promptsData[0]);
          setPromptContent(content);
        }
      } catch (err) {
        setError(err.message);
      }
    }
    loadData();
  }, []);

  // Connect WebSocket
  useEffect(() => {
    async function initWs() {
      try {
        await connect(
          (data) => {
            if (!mountedRef.current) return;
            handleWsMessage(data);
          },
          (state) => {
            if (!mountedRef.current) return;
            setStatus(state);
          }
        );
        if (mountedRef.current) setWsConnected(true);
      } catch (err) {
        if (mountedRef.current) setError('Failed to connect to voice service');
      }
    }

    initWs();

    return () => {
      mountedRef.current = false;
      disconnect();
    };
  }, []);

  const handleWsMessage = useCallback((data) => {
    switch (data.type) {
      case 'text':
        setMessages((prev) => [
          ...prev,
          { role: 'user', text: data.text, time: new Date() },
        ]);
        break;
      case 'llm_chunk':
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.role === 'assistant' && !last.complete) {
            return [
              ...prev.slice(0, -1),
              { ...last, text: last.text + data.text },
            ];
          }
          return [
            ...prev,
            { role: 'assistant', text: data.text, time: new Date(), complete: false },
          ];
        });
        break;
      case 'tts_complete':
        // Complete audio data received (non-streaming mode)
        if (typeof data.data === 'string') {
          audioDataRef.current = data.data;
          console.log('[Audio] Received tts_complete, length:', data.data.length, 'first 20 chars:', data.data.substring(0, 20));
        } else {
          console.log('[Audio] Received tts_complete with non-string data, type:', typeof data.data);
        }
        setHasAudio(true);
        setStatus(STATES.IDLE);
        setMessages((prev) =>
          prev.map((m, i) =>
            i === prev.length - 1 && m.role === 'assistant' ? { ...m, complete: true } : m
          )
        );
        break;
      case 'state':
        if (data.state === 'idle') {
          setStatus(STATES.IDLE);
          setIsRecording(false);
        }
        break;
      case 'error':
        setError(data.message);
        setStatus(STATES.IDLE);
        break;
    }
  }, []);

  const playFullAudio = useCallback(() => {
    const b64 = audioDataRef.current;
    if (!b64) {
      console.log('[Audio] No audio to play');
      setHasAudio(false);
      return;
    }

    audioDataRef.current = null;
    setHasAudio(false);

    try {
      const binaryString = atob(b64);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // Create AudioContext if needed
      if (!audioContextRef.current) {
        audioContextRef.current = new AudioContext();
      }

      audioContextRef.current.decodeAudioData(
        bytes.buffer,
        (buffer) => {
          console.log('[Audio] Audio decoded successfully, duration:', buffer.duration);
          const source = audioContextRef.current.createBufferSource();
          source.buffer = buffer;
          source.connect(audioContextRef.current.destination);
          source.start();
          source.onended = () => {
            setStatus(STATES.IDLE);
          };
        },
        (err) => {
          console.error('[Audio] decode error:', err);
          setHasAudio(false);
        }
      );
    } catch (err) {
      console.error('[Audio] Playback error:', err.message);
      setHasAudio(false);
    }
  }, []);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        await sendAudio();
      };

      mediaRecorder.start(100);
      setIsRecording(true);
      setError(null);
      sendAudioStart(sessionId.current);
      setStatus(STATES.LISTENING);
    } catch (err) {
      setError('Microphone access denied. Please enable microphone permissions.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      setStatus(STATES.PROCESSING);
    }
  };

  const sendAudio = async () => {
    if (audioChunksRef.current.length === 0) return;

    const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
    const arrayBuffer = await audioBlob.arrayBuffer();

    // Convert to base64
    const bytes = new Uint8Array(arrayBuffer);
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    const b64Audio = btoa(binary);

    // For simplicity, we'll send as text chunks since the server expects base64
    // In a real implementation, you'd use the audio_chunk message type
    sendAudioEnd();
  };

  const handleCancel = () => {
    sendCancel();
    setIsRecording(false);
    setStatus(STATES.IDLE);
    audioDataRef.current = null;
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
    }
  };

  const handlePromptChange = async (name) => {
    setSelectedPrompt(name);
    try {
      const content = await api.fetchPrompt(name);
      setPromptContent(content);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleSavePrompt = async () => {
    try {
      await api.updatePrompt(selectedPrompt, promptContent);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleCreatePrompt = async () => {
    if (!newPromptName.trim()) return;
    // Validate: only alphanumeric, dash, underscore allowed
    if (!/^[a-zA-Z0-9_-]+$/.test(newPromptName.trim())) {
      setError('名字只能包含字母、数字、下划线和短横线');
      return;
    }
    try {
      await api.createPrompt(newPromptName.trim(), '');
      setNewPromptName('');
      const updatedPrompts = await api.fetchPrompts();
      setPrompts(updatedPrompts);
      if (updatedPrompts.length > 0) {
        setSelectedPrompt(updatedPrompts[updatedPrompts.length - 1]);
      }
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDeletePrompt = async () => {
    if (!selectedPrompt) return;
    try {
      await api.deletePrompt(selectedPrompt);
      const updatedPrompts = await api.fetchPrompts();
      setPrompts(updatedPrompts);
      if (updatedPrompts.length > 0) {
        setSelectedPrompt(updatedPrompts[0]);
        const content = await api.fetchPrompt(updatedPrompts[0]);
        setPromptContent(content);
      } else {
        setSelectedPrompt('');
        setPromptContent('');
      }
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleConfigChange = async (key, value) => {
    const newConfig = { ...config, [key]: value };
    setConfig(newConfig);
    try {
      await api.updateConfig(newConfig);
      // Save TTS settings to localStorage for persistence
      if (['voice', 'rate', 'pitch', 'volume'].includes(key)) {
        localStorage.setItem('ttsSettings', JSON.stringify(newConfig));
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const handleSendManualInput = async () => {
    if (!manualInput.trim() || status !== STATES.IDLE) return;
    const text = manualInput.trim();
    setManualInput('');
    setStatus(STATES.PROCESSING);
    sendTextInput(text, promptContent);
  };

  return (
    <div className="min-h-screen bg-dark-bg text-gray-200 p-6">
      {/* Header */}
      <header className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <div className="relative">
            <Zap className="w-10 h-10 text-neon-cyan animate-pulse" />
            <div className="absolute inset-0 w-10 h-10 bg-neon-cyan/20 rounded-full blur-xl animate-pulse-slow" />
          </div>
          <div>
            <h1 className="font-display text-2xl font-bold tracking-wider text-neon-cyan">
              VOICE ASSISTANT HUB
            </h1>
            <p className="text-xs text-gray-500 font-mono">v1.0 // SYSTEM ONLINE</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <StatusBadge status={status} />
          <ConnectionIndicator connected={wsConnected} />
        </div>
      </header>

      {error && (
        <div className="mb-6 p-4 bg-red-500/10 border border-red-500/50 rounded-lg text-red-400 font-mono text-sm animate-slide-up">
          <span className="text-red-500">ERROR: </span>
          {error}
        </div>
      )}

      {/* Main Grid */}
      <div className="grid grid-cols-12 gap-6">
        {/* Left Panel - Prompts */}
        <div className="col-span-3 space-y-6">
          <div className="panel">
            <div className="flex items-center gap-2 mb-4">
              <FileText className="w-4 h-4 text-neon-purple" />
              <h2 className="text-sm font-mono font-semibold text-gray-300 uppercase tracking-wider">
                System Prompts
              </h2>
            </div>

            <div className="flex gap-2 mb-4">
              <input
                type="text"
                value={newPromptName}
                onChange={(e) => setNewPromptName(e.target.value)}
                className="input-field flex-1"
                placeholder="New prompt name..."
              />
              <button
                onClick={handleCreatePrompt}
                className="px-4 py-2 bg-neon-purple/20 border border-neon-purple/50 text-neon-purple font-mono text-sm rounded-lg hover:bg-neon-purple/30 transition-colors"
              >
                ADD
              </button>
            </div>

            <select
              value={selectedPrompt}
              onChange={(e) => handlePromptChange(e.target.value)}
              className="input-field mb-4"
            >
              {prompts.map((prompt) => (
                <option key={prompt} value={prompt}>
                  {prompt}
                </option>
              ))}
            </select>

            <textarea
              value={promptContent}
              onChange={(e) => setPromptContent(e.target.value)}
              className="input-field h-48 resize-none mb-4"
              placeholder="Prompt content..."
            />

            <button onClick={handleSavePrompt} className="btn-primary w-full text-sm mb-2">
              SAVE PROMPT
            </button>
            <button onClick={handleDeletePrompt} className="w-full py-2 px-4 bg-red-500/10 border border-red-500/30 text-red-400 font-mono text-sm rounded-lg hover:bg-red-500/20 transition-colors">
              DELETE PROMPT
            </button>
          </div>

          {/* Settings Panel */}
          <div className="panel">
            <div className="flex items-center gap-2 mb-4">
              <Settings className="w-4 h-4 text-neon-purple" />
              <h2 className="text-sm font-mono font-semibold text-gray-300 uppercase tracking-wider">
                TTS Settings
              </h2>
            </div>

            <div className="space-y-4">
              <div>
                <label className="label">Voice</label>
                <select
                  value={config.voice}
                  onChange={(e) => handleConfigChange('voice', e.target.value)}
                  className="input-field"
                >
                  <option value="zh-CN-YunxiaNeural">zh-CN-YunxiaNeural</option>
                  <option value="zh-CN-XiaoxiaoNeural">zh-CN-XiaoxiaoNeural</option>
                  <option value="zh-CN-YunyangNeural">zh-CN-YunyangNeural</option>
                </select>
              </div>

              <div>
                <label className="label">Rate: {config.rate}</label>
                <input
                  type="range"
                  min="-50"
                  max="50"
                  value={parseInt(config.rate) || 0}
                  onChange={(e) => handleConfigChange('rate', `${e.target.value}%`)}
                  className="w-full accent-neon-cyan"
                />
              </div>

              <div>
                <label className="label">Pitch: {config.pitch}</label>
                <input
                  type="range"
                  min="-50"
                  max="50"
                  value={parseInt(config.pitch) || 0}
                  onChange={(e) => handleConfigChange('pitch', `${e.target.value}Hz`)}
                  className="w-full accent-neon-purple"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Middle Panel - Chat */}
        <div className="col-span-6">
          <div className="panel h-[calc(100vh-220px)] flex flex-col">
            <div className="flex items-center gap-2 mb-4 pb-4 border-b border-dark-border">
              <MessageSquare className="w-4 h-4 text-neon-green" />
              <h2 className="text-sm font-mono font-semibold text-gray-300 uppercase tracking-wider">
                Conversation
              </h2>
            </div>

            <div className="flex-1 overflow-y-auto space-y-4 mb-4 pr-2">
              {messages.length === 0 && (
                <div className="text-center text-gray-500 font-mono text-sm py-12">
                  <p>// Awaiting input...</p>
                  <p className="text-xs mt-2">Press the microphone and start speaking</p>
                </div>
              )}

              {messages.map((message, index) => (
                <div
                  key={index}
                  className={`animate-slide-up ${
                    message.role === 'user'
                      ? 'text-right'
                      : ''
                  }`}
                >
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
              ))}
            </div>

            {/* Manual Text Input */}
            <div className="flex gap-2 mb-4">
              <input
                type="text"
                value={manualInput}
                onChange={(e) => setManualInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSendManualInput()}
                className="input-field flex-1"
                placeholder="Type a message..."
                disabled={status !== STATES.IDLE}
              />
              <button
                onClick={handleSendManualInput}
                disabled={status !== STATES.IDLE || !manualInput.trim()}
                className="px-4 py-2 bg-neon-cyan/20 border border-neon-cyan/50 text-neon-cyan font-mono text-sm rounded-lg hover:bg-neon-cyan/30 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>

            {/* Microphone Controls */}
            <div className="pt-4 border-t border-dark-border">
              <div className="flex items-center justify-center gap-6">
                {isRecording ? (
                  <button
                    onClick={stopRecording}
                    className="relative group"
                  >
                    <div className="absolute inset-0 bg-red-500/30 rounded-full blur-xl animate-pulse" />
                    <div className="relative w-20 h-20 bg-red-500/20 border-2 border-red-500 rounded-full flex items-center justify-center transition-all group-hover:bg-red-500/30">
                      <Square className="w-8 h-8 text-red-500 fill-red-500" />
                    </div>
                    <span className="absolute -bottom-8 left-1/2 -translate-x-1/2 text-xs font-mono text-red-400 whitespace-nowrap">
                      STOP
                    </span>
                  </button>
                ) : (
                  <button
                    onClick={startRecording}
                    disabled={status !== STATES.IDLE}
                    className="relative group"
                  >
                    <div className="absolute inset-0 bg-neon-cyan/30 rounded-full blur-xl animate-pulse" />
                    <div className="relative w-20 h-20 bg-neon-cyan/10 border-2 border-neon-cyan rounded-full flex items-center justify-center transition-all group-hover:bg-neon-cyan/20 group-hover:scale-110 disabled:opacity-30 disabled:cursor-not-allowed">
                      <Mic className="w-8 h-8 text-neon-cyan" />
                    </div>
                    <span className="absolute -bottom-8 left-1/2 -translate-x-1/2 text-xs font-mono text-neon-cyan whitespace-nowrap">
                      PUSH TO TALK
                    </span>
                  </button>
                )}

                {(status === STATES.PROCESSING || status === STATES.SPEAKING) && (
                  <button
                    onClick={handleCancel}
                    className="relative group"
                  >
                    <div className="relative w-16 h-16 bg-gray-500/10 border-2 border-gray-500 rounded-full flex items-center justify-center transition-all group-hover:bg-gray-500/20">
                      <Square className="w-6 h-6 text-gray-400" />
                    </div>
                    <span className="absolute -bottom-8 left-1/2 -translate-x-1/2 text-xs font-mono text-gray-400 whitespace-nowrap">
                      CANCEL
                    </span>
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Right Panel - Status */}
        <div className="col-span-3 space-y-6">
          <div className="panel">
            <div className="flex items-center gap-2 mb-4">
              <Volume2 className="w-4 h-4 text-neon-green" />
              <h2 className="text-sm font-mono font-semibold text-gray-300 uppercase tracking-wider">
                System Status
              </h2>
            </div>

            <div className="space-y-3 text-xs font-mono">
              <div className="flex justify-between">
                <span className="text-gray-500">STATE</span>
                <span className={`font-semibold ${
                  status === STATES.IDLE ? 'text-gray-400' :
                  status === STATES.LISTENING ? 'text-neon-cyan' :
                  status === STATES.PROCESSING ? 'text-yellow-400' :
                  'text-neon-purple'
                }`}>
                  {status.toUpperCase()}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">SESSION</span>
                <span className="text-gray-400 truncate max-w-[120px]">{sessionId.current}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">MESSAGES</span>
                <span className="text-gray-400">{messages.length}</span>
              </div>
            </div>
          </div>

          <div className="panel">
            <h3 className="text-xs font-mono text-gray-500 uppercase tracking-wider mb-3">
              Quick Actions
            </h3>
            <div className="space-y-2">
              <button
                onClick={playFullAudio}
                disabled={!hasAudio}
                className="w-full py-2 px-4 bg-neon-green/10 border border-neon-green/30 rounded-lg text-xs font-mono text-neon-green hover:bg-neon-green/20 transition-colors disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                <Volume2 className="w-4 h-4" />
                PLAY AUDIO
              </button>
              <button
                onClick={() => setMessages([])}
                className="w-full py-2 px-4 bg-dark-bg border border-dark-border rounded-lg text-xs font-mono text-gray-400 hover:border-gray-500 transition-colors"
              >
                CLEAR CHAT
              </button>
              <button
                onClick={() => window.location.reload()}
                className="w-full py-2 px-4 bg-dark-bg border border-dark-border rounded-lg text-xs font-mono text-gray-400 hover:border-gray-500 transition-colors"
              >
                RELOAD APP
              </button>
            </div>
          </div>

          <div className="panel bg-gradient-to-br from-neon-cyan/5 to-neon-purple/5 border-neon-cyan/20">
            <h3 className="text-xs font-mono text-neon-cyan uppercase tracking-wider mb-2">
              Tip
            </h3>
            <p className="text-xs text-gray-400 font-mono leading-relaxed">
              Press and hold the microphone button while speaking, then release to send your audio.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ status }) {
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

function ConnectionIndicator({ connected }) {
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

export default App;