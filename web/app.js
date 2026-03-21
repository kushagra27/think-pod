let sessionId = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let isProcessing = false;
const API = '';

async function startSession() {
  const name = document.getElementById('guest-name').value.trim() || 'Guest';
  const topic = document.getElementById('topic').value.trim() || 'life, ideas, and the future';
  const btn = document.getElementById('start-btn');
  btn.disabled = true;
  btn.textContent = 'Starting...';

  try {
    const resp = await fetch(`${API}/api/session/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ guest_name: name, topic })
    });
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    sessionId = data.session_id;

    document.getElementById('start-screen').style.display = 'none';
    document.getElementById('interview-screen').style.display = 'flex';

    addTranscript('Chris', data.greeting_text);
    setStatus('speaking', 'Chris is speaking...');
    await playAudio(data.greeting_audio);
    setStatus('', 'Your turn — hold the button to talk or type below');

    document.getElementById('talk-btn').disabled = false;
    document.getElementById('send-btn').disabled = false;

    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      await navigator.mediaDevices.getUserMedia({ audio: true });
    } else {
      console.warn('MediaDevices not available — needs HTTPS');
      setStatus('', 'Mic unavailable here — use text box below or open over HTTPS');
    }
  } catch (err) {
    alert('Error starting session: ' + err.message);
    btn.disabled = false;
    btn.textContent = 'Start Interview';
  }
}

async function endSession() {
  if (!sessionId) return;
  try {
    const resp = await fetch(`${API}/api/session/${sessionId}/end`, { method: 'POST' });
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    document.getElementById('interview-screen').style.display = 'none';
    document.getElementById('end-screen').style.display = 'flex';
    document.getElementById('summary').textContent = data.transcript_md;
  } catch (err) {
    alert('Error ending session: ' + err.message);
  }
}

async function startRecording() {
  if (isProcessing || isRecording) return;
  if (!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia)) {
    setStatus('', 'Microphone unavailable — use text box below');
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
    audioChunks = [];
    mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.start();
    isRecording = true;
    document.getElementById('talk-btn').classList.add('recording');
    setStatus('listening', '🔴 Recording...');
  } catch (err) {
    console.error('Mic error:', err);
    setStatus('', 'Microphone access denied — use text box below');
  }
}

async function stopRecording() {
  if (!isRecording || !mediaRecorder) return;
  isRecording = false;
  document.getElementById('talk-btn').classList.remove('recording');
  mediaRecorder.stop();
  mediaRecorder.stream.getTracks().forEach(t => t.stop());
  await new Promise(resolve => { mediaRecorder.onstop = resolve; });
  if (audioChunks.length === 0) {
    setStatus('', 'No audio recorded');
    return;
  }
  const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
  if (audioBlob.size < 5000) {
    setStatus('', 'Recording too short — hold longer');
    return;
  }
  await sendAudio(audioBlob);
}

async function sendAudio(audioBlob) {
  if (!sessionId) return;
  isProcessing = true;
  document.getElementById('talk-btn').disabled = true;
  document.getElementById('send-btn').disabled = true;
  setStatus('thinking', 'Chris is thinking...');

  const formData = new FormData();
  formData.append('audio', audioBlob, 'recording.webm');

  try {
    const t0 = Date.now();
    const resp = await fetch(`${API}/api/session/${sessionId}/chat`, { method: 'POST', body: formData });
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    const totalMs = Date.now() - t0;

    addTranscript('You', data.user_text);
    addTranscript('Chris', data.chris_text);
    document.getElementById('latency').textContent = `STT: ${data.stt_ms}ms | LLM: ${data.llm_ms}ms | TTS: ${data.tts_ms}ms | Total: ${totalMs}ms`;

    setStatus('speaking', 'Chris is speaking...');
    await playAudio(data.chris_audio);
    setStatus('', 'Your turn — hold the button to talk or type below');
  } catch (err) {
    console.error('Chat error:', err);
    setStatus('', 'Error: ' + err.message);
  } finally {
    isProcessing = false;
    document.getElementById('talk-btn').disabled = false;
    document.getElementById('send-btn').disabled = false;
  }
}

async function sendText() {
  if (!sessionId || isProcessing) return;
  const input = document.getElementById('text-input');
  const text = input.value.trim();
  if (!text) return;

  isProcessing = true;
  document.getElementById('talk-btn').disabled = true;
  document.getElementById('send-btn').disabled = true;
  addTranscript('You', text);
  input.value = '';
  setStatus('thinking', 'Chris is thinking...');

  try {
    const t0 = Date.now();
    const resp = await fetch(`${API}/api/session/${sessionId}/chat-text`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    const totalMs = Date.now() - t0;

    removeLastUserEchoIfDuplicated(text, data.user_text);
    addTranscript('Chris', data.chris_text);
    document.getElementById('latency').textContent = `LLM: ${data.llm_ms}ms | TTS: ${data.tts_ms}ms | Total: ${totalMs}ms`;

    setStatus('speaking', 'Chris is speaking...');
    await playAudio(data.chris_audio);
    setStatus('', 'Your turn — hold the button to talk or type below');
  } catch (err) {
    console.error('Text chat error:', err);
    setStatus('', 'Error: ' + err.message);
  } finally {
    isProcessing = false;
    document.getElementById('talk-btn').disabled = false;
    document.getElementById('send-btn').disabled = false;
  }
}

function removeLastUserEchoIfDuplicated(sent, returned) {
  if (sent === returned) return;
}

async function refreshTranscript() {
  if (!sessionId) return;
  try {
    const resp = await fetch(`${API}/api/session/${sessionId}/transcript`);
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    const el = document.getElementById('transcript');
    el.innerHTML = '';
    for (const entry of data.transcript) {
      addTranscript(entry.speaker === 'Chris' ? 'Chris' : entry.speaker, entry.text);
    }
  } catch (err) {
    console.error('Transcript refresh error:', err);
  }
}

function playAudio(base64Audio) {
  return new Promise((resolve) => {
    const audio = new Audio('data:audio/mp3;base64,' + base64Audio);
    audio.onended = resolve;
    audio.onerror = resolve;
    audio.play().catch(resolve);
  });
}

function setStatus(cls, text) {
  const el = document.getElementById('status');
  el.className = 'status' + (cls ? ' ' + cls : '');
  el.textContent = text;
}

function addTranscript(speaker, text) {
  const el = document.getElementById('transcript');
  const entry = document.createElement('div');
  entry.className = 'transcript-entry';
  const isChris = speaker === 'Chris';
  entry.innerHTML = `
    <div class="speaker ${isChris ? 'speaker-chris' : 'speaker-user'}">${isChris ? '🎙️' : '🗣️'} ${escapeHtml(speaker)}</div>
    <div class="text">${escapeHtml(text)}</div>
  `;
  el.appendChild(entry);
  el.scrollTop = el.scrollHeight;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) sendText();
});
