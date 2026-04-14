// Schaltet zwischen hellem und dunklem Theme um.
document.getElementById('theme-toggle').onclick = () => {
    const isDark = document.documentElement.dataset.theme === 'dark';
    document.documentElement.dataset.theme = isDark ? 'light' : 'dark';
    document.getElementById('theme-toggle').textContent = isDark ? '🌙' : '☀️';
};

// Schaltet Text-to-Speech ein oder aus.
let ttsEnabled = false;

document.getElementById('tts-toggle').onclick = () => {
    ttsEnabled = !ttsEnabled;
    document.getElementById('tts-toggle').textContent = ttsEnabled ? '🔊' : '🔇';
    if (!ttsEnabled) speechSynthesis.cancel();
};


document.addEventListener('DOMContentLoaded', () => {
    // Holt die wichtigsten Elemente aus dem DOM.
    const sendBtn      = document.getElementById('send-button');
    const userInput    = document.getElementById('user-input');
    const micBtn       = document.getElementById('mic-button');
    const chatBox      = document.getElementById('chat-box');
    const scrollDownBtn = document.getElementById('scroll-down-btn');

    // Bricht ab, wenn wichtige Elemente fehlen.
    if (!userInput || !chatBox) return;

    // Hilfsfunktionen fürs Scrollen.

    // Zeigt oder versteckt den Scroll-Button je nach Position.
    function checkScrollPosition() {
        const isAtBottom = chatBox.scrollHeight - chatBox.scrollTop <= chatBox.clientHeight + 1;
        scrollDownBtn.classList.toggle('show', !isAtBottom);
    }

    // Scrollt weich zur neuesten Nachricht.
    function scrollToBottom() {
        chatBox.scrollTo({
            top: chatBox.scrollHeight,
            behavior: 'smooth'
        });
        scrollDownBtn.classList.remove('show');
    }

    // Aktualisiert den Scroll-Button bei Scrollen und neuen Nachrichten.
    scrollDownBtn?.addEventListener('click', scrollToBottom);
    chatBox.addEventListener('scroll', checkScrollPosition);

    // Beobachtet Änderungen im Chat für die Scroll-Logik.
    const observer = new MutationObserver(checkScrollPosition);
    observer.observe(chatBox, { childList: true, subtree: true });

    // Bereich für Speech-to-Text.
    let recognition;
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous    = false;  // Stoppt nach der ersten Erkennung.
        recognition.interimResults = true;   // Zeigt auch Zwischenergebnisse an.
        recognition.lang          = 'de-DE';

        // Schreibt den erkannten Text ins Eingabefeld.
        recognition.onresult = (event) => {
            userInput.value = event.results[0][0].transcript;
        };

        recognition.onerror = (event) => {
            console.error('Speech Error:', event.error);
        };
    }

    if (micBtn) {
        micBtn.addEventListener('click', () => {
            if (recognition) {
                recognition.start();
                micBtn.textContent = '⏹️'; // Zeigt aktive Aufnahme an.
            } else {
                alert('Spracherkennung nicht unterstützt (Chrome/Edge/Safari)');
            }
        });

        // Setzt das Mikro-Icon zurück, wenn die Aufnahme endet.
        recognition?.addEventListener('end', () => {
            micBtn.textContent = '🎤';
        });
    }

    // Bereich für Text-to-Speech.

    // Liest den Text laut vor und bevorzugt eine deutsche Stimme.
    function speak(text) {
        if (!ttsEnabled) return;
        if (!('speechSynthesis' in window)) return;

        speechSynthesis.cancel(); // Stoppt laufende Sprachausgabe.

        const utterance  = new SpeechSynthesisUtterance(text);
        utterance.lang   = 'de-DE';
        utterance.rate   = 0.9;
        utterance.pitch  = 1.0;
        utterance.volume = 0.8;

    // Nutzt eine gute deutsche Stimme, wenn verfügbar.
        const voices = speechSynthesis.getVoices();
        const germanVoice = voices.find(v =>
            v.lang.startsWith('de-DE') && (
                v.name.includes('Google') ||
                v.name.includes('Hedda')  ||
                v.name.includes('Deutsch')
            )
        );
        if (germanVoice) utterance.voice = germanVoice;

        speechSynthesis.speak(utterance);
    }

    // Hilfsfunktionen für den Chat.

    // Fügt eine neue Nachrichtenblase im Chat hinzu.
    function addMessage(role, text, options = {}) {
        const m = document.createElement('div');
        m.className = `message ${role}`;
        if (options.placeholder) m.classList.add('placeholder');

        const b = document.createElement('div');
        b.className = 'bubble';

        if (role === 'bot' && typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
            // Rendert Markdown und bereinigt es gegen XSS.
            b.innerHTML = DOMPurify.sanitize(marked.parse(text));
        } else {
            b.textContent = text;
        }

        m.appendChild(b);

        chatBox.appendChild(m);
        scrollToBottom();

        return { messageEl: m, bubbleEl: b };
    }

    // Backend-API Einstellungen.

    const API_BASE  = 'http://localhost:8000';
    const API_URL   = `${API_BASE}/api/chat`;

    // Erstellt eine eindeutige Session-ID für diesen Seitenaufruf.
    const SESSION_ID = (typeof crypto !== 'undefined' && crypto.randomUUID)
        ? crypto.randomUUID()
        : `session-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    console.log('[Session] ID:', SESSION_ID);

    // Deaktiviert Eingaben bis die Session bereit ist.
    if (sendBtn)   sendBtn.disabled = true;
    if (userInput) userInput.disabled = true;
    if (micBtn)    micBtn.disabled = true;

    // Initialisiert die Session im Backend ohne zusätzliche UI-Meldung.
    fetch(`${API_BASE}/api/session/init`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId: SESSION_ID })
    })
    .then(() => {
        console.log('[Session] Initialised successfully:', SESSION_ID);
        if (sendBtn)   sendBtn.disabled = false;
        if (userInput) userInput.disabled = false;
        if (micBtn)    micBtn.disabled = false;
    })
    .catch((err) => {
        console.error('[Session] Init failed:', err);
        // Aktiviert Eingaben trotzdem, damit man es direkt probieren kann.
        if (sendBtn)   sendBtn.disabled = false;
        if (userInput) userInput.disabled = false;
        if (micBtn)    micBtn.disabled = false;
    });

    // Sendet die Eingabe ans Backend und zeigt danach die Antwort an.
    const send = async () => {
        const value = (userInput.value || '').trim();
        if (!value) return;

        addMessage('user', value);
        userInput.value = '';

    // Zeigt kurz eine Platzhalter-Nachricht während die Anfrage läuft.
        const thinkingText = 'Diagnose wird erstellt...';
        const placeholder = addMessage('bot', thinkingText, { placeholder: true });
        if (sendBtn) sendBtn.disabled = true;

        const start      = Date.now();
    const MIN_WAIT_MS = 300; // Mindestanzeigezeit für den Platzhalter.

        try {
            const response = await fetch(API_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: value, sessionId: SESSION_ID })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data   = await response.json();
            const answer = data.answer || 'Keine Antwort vom LLM erhalten.';

            const elapsed = Date.now() - start;
            const wait    = Math.max(0, MIN_WAIT_MS - elapsed);

            setTimeout(() => {
                // Ersetzt den Platzhalter mit der echten Antwort.
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

            const elapsed = Date.now() - start;
            const wait    = Math.max(0, MIN_WAIT_MS - elapsed);

            setTimeout(() => {
                // Ersetzt den Platzhalter mit einer Fehlermeldung.
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

    // Event-Listener.

    if (sendBtn) {
        sendBtn.addEventListener('click', send);
    }

    // Erlaubt das Senden mit der Enter-Taste.
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            send();
        }
    });
});
