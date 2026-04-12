// Hell/Dunkel-Modus umschalten
document.getElementById('theme-toggle').onclick = () => {
    const isDark = document.documentElement.dataset.theme === 'dark';
    document.documentElement.dataset.theme = isDark ? 'light' : 'dark';
    document.getElementById('theme-toggle').textContent = isDark ? '🌙' : '☀️';
};

// Sprachausgabe (TTS) ein-/ausschalten
let ttsEnabled = false;

document.getElementById('tts-toggle').onclick = () => {
    ttsEnabled = !ttsEnabled;
    document.getElementById('tts-toggle').textContent = ttsEnabled ? '🔊' : '🔇';
    if (!ttsEnabled) speechSynthesis.cancel(); // laufende Ausgabe stoppen
};


document.addEventListener('DOMContentLoaded', () => {
    // DOM-Elemente holen
    const sendBtn       = document.getElementById('send-button');
    const userInput     = document.getElementById('user-input');
    const micBtn        = document.getElementById('mic-button');
    const chatBox       = document.getElementById('chat-box');
    const scrollDownBtn = document.getElementById('scroll-down-btn');

    if (!userInput || !chatBox) return; // Abbruch wenn Pflicht-Elemente fehlen

    // Scroll-Button ein-/ausblenden je nach Position
    function checkScrollPosition() {
        const isAtBottom = chatBox.scrollHeight - chatBox.scrollTop <= chatBox.clientHeight + 1;
        scrollDownBtn.classList.toggle('show', !isAtBottom);
    }

    // Sanft zum Ende der Chat-Liste scrollen
    function scrollToBottom() {
        chatBox.scrollTo({ top: chatBox.scrollHeight, behavior: 'smooth' });
        scrollDownBtn.classList.remove('show');
    }

    scrollDownBtn?.addEventListener('click', scrollToBottom);
    chatBox.addEventListener('scroll', checkScrollPosition);
    const observer = new MutationObserver(checkScrollPosition);
    observer.observe(chatBox, { childList: true, subtree: true }); // bei neuen Nachrichten prüfen

    // Spracheingabe (STT) einrichten
    let recognition;
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous     = false; // stoppt nach erster Aussage
        recognition.interimResults = true;  // Zwischenergebnisse erlaubt
        recognition.lang           = 'de-DE';
        recognition.onresult = (event) => { userInput.value = event.results[0][0].transcript; }; // Text ins Eingabefeld schreiben
        recognition.onerror  = (event) => { console.error('Speech Error:', event.error); };
    }

    if (micBtn) {
        micBtn.addEventListener('click', () => {
            if (recognition) {
                recognition.start();
                micBtn.textContent = '⏹️'; // Aufnahme läuft
            } else {
                alert('Spracherkennung nicht unterstützt (Chrome/Edge/Safari)');
            }
        });
        recognition?.addEventListener('end', () => { micBtn.textContent = '🎤'; }); // Icon zurücksetzen
    }

    // Text über Web Speech API vorlesen
    function speak(text) {
        if (!ttsEnabled || !('speechSynthesis' in window)) return;
        speechSynthesis.cancel(); // vorherige Ausgabe abbrechen
        const utterance  = new SpeechSynthesisUtterance(text);
        utterance.lang   = 'de-DE';
        utterance.rate   = 0.9;
        utterance.pitch  = 1.0;
        utterance.volume = 0.8;
        // Deutsche Stimme bevorzugen wenn vorhanden
        const germanVoice = speechSynthesis.getVoices().find(v =>
            v.lang.startsWith('de-DE') && (v.name.includes('Google') || v.name.includes('Hedda') || v.name.includes('Deutsch'))
        );
        if (germanVoice) utterance.voice = germanVoice;
        speechSynthesis.speak(utterance);
    }

    // Neue Nachrichtenblase in den Chat einfügen
    function addMessage(role, text, options = {}) {
        const m = document.createElement('div');
        m.className = `message ${role}`;
        if (options.placeholder) m.classList.add('placeholder'); // Ladezustand markieren

        const b = document.createElement('div');
        b.className = 'bubble';

        if (role === 'bot' && typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
            b.innerHTML = DOMPurify.sanitize(marked.parse(text)); // Markdown rendern + XSS-Schutz
        } else {
            b.textContent = text;
        }

        m.appendChild(b);

        // Quelldokument-Panel nur bei Bot-Nachrichten mit Quellen
        if (role === 'bot' && options.sources && options.sources.length > 0) {
            const src = options.sources[0]; // nur die erste Quelle zeigen

            const toggle = document.createElement('div');
            toggle.className   = 'source-toggle';
            toggle.textContent = 'Dokumentation anzeigen';

            const panel = document.createElement('div');
            panel.className = 'source-panel';

            const info = document.createElement('div');
            info.textContent = src.title || 'Dokumentation';
            panel.appendChild(info);

            const iframe = document.createElement('iframe');
            iframe.src     = src.url;
            iframe.loading = 'lazy';
            panel.appendChild(iframe);

            toggle.addEventListener('click', () => {
                const isVisible = panel.style.display === 'block';
                panel.style.display = isVisible ? 'none' : 'block'; // Panel ein-/ausklappen
                toggle.textContent  = isVisible ? 'Dokumentation anzeigen' : 'Dokumentation ausblenden';
            });

            m.appendChild(toggle);
            m.appendChild(panel);
        }

        chatBox.appendChild(m);
        scrollToBottom();
        return { messageEl: m, bubbleEl: b };
    }

    // API-Endpunkt und eindeutige Sitzungs-ID für diesen Seitenaufruf
    const API_BASE   = 'http://localhost:8000';
    const API_URL    = `${API_BASE}/api/chat`;
    const SESSION_ID = (typeof crypto !== 'undefined' && crypto.randomUUID)
        ? crypto.randomUUID()
        : `session-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    console.log('[Session] ID:', SESSION_ID);

    // Eingabe sperren bis Sitzung bereit ist
    if (sendBtn)   sendBtn.disabled   = true;
    if (userInput) userInput.disabled = true;
    if (micBtn)    micBtn.disabled    = true;

    // Sitzung beim Backend initialisieren
    fetch(`${API_BASE}/api/session/init`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId: SESSION_ID })
    })
    .then(() => {
        console.log('[Session] Initialised successfully:', SESSION_ID);
        if (sendBtn)   sendBtn.disabled   = false; // Eingabe freischalten
        if (userInput) userInput.disabled = false;
        if (micBtn)    micBtn.disabled    = false;
    })
    .catch(err => {
        console.error('[Session] Init failed:', err);
        if (sendBtn)   sendBtn.disabled   = false; // auch bei Fehler freischalten
        if (userInput) userInput.disabled = false;
        if (micBtn)    micBtn.disabled    = false;
    });

    // Nachricht ans Backend senden und Antwort anzeigen
    const send = async () => {
        const value = (userInput.value || '').trim();
        if (!value) return;

        addMessage('user', value);
        userInput.value = '';

        // Ladeplatzhalter während der Anfrage anzeigen
        const placeholder = addMessage('bot', 'Diagnose wird erstellt...', { placeholder: true });
        if (sendBtn) sendBtn.disabled = true;

        const start       = Date.now();
        const MIN_WAIT_MS = 500; // mindestens 500ms Ladezeit anzeigen

        try {
            const response = await fetch(API_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: value, sessionId: SESSION_ID })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data   = await response.json();
            const answer = data.answer || 'Keine Antwort vom LLM erhalten.';
            const wait   = Math.max(0, MIN_WAIT_MS - (Date.now() - start));

            setTimeout(() => {
                // Platzhalter durch echte Antwort ersetzen
                if (placeholder?.bubbleEl) {
                    if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
                        placeholder.bubbleEl.innerHTML = DOMPurify.sanitize(marked.parse(answer));
                    } else {
                        placeholder.bubbleEl.textContent = answer;
                    }
                    placeholder.messageEl.classList.remove('placeholder');
                } else {
                    addMessage('bot', answer);
                }
                speak(answer);
                if (sendBtn) sendBtn.disabled = false;
            }, wait);

        } catch (err) {
            console.error('Fehler beim Request:', err);
            const wait = Math.max(0, MIN_WAIT_MS - (Date.now() - start));
            setTimeout(() => {
                // Fehlermeldung anzeigen
                if (placeholder?.bubbleEl) {
                    placeholder.bubbleEl.textContent = 'Fehler beim Kontakt zum LLM Backend.';
                    placeholder.messageEl.classList.remove('placeholder');
                } else {
                    addMessage('bot', 'Fehler beim Kontakt zum LLM Backend.');
                }
                if (sendBtn) sendBtn.disabled = false;
            }, wait);
        }
    };

    // Sende-Button und Enter-Taste binden
    if (sendBtn) sendBtn.addEventListener('click', send);
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); send(); } // Enter = Senden
    });
});
