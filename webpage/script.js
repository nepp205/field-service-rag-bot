// ============================================================
// Theme toggle – switches between light and dark mode via the
// data-theme attribute on <html>.
// ============================================================
document.getElementById('theme-toggle').onclick = () => {
    const isDark = document.documentElement.dataset.theme === 'dark';
    document.documentElement.dataset.theme = isDark ? 'light' : 'dark';
    document.getElementById('theme-toggle').textContent = isDark ? '🌙' : '☀️';
};

// ============================================================
// TTS toggle – enables / disables text-to-speech (off by default)
// ============================================================
let ttsEnabled = false;

document.getElementById('tts-toggle').onclick = () => {
    ttsEnabled = !ttsEnabled;
    document.getElementById('tts-toggle').textContent = ttsEnabled ? '🔊' : '🔇';
    if (!ttsEnabled) speechSynthesis.cancel();
};


document.addEventListener('DOMContentLoaded', () => {
    // ---- Element references ----
    const sendBtn      = document.getElementById('send-button');
    const userInput    = document.getElementById('user-input');
    const micBtn       = document.getElementById('mic-button');
    const chatBox      = document.getElementById('chat-box');
    const scrollDownBtn = document.getElementById('scroll-down-btn');

    // Abort early if required elements are missing
    if (!userInput || !chatBox) return;

    // ============================================================
    // Scroll helpers
    // ============================================================

    /** Show or hide the scroll-to-bottom button depending on position. */
    function checkScrollPosition() {
        const isAtBottom = chatBox.scrollHeight - chatBox.scrollTop <= chatBox.clientHeight + 1;
        scrollDownBtn.classList.toggle('show', !isAtBottom);
    }

    /** Smooth-scroll the chat box to the latest message. */
    function scrollToBottom() {
        chatBox.scrollTo({
            top: chatBox.scrollHeight,
            behavior: 'smooth'
        });
        scrollDownBtn.classList.remove('show');
    }

    // Update scroll-button visibility on user scroll and on new messages
    scrollDownBtn?.addEventListener('click', scrollToBottom);
    chatBox.addEventListener('scroll', checkScrollPosition);

    const observer = new MutationObserver(checkScrollPosition);
    observer.observe(chatBox, { childList: true, subtree: true });

    // ============================================================
    // Speech-to-Text (STT)
    // ============================================================
    let recognition;
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous    = false;  // stop after first utterance
        recognition.interimResults = false; // only final results
        recognition.lang          = 'de-DE';

        // Fill the input field with the recognised transcript
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
                micBtn.textContent = '⏹️'; // indicate active recording
            } else {
                alert('Spracherkennung nicht unterstützt (Chrome/Edge/Safari)');
            }
        });

        // Reset mic icon when recognition session ends
        recognition?.addEventListener('end', () => {
            micBtn.textContent = '🎤';
        });
    }

    // ============================================================
    // Text-to-Speech (TTS)
    // ============================================================

    /**
     * Read `text` aloud using the Web Speech API.
     * Prefers a German Google / system voice when available.
     *
     * @param {string} text - Plain text to speak.
     */
    function speak(text) {
        if (!ttsEnabled) return;
        if (!('speechSynthesis' in window)) return;

        speechSynthesis.cancel(); // stop any ongoing utterance

        const utterance  = new SpeechSynthesisUtterance(text);
        utterance.lang   = 'de-DE';
        utterance.rate   = 0.9;
        utterance.pitch  = 1.0;
        utterance.volume = 0.8;

        // Prefer a high-quality German voice if one is available
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

    // ============================================================
    // Chat helpers
    // ============================================================

    /**
     * Append a message bubble to the chat box.
     *
     * @param {'user'|'bot'} role - Who sent the message.
     * @param {string}       text - Message content.
     * @param {Object}       [options={}]
     * @param {Array}        [options.sources] - Optional list of source objects
     *                       ({title, url}) shown as a collapsible panel for
     *                       bot messages.
     */
    function addMessage(role, text, options = {}) {
        const m = document.createElement('div');
        m.className = `message ${role}`;
        if (options.placeholder) m.classList.add('placeholder');

        const b = document.createElement('div');
        b.className = 'bubble';

        if (role === 'bot' && typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
            // Render markdown and sanitize to prevent XSS
            b.innerHTML = DOMPurify.sanitize(marked.parse(text));
        } else {
            b.textContent = text;
        }

        m.appendChild(b);

        // Source-document collapsible panel (bot messages only)
        if (role === 'bot' && options.sources && options.sources.length > 0) {
            const toggle = document.createElement('div');
            toggle.className = 'source-toggle';
            toggle.textContent = 'Dokumentation anzeigen';

            const panel = document.createElement('div');
            panel.className = 'source-panel';

            const src = options.sources[0]; // display the primary source

            const info = document.createElement('div');
            info.textContent = src.title || 'Dokumentation';
            panel.appendChild(info);

            const iframe = document.createElement('iframe');
            iframe.src     = src.url;
            iframe.loading = 'lazy';
            panel.appendChild(iframe);

            toggle.addEventListener('click', () => {
                const isVisible = panel.style.display === 'block';
                panel.style.display = isVisible ? 'none' : 'block';
                toggle.textContent  = isVisible
                    ? 'Dokumentation anzeigen'
                    : 'Dokumentation ausblenden';
            });

            m.appendChild(toggle);
            m.appendChild(panel);
        }

        chatBox.appendChild(m);
        scrollToBottom();

        return { messageEl: m, bubbleEl: b };
    }

    // ============================================================
    // Backend API
    // ============================================================

    const API_BASE  = 'http://localhost:8000';
    const API_URL   = `${API_BASE}/api/chat`;

    // Generate a unique session ID for this page load.
    const SESSION_ID = (typeof crypto !== 'undefined' && crypto.randomUUID)
        ? crypto.randomUUID()
        : `session-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    console.log('[Session] ID:', SESSION_ID);

    // Disable input until the session is ready
    if (sendBtn)   sendBtn.disabled = true;
    if (userInput) userInput.disabled = true;
    if (micBtn)    micBtn.disabled = true;

    // Silently initialise the session on the backend (no UI feedback)
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
        // Still enable input so the user can try (fallback session created on first chat)
        if (sendBtn)   sendBtn.disabled = false;
        if (userInput) userInput.disabled = false;
        if (micBtn)    micBtn.disabled = false;
    });

    /**
     * Send the current input value to the backend and display the answer.
     * Shows a temporary "thinking" message while waiting for the response.
     * The bot's reply is also read aloud via TTS.
     */
    const send = async () => {
        const value = (userInput.value || '').trim();
        if (!value) return;

        addMessage('user', value);
        userInput.value = '';

        // Temporary thinking placeholder shown while the request is in-flight
        const thinkingText = 'Diagnose wird erstellt...';
        const placeholder = addMessage('bot', thinkingText, { placeholder: true });
        if (sendBtn) sendBtn.disabled = true;

        const start      = Date.now();
        const MIN_WAIT_MS = 500; // minimum display time for the thinking message

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
                // Replace placeholder content with real answer
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
                // Replace placeholder content with error message
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

    // ============================================================
    // Event listeners
    // ============================================================

    if (sendBtn) {
        sendBtn.addEventListener('click', send);
    }

    // Allow sending with the Enter key
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            send();
        }
    });
});
