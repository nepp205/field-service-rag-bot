// ============================================================
// Theme toggle – switches between light and dark mode via the
// data-theme attribute on <html>.
// ============================================================
document.getElementById('theme-toggle').onclick = () => {
    document.documentElement.dataset.theme =
        document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
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

        const b = document.createElement('div');
        b.className = 'bubble';
        b.textContent = text;
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
    }

    // ============================================================
    // Typing indicator
    // ============================================================

    /**
     * Append an animated typing-indicator bubble to the chat box.
     * Returns the wrapper element so it can be removed when the response arrives.
     *
     * @returns {HTMLElement} The `.message.bot` wrapper element.
     */
    function addTypingIndicator() {
        const m = document.createElement('div');
        m.className = 'message bot';

        const indicator = document.createElement('div');
        indicator.className = 'typing-indicator';

        const dots = document.createElement('div');
        dots.className = 'typing-dots';
        for (let i = 0; i < 3; i++) {
            const dot = document.createElement('span');
            dot.className = 'typing-dot';
            dots.appendChild(dot);
        }

        const label = document.createElement('span');
        label.className = 'typing-text';
        label.textContent = 'Diagnose wird erstellt...';

        indicator.appendChild(dots);
        indicator.appendChild(label);
        m.appendChild(indicator);

        chatBox.appendChild(m);
        scrollToBottom();
        return m;
    }

    // ============================================================
    // Backend API
    // ============================================================

    const API_URL   = 'http://localhost:8000/api/chat';
    const SESSION_ID = 'demo-session-1';

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

        // Animated typing-indicator shown while the request is in-flight
        const thinkingBubble = addTypingIndicator();
        if (sendBtn) sendBtn.disabled = true;

        const start      = Date.now();
        const MIN_WAIT_MS = 500; // minimum display time for the thinking message

        try {
            const response = await fetch(API_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: value, sessionId: SESSION_ID })
            });

            const data   = await response.json();
            const answer = data.answer || 'Keine Antwort vom LLM erhalten.';

            // Ensure the thinking message is visible for at least MIN_WAIT_MS
            const elapsed = Date.now() - start;
            const wait    = Math.max(0, MIN_WAIT_MS - elapsed);

            setTimeout(() => {
                thinkingBubble.remove();
                addMessage('bot', answer);
                speak(answer); // auto-read the bot's reply aloud
                if (sendBtn) sendBtn.disabled = false;
            }, wait);

        } catch (err) {
            console.error('Fehler beim Request:', err);

            const elapsed = Date.now() - start;
            const wait    = Math.max(0, MIN_WAIT_MS - elapsed);

            setTimeout(() => {
                thinkingBubble.remove();
                addMessage('bot', 'Fehler beim Kontakt zum LLM Backend.');
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
