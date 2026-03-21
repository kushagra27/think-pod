// Think-Pod Frontend
let sessionId = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let isProcessing = false;

const API = '';  // Same origin

// ─── Session Management ───

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
      body: JSON.stringify({ guest_name: name, topic: topic }),
    });

    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();

    sessionId = data.session_id;

    // Switch to interview screen
    document.getElementById('start-screen').style.display = 'none';
    document.getElementById('interview-screen').style.display = 'flex';

    // Show greeting in transcript
    addTranscript('Chris', data.greeting_text);

    // Play greeting audio
    setStatus('speaking', 'Chris is speaking...');
    await playAudio(data.greeting_audio);
    setStatus('', 'Your turn — hold the button to talk');

    // Enable talk button
    document.getElementById('talk-btn').disabled = false;

    // Request mic permission
    await navigator.mediaDevices.getUserMedia({ audio: true });

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

// ─── Recording ───

async function startRecording() {
  if (isProcessing || isRecording) return;

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
    audioChunks = [];

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.start();
    isRecording = true;
    document.getElementById('talk-btn').classList.add('recording');
    setStatus('listening', '🔴 Recording...');
  } catch (err) {
    console.error('Mic error:', err);
    setStatus('', 'Microphone access denied');
  }
}

async function stopRecording() {
  if (!isRecording || !mediaRecorder) return;

  isRecording = false;
  document.getElementById('talk-btn').classList.remove('recording');

  mediaRecorder.stop();
  mediaRecorder.stream.getTracks().forEach(t => t.stop());

  // Wait for final data
  await new Promise(resolve => {
    mediaRecorder.onstop = resolve;
  });

  if (audioChunks.length === 0) {
    setStatus('', 'No audio recorded');
    return;
  }

  const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
  
  // Minimum recording length check (~0.5s)
  if (audioBlob.size < 5000) {
    setStatus('', 'Recording too short — hold longer');
    return;
  }

  await sendAudio(audioBlob);
}

// ─── API Communication ───

async function sendAudio(audioBlob) {
  if (!sessionId) return;
  
  isProcessing = true;
  document.getElementById('talk-btn').disabled = true;
  setStatus('thinking', 'Chris is thinking...');

  const formData = new FormData();
  formData.append('audio', audioBlob, 'recording.webm');

  try {
    const t0 = Date.now();
    const resp = await fetch(`${API}/api/session/${sessionId}/chat`, {
      method: 'POST',
      body: formData,
    });

    if (!resp.ok) {
      const err = await resp.text();
      throw new Error(err);
    }

    const data = await resp.json();
    const totalMs = Date.now() - t0;

    // Show user's transcribed text
    addTranscript('You', data.user_text);

    // Show Chris's response
    addTranscript('Chris', data.chris_text);

    // Show latency
    document.getElementById('latency').textContent = 
      `STT: ${data.stt_ms}ms | LLM: ${data.llm_ms}ms | TTS: ${data.tts_ms}ms | Total: ${totalMs}ms`;

    // Play Chris's audio
    setStatus('speaking', 'Chris is speaking...');
    await playAudio(data.chris_audio);
    setStatus('', 'Your turn — hold the button to talk');

  } catch (err) {
    console.error('Chat error:', err);
    setStatus('', 'Error: ' + err.message);
  } finally {
    isProcessing = false;
    document.getElementById('talk-btn').disabled = false;
  }
}

// ─── Audio Playback ───

function playAudio(base64Audio) {
  return new Promise((resolve) => {
    const audio = new Audio('data:audio/mp3;base64,' + base64Audio);
    audio.onended = resolve;
    audio.onerror = resolve;
    audio.play().catch(resolve);
  });
}

// ─── UI Helpers ───

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
    <div class="speaker ${isChris ? 'speaker-chris' : 'speaker-user'}">
      ${isChris ? '🎙️' : '🗣️'} ${speaker}
    </div>
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
