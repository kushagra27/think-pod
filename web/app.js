let sessionId = null;
let selectedPodcaster = null;
let hostName = '';
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let isProcessing = false;

// ─── Init ───
document.addEventListener('DOMContentLoaded', loadPodcasters);

async function loadPodcasters() {
  try {
    const resp = await fetch('/api/podcasters');
    const podcasters = await resp.json();
    const grid = document.getElementById('podcaster-list');
    grid.innerHTML = '';
    for (const p of podcasters) {
      const card = document.createElement('div');
      card.className = 'podcaster-card';
      card.dataset.id = p.id;
      card.innerHTML = `
        <img class="avatar" src="${p.avatar}" alt="${p.name}" onerror="this.style.display='none'">
        <div class="info">
          <strong>${esc(p.name)}${p.voice_cloned ? '<span class="cloned-badge">voice cloned</span>' : ''}</strong>
          <span>${esc(p.show)}</span>
          <div class="desc">${esc(p.description)}</div>
        </div>
      `;
      card.onclick = () => selectPodcaster(p.id, p.name, card);
      grid.appendChild(card);
    }
  } catch (e) {
    document.getElementById('podcaster-list').innerHTML = '<div class="loading">Failed to load podcasters</div>';
  }
}

function selectPodcaster(id, name, card) {
  document.querySelectorAll('.podcaster-card').forEach(c => c.classList.remove('selected'));
  card.classList.add('selected');
  selectedPodcaster = id;
  hostName = name;
  const btn = document.getElementById('start-btn');
  btn.disabled = false;
  btn.textContent = `Start Interview with ${name}`;
}

// ─── Session ───
async function startSession() {
  if (!selectedPodcaster) return;
  const name = document.getElementById('guest-name').value.trim() || 'Guest';
  const topic = document.getElementById('topic').value.trim() || 'life, ideas, and the future';
  const btn = document.getElementById('start-btn');
  btn.disabled = true;
  btn.textContent = 'Starting...';

  try {
    const resp = await fetch('/api/session/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ guest_name: name, topic, podcaster: selectedPodcaster }),
    });
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    sessionId = data.session_id;

    // Update interview screen header
    const avatarEl = document.querySelector(`.podcaster-card.selected .avatar`);
    if (avatarEl) document.getElementById('host-avatar').src = avatarEl.src;
    document.getElementById('host-title').textContent = `🎙️ ${data.podcaster_name}`;

    document.getElementById('start-screen').style.display = 'none';
    document.getElementById('interview-screen').style.display = 'flex';

    addTranscript(hostName, data.greeting_text, true);
    setStatus('speaking', `${hostName} is speaking...`);
    await playAudio(data.greeting_audio);
    setStatus('', 'Your turn — hold the button to talk or type below');

    document.getElementById('talk-btn').disabled = false;
    document.getElementById('send-btn').disabled = false;

    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      try { await navigator.mediaDevices.getUserMedia({ audio: true }); }
      catch (e) { setStatus('', 'Mic unavailable — use text box below'); }
    } else {
      setStatus('', 'Mic unavailable (needs HTTPS) — use text box below');
    }
  } catch (err) {
    alert('Error starting session: ' + err.message);
    btn.disabled = false;
    btn.textContent = `Start Interview with ${hostName}`;
  }
}

async function endSession() {
  if (!sessionId) return;
  try {
    const resp = await fetch(`/api/session/${sessionId}/end`, { method: 'POST' });
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
  if (audioChunks.length === 0) return;
  const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
  if (audioBlob.size < 5000) { setStatus('', 'Recording too short'); return; }
  await sendAudio(audioBlob);
}

// ─── Send ───
async function sendAudio(audioBlob) {
  if (!sessionId) return;
  setProcessing(true);
  setStatus('thinking', `${hostName} is thinking...`);
  const formData = new FormData();
  formData.append('audio', audioBlob, 'recording.webm');
  try {
    const t0 = Date.now();
    const resp = await fetch(`/api/session/${sessionId}/chat`, { method: 'POST', body: formData });
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    showResponse(data, Date.now() - t0);
  } catch (err) {
    setStatus('', 'Error: ' + err.message);
  } finally {
    setProcessing(false);
  }
}

async function sendText() {
  if (!sessionId || isProcessing) return;
  const input = document.getElementById('text-input');
  const text = input.value.trim();
  if (!text) return;
  setProcessing(true);
  addTranscript('You', text, false);
  input.value = '';
  setStatus('thinking', `${hostName} is thinking...`);
  try {
    const t0 = Date.now();
    const resp = await fetch(`/api/session/${sessionId}/chat-text`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    showResponse(data, Date.now() - t0, true);
  } catch (err) {
    setStatus('', 'Error: ' + err.message);
  } finally {
    setProcessing(false);
  }
}

async function showResponse(data, totalMs, skipUser = false) {
  if (!skipUser) addTranscript('You', data.user_text, false);
  addTranscript(hostName, data.chris_text, true);
  const parts = [];
  if (data.stt_ms) parts.push(`STT: ${data.stt_ms}ms`);
  parts.push(`LLM: ${data.llm_ms}ms`, `TTS: ${data.tts_ms}ms`, `Total: ${totalMs}ms`);
  document.getElementById('latency').textContent = parts.join(' | ');
  setStatus('speaking', `${hostName} is speaking...`);
  await playAudio(data.chris_audio);
  setStatus('', 'Your turn — hold the button to talk or type below');
}

function setProcessing(val) {
  isProcessing = val;
  document.getElementById('talk-btn').disabled = val;
  document.getElementById('send-btn').disabled = val;
}

// ─── Audio ───
function playAudio(b64) {
  return new Promise(resolve => {
    const audio = new Audio('data:audio/mp3;base64,' + b64);
    audio.onended = resolve;
    audio.onerror = resolve;
    audio.play().catch(resolve);
  });
}

// ─── Transcript ───
function addTranscript(speaker, text, isHost) {
  const el = document.getElementById('transcript');
  const entry = document.createElement('div');
  entry.className = 'transcript-entry';
  entry.innerHTML = `
    <div class="speaker ${isHost ? 'speaker-host' : 'speaker-user'}">${isHost ? '🎙️' : '🗣️'} ${esc(speaker)}</div>
    <div class="text">${esc(text)}</div>
  `;
  el.appendChild(entry);
  el.scrollTop = el.scrollHeight;
}

function downloadTranscript() {
  const entries = document.querySelectorAll('.transcript-entry');
  let md = `# Think-Pod Session\n\n`;
  entries.forEach(e => {
    const speaker = e.querySelector('.speaker').textContent.trim();
    const text = e.querySelector('.text').textContent.trim();
    md += `**${speaker}:** ${text}\n\n`;
  });
  const blob = new Blob([md], { type: 'text/markdown' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `thinkpod-session-${sessionId || 'draft'}.md`;
  a.click();
}

// ─── Helpers ───
function setStatus(cls, text) {
  const el = document.getElementById('status');
  el.className = 'status' + (cls ? ' ' + cls : '');
  el.textContent = text;
}

function esc(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) sendText();
});
