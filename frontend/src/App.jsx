import { useState, useEffect, useRef, useCallback } from 'react';
import { Mic, Square, Settings, MessageSquare, FileText, Volume2, Send } from 'lucide-react';
import * as api from './services/api';
import { BrowserWebSocket } from './services/websocket';
import { useWebSocket } from './hooks/useWebSocket';
import StatusBadge from './components/StatusBadge';
import ConnectionIndicator from './components/ConnectionIndicator';
import MessageBubble from './components/MessageBubble';
import LionMascot from './components/LionMascot';

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
  const [llmMode, setLlmMode] = useState('local');
  const [messages, setMessages] = useState([]);
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState(null);
  const [newPromptName, setNewPromptName] = useState('');
  const [manualInput, setManualInput] = useState('');
  const [hasAudio, setHasAudio] = useState(false);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioContextRef = useRef(null);
  const mountedRef = useRef(true);
  const audioDataRef = useRef(null);

  const sessionId = useRef(`ts-${Date.now()}`);

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
        if (typeof data.data === 'string') {
          audioDataRef.current = data.data;
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

  const { wsConnected, getWs } = useWebSocket(handleWsMessage, setStatus);

  useEffect(() => {
    async function loadData() {
      try {
        const [promptsData, configData] = await Promise.all([
          api.fetchPrompts(),
          api.fetchConfig(),
        ]);
        setPrompts(promptsData);
        const savedTtsSettings = localStorage.getItem('ttsSettings');
        if (savedTtsSettings) {
          const parsed = JSON.parse(savedTtsSettings);
          setConfig({ ...configData.tts, ...parsed });
        } else {
          setConfig(configData.tts);
        }
        if (configData.llm) {
          setLlmMode(configData.llm.active_chat_llm || 'local');
        }
        if (promptsData.length > 0) {
          setSelectedPrompt(promptsData[0]);
          const content = await api.fetchPrompt(promptsData[0]);
          setPromptContent(content);
        }
      } catch (err) {
        setError(err.message);
      }
    }
    loadData();
  }, []);

  useEffect(() => {
    const handleBeforeUnload = () => {
      const ws = new BrowserWebSocket();
      ws.sendSessionEnd(sessionId.current);
    };
    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      mountedRef.current = false;
      window.removeEventListener('beforeunload', handleBeforeUnload);
      const ws = new BrowserWebSocket();
      ws.sendSessionEnd(sessionId.current);
    };
  }, []);

  const playFullAudio = useCallback(() => {
    const b64 = audioDataRef.current;
    if (!b64) {
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
      if (!audioContextRef.current) {
        audioContextRef.current = new AudioContext();
      }
      audioContextRef.current.decodeAudioData(
        bytes.buffer,
        (buffer) => {
          const source = audioContextRef.current.createBufferSource();
          source.buffer = buffer;
          source.connect(audioContextRef.current.destination);
          source.start();
          source.onended = () => setStatus(STATES.IDLE);
        },
        () => setHasAudio(false)
      );
    } catch {
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
      getWs().sendAudioStart(sessionId.current);
      setStatus(STATES.LISTENING);
    } catch {
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
    const b64Audio = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const base64 = reader.result.split(',')[1];
        resolve(base64);
      };
      reader.onerror = reject;
      reader.readAsDataURL(audioBlob);
    });
    getWs().sendAudioChunk(b64Audio);
    getWs().sendAudioEnd();
  };

  const handleCancel = () => {
    getWs().sendCancel();
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
    if (!/^[a-zA-Z0-9_-]+$/.test(newPromptName.trim())) {
      setError('Name can only contain letters, numbers, underscores, and dashes.');
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

  const handleLlmModeChange = async (mode) => {
    setLlmMode(mode);
    try {
      await api.updateConfig({ active_chat_llm: mode });
    } catch (err) {
      setError(err.message);
    }
  };

  const handleConfigChange = async (key, value) => {
    const newConfig = { ...config, [key]: value };
    setConfig(newConfig);
    try {
      await api.updateConfig(newConfig);
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
    getWs().sendTextInput(text, promptContent, sessionId.current);
  };

  return (
    <div className="min-h-screen font-body text-ac-brown p-6">
      {/* Header */}
      <header className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          {/* House icon with leaf */}
          <div className="relative animate-float">
            <div className="w-14 h-14 bg-ac-leaf/15 border-2 border-ac-leaf/30 rounded-3xl flex items-center justify-center shadow-ac-soft">
              <span className="text-2xl">🏠</span>
            </div>
            <span className="absolute -top-1 -right-1 text-lg animate-leaf-fall">🍃</span>
          </div>
          <div>
            <h1 className="font-display text-2xl font-semibold tracking-tight text-ac-brown-dark">
              岛民小助手
            </h1>
            <p className="text-sm text-ac-brown-light flex items-center gap-1">
              <span className="text-ac-leaf">✦</span> 动森风格语音对话
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <StatusBadge status={status} />
          <ConnectionIndicator connected={wsConnected} />
        </div>
      </header>

      {/* Error Banner */}
      {error && (
        <div className="mb-6 p-4 bg-ac-peach/40 border-2 border-ac-error/40 rounded-2xl text-ac-brown-dark text-sm font-body font-semibold animate-pop-in flex items-center gap-2">
          <span className="text-lg">😿</span>
          <span>{error}</span>
        </div>
      )}

      {/* Main Grid */}
      <div className="grid grid-cols-12 gap-5">
        {/* Left Panel */}
        <div className="col-span-3 space-y-5">
          {/* Prompts Panel */}
          <div className="panel panel-leaf">
            <div className="flex items-center gap-2 mb-4">
              <span className="text-lg">📝</span>
              <h2 className="text-sm font-display font-semibold text-ac-brown-dark uppercase tracking-wide">
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
              <button onClick={handleCreatePrompt} className="btn-primary text-sm px-4 py-2">
                +
              </button>
            </div>

            <select
              value={selectedPrompt}
              onChange={(e) => handlePromptChange(e.target.value)}
              className="input-field mb-4"
            >
              {prompts.map((prompt) => (
                <option key={prompt} value={prompt}>{prompt}</option>
              ))}
            </select>

            <textarea
              value={promptContent}
              onChange={(e) => setPromptContent(e.target.value)}
              className="input-field h-44 resize-none mb-4"
              placeholder="Write your prompt here..."
            />

            <button onClick={handleSavePrompt} className="btn-primary w-full text-sm mb-2">
              <span className="mr-1">💾</span> Save
            </button>
            <button onClick={handleDeletePrompt} className="btn-danger w-full text-sm">
              <span className="mr-1">🗑️</span> Delete
            </button>
          </div>

          {/* TTS Settings */}
          <div className="panel">
            <div className="flex items-center gap-2 mb-4">
              <span className="text-lg">🎵</span>
              <h2 className="text-sm font-display font-semibold text-ac-brown-dark uppercase tracking-wide">
                Voice Settings
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
                  <option value="zh-CN-YunxiaNeural">☁️ Yunxia</option>
                  <option value="zh-CN-XiaoxiaoNeural">🌟 Xiaoxiao</option>
                  <option value="zh-CN-YunyangNeural">☀️ Yunyang</option>
                </select>
              </div>

              <div>
                <label className="label">Speed: {config.rate}</label>
                <input
                  type="range"
                  min="-50"
                  max="50"
                  value={parseInt(config.rate) || 0}
                  onChange={(e) => handleConfigChange('rate', `${e.target.value}%`)}
                  className="w-full accent-ac-leaf h-2 rounded-full"
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
                  className="w-full accent-ac-gold h-2 rounded-full"
                />
              </div>

              <div className="pt-4 border-t-2 border-ac-tan-light">
                <label className="label mb-3">AI 模型</label>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleLlmModeChange('local')}
                    className={`flex-1 py-2.5 px-3 rounded-2xl border-2 text-sm font-body font-bold transition-all ${
                      llmMode === 'local'
                        ? 'bg-ac-leaf/15 border-ac-leaf text-ac-leaf-dark shadow-ac-soft'
                        : 'bg-white border-ac-tan-light text-ac-brown-light hover:border-ac-tan'
                    }`}
                  >
                    <span className="block text-lg mb-0.5">🏠</span>
                    本地
                  </button>
                  <button
                    onClick={() => handleLlmModeChange('online')}
                    className={`flex-1 py-2.5 px-3 rounded-2xl border-2 text-sm font-body font-bold transition-all ${
                      llmMode === 'online'
                        ? 'bg-ac-sky/15 border-ac-sky text-ac-sky shadow-ac-soft'
                        : 'bg-white border-ac-tan-light text-ac-brown-light hover:border-ac-tan'
                    }`}
                  >
                    <span className="block text-lg mb-0.5">☁️</span>
                    DeepSeek
                  </button>
                </div>
                <p className="text-[10px] text-ac-tan mt-2 text-center">
                  {llmMode === 'online' ? '对话用 DeepSeek，记忆保持本地' : '全部使用本地模型'}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Middle Panel - Chat */}
        <div className="col-span-6">
          <div className="panel h-[calc(100vh-200px)] flex flex-col" style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg width='60' height='60' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M30 5 Q35 0 40 5 Q45 0 50 5 Q55 10 50 15 L30 15 L10 15 Q5 10 10 5 Q15 0 20 5 Q25 0 30 5Z' fill='%237BC47F' opacity='0.04'/%3E%3C/svg%3E")`,
            backgroundRepeat: 'repeat',
          }}>
            <div className="flex items-center gap-2 mb-4 pb-4 border-b-2 border-ac-tan-light">
              <span className="text-lg">💬</span>
              <h2 className="text-sm font-display font-semibold text-ac-brown-dark uppercase tracking-wide">
                Chat
              </h2>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto space-y-4 mb-4 pr-1">
              {messages.length === 0 && (
                <div className="text-center py-16 space-y-3">
                  <div className="text-5xl animate-float">🏝️</div>
                  <p className="text-ac-brown-light font-body font-semibold">
                    来聊天吧！
                  </p>
                  <p className="text-xs text-ac-tan">
                    打字或按话筒按钮开始对话
                  </p>
                </div>
              )}

              {messages.map((message, index) => (
                <MessageBubble key={index} message={message} />
              ))}
            </div>

            {/* Text Input */}
            <div className="flex gap-2 mb-3">
              <input
                type="text"
                value={manualInput}
                onChange={(e) => setManualInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSendManualInput()}
                className="input-field flex-1"
                placeholder="想说点什么？"
                disabled={status !== STATES.IDLE}
              />
              <button
                onClick={handleSendManualInput}
                disabled={status !== STATES.IDLE || !manualInput.trim()}
                className="btn-primary p-3 rounded-2xl disabled:opacity-40"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>

            {/* Microphone */}
            <div className="pt-4 border-t-2 border-ac-tan-light">
              <div className="flex items-center justify-center gap-8">
                {isRecording ? (
                  <button onClick={stopRecording} className="relative group">
                    <div className="w-20 h-20 bg-ac-error/15 border-2 border-ac-error/50 rounded-full flex items-center justify-center shadow-ac-button transition-all group-hover:scale-105 group-hover:bg-ac-error/25">
                      <Square className="w-8 h-8 text-ac-error fill-ac-error/30" />
                    </div>
                    <span className="absolute -bottom-8 left-1/2 -translate-x-1/2 text-xs font-body font-bold text-ac-error whitespace-nowrap">
                      STOP
                    </span>
                  </button>
                ) : (
                  <button
                    onClick={startRecording}
                    disabled={status !== STATES.IDLE}
                    className="relative group"
                  >
                    <div className="w-20 h-20 bg-ac-leaf/15 border-2 border-ac-leaf/40 rounded-full flex items-center justify-center shadow-ac-button transition-all group-hover:scale-110 group-hover:bg-ac-leaf/25 disabled:opacity-40 disabled:cursor-not-allowed">
                      <Mic className="w-8 h-8 text-ac-leaf-dark" />
                    </div>
                    <span className="absolute -bottom-8 left-1/2 -translate-x-1/2 text-xs font-body font-bold text-ac-leaf-dark whitespace-nowrap">
                      TALK
                    </span>
                  </button>
                )}

                {(status === STATES.PROCESSING || status === STATES.SPEAKING) && (
                  <button onClick={handleCancel} className="relative group">
                    <div className="w-16 h-16 bg-ac-tan/20 border-2 border-ac-tan rounded-full flex items-center justify-center transition-all group-hover:scale-105">
                      <Square className="w-6 h-6 text-ac-brown-light" />
                    </div>
                    <span className="absolute -bottom-8 left-1/2 -translate-x-1/2 text-xs font-body font-semibold text-ac-brown-light whitespace-nowrap">
                      CANCEL
                    </span>
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Right Panel */}
        <div className="col-span-3 space-y-5">
          {/* Status Panel */}
          <div className="panel">
            <div className="flex items-center gap-2 mb-4">
              <span className="text-lg">📊</span>
              <h2 className="text-sm font-display font-semibold text-ac-brown-dark uppercase tracking-wide">
                Status
              </h2>
            </div>

            <div className="space-y-3 text-sm font-body">
              <div className="flex justify-between items-center py-1.5 px-3 rounded-xl bg-ac-warm/50">
                <span className="text-ac-brown-light font-semibold text-xs">State</span>
                <span className={`font-bold text-xs ${
                  status === STATES.IDLE ? 'text-ac-idle' :
                  status === STATES.LISTENING ? 'text-ac-active' :
                  status === STATES.PROCESSING ? 'text-ac-amber' :
                  'text-ac-sky'
                }`}>
                  {status.toUpperCase()}
                </span>
              </div>
              <div className="flex justify-between items-center py-1.5 px-3 rounded-xl bg-ac-warm/50">
                <span className="text-ac-brown-light font-semibold text-xs">Session</span>
                <span className="text-ac-tan font-mono text-[10px] truncate max-w-[130px]">{sessionId.current}</span>
              </div>
              <div className="flex justify-between items-center py-1.5 px-3 rounded-xl bg-ac-warm/50">
                <span className="text-ac-brown-light font-semibold text-xs">Messages</span>
                <span className="font-bold text-ac-leaf-dark">{messages.length}</span>
              </div>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="panel">
            <h3 className="text-xs font-display text-ac-brown-light uppercase tracking-wide mb-3">
              Actions
            </h3>
            <div className="space-y-2">
              <button
                onClick={playFullAudio}
                disabled={!hasAudio}
                className="w-full py-2.5 px-4 bg-ac-sky-light/50 border-2 border-ac-sky/30 rounded-2xl text-sm font-body font-bold text-ac-brown hover:bg-ac-sky-light hover:-translate-y-0.5 hover:shadow-ac-hover transition-all disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:translate-y-0 flex items-center justify-center gap-2"
              >
                <span>🔊</span> Play Audio
              </button>
              <button
                onClick={() => setMessages([])}
                className="btn-ghost w-full text-sm flex items-center justify-center gap-2"
              >
                <span>🧹</span> Clear Chat
              </button>
              <button
                onClick={() => window.location.reload()}
                className="btn-ghost w-full text-sm flex items-center justify-center gap-2"
              >
                <span>🔄</span> Reload
              </button>
            </div>
          </div>

          {/* Tip Card */}
          <div className="panel bg-gradient-to-br from-ac-mint/20 via-ac-card to-ac-peach/20 border-ac-leaf/20">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-lg">💡</span>
              <h3 className="text-xs font-display font-semibold text-ac-leaf-dark uppercase tracking-wide">
                Tip
              </h3>
            </div>
            <p className="text-xs text-ac-brown-light leading-relaxed">
              Press the microphone button to talk, release to send your message.
              You can also type messages in the text box below. 🍃
            </p>
          </div>
        </div>
      </div>

      {/* Lion Mascot */}
      <LionMascot />
    </div>
  );
}

export default App;
