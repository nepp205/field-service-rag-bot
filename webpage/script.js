document.getElementById('theme-toggle').onclick = () => {
    document.documentElement.dataset.theme = 
        document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
};


document.addEventListener('DOMContentLoaded', () => {
    const sendBtn = document.getElementById('send-button');
    const userInput = document.getElementById('user-input');
    const micBtn = document.getElementById('mic-button');
    const chatBox = document.getElementById('chat-box');
    const responseText = document.getElementById('response-text');
const scrollDownBtn = document.getElementById('scroll-down-btn');   
    if (!userInput || !chatBox) return;

function checkScrollPosition() {
    const isAtBottom = chatBox.scrollHeight - chatBox.scrollTop <= chatBox.clientHeight + 1;
    scrollDownBtn.classList.toggle('show', !isAtBottom);
}

function scrollToBottom() {
    chatBox.scrollTo({
        top: chatBox.scrollHeight,
        behavior: 'smooth'
    });
    scrollDownBtn.classList.remove('show');
}

// Events
scrollDownBtn?.addEventListener('click', scrollToBottom);
chatBox.addEventListener('scroll', checkScrollPosition);

// Bei neuen Nachrichten prüfen
const observer = new MutationObserver(checkScrollPosition);
observer.observe(chatBox, { childList: true, subtree: true });

    // === SPEECH TO TEXT ===
    let recognition;
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'de-DE';

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
                micBtn.textContent = '⏹️';
            } else {
                alert('Spracherkennung nicht unterstützt (Chrome/Edge/Safari)');
            }
        });

        recognition?.addEventListener('end', () => {
            micBtn.textContent = '🎤';
        });
    }

    // === TEXT TO SPEECH ===
    function speak(text) {
        if ('speechSynthesis' in window) {
            speechSynthesis.cancel();  // Vorheriges stoppen
            
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = 'de-DE';
            utterance.rate = 0.9;
            utterance.pitch = 1.0;
            utterance.volume = 0.8;
            
            // Beste deutsche Stimme
            const voices = speechSynthesis.getVoices();
            const germanVoice = voices.find(v => 
                v.lang.startsWith('de-DE') && (
                    v.name.includes('Google') || 
                    v.name.includes('Hedda') || 
                    v.name.includes('Deutsch')
                )
            );
            if (germanVoice) utterance.voice = germanVoice;
            
            speechSynthesis.speak(utterance);
        }
    }

    // === CHAT HELPER ===
    function scrollToBottom() {
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function addMessage(role, text, options = {}) {
    const m = document.createElement('div');
    m.className = `message ${role}`;

    const b = document.createElement('div');
    b.className = 'bubble';
    b.textContent = text;
    m.appendChild(b);

    // Quellen-Ausklapper nur für Bot-Messages
    if (role === 'bot' && options.sources && options.sources.length > 0) {
        const toggle = document.createElement('div');
        toggle.className = 'source-toggle';
        toggle.textContent = 'Dokumentation anzeigen';

        const panel = document.createElement('div');
        panel.className = 'source-panel';

        const src = options.sources[0]; // erstmal nur erste Quelle nutzen

        const info = document.createElement('div');
        info.textContent = src.title || 'Dokumentation';
        panel.appendChild(info);

        const iframe = document.createElement('iframe');
        iframe.src = src.url;           // z.B. ein Dummy-PDF
        iframe.loading = 'lazy';
        panel.appendChild(iframe);

        toggle.addEventListener('click', () => {
            const isVisible = panel.style.display === 'block';
            panel.style.display = isVisible ? 'none' : 'block';
            toggle.textContent = isVisible ? 'Dokumentation anzeigen' : 'Dokumentation ausblenden';
        });

        m.appendChild(toggle);
        m.appendChild(panel);
    }

    chatBox.appendChild(m);
    scrollToBottom();
}


    // === BACKEND API ===
    const API_URL = 'http://localhost:8000/api/chat';
    const SESSION_ID = 'demo-session-1';

    const send = async () => {
        const value = (userInput.value || '').trim();
        if (!value) return;

        addMessage('user', value);
        userInput.value = '';
        if (responseText) responseText.textContent = '';

        const thinkingText = 'Diagnose wird erstellt...';
        addMessage('bot', thinkingText);
        if (sendBtn) sendBtn.disabled = true;

        const start = Date.now();
        const MIN_WAIT_MS = 500;

        try {
            const response = await fetch(API_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: value, sessionId: SESSION_ID })
            });

            const data = await response.json();
            const answer = data.answer || 'Keine Antwort vom LLM erhalten.';
            
            const elapsed = Date.now() - start;
            const wait = Math.max(0, MIN_WAIT_MS - elapsed);
            
            setTimeout(() => {
                // Thinking-Message entfernen
                const msgs = chatBox.querySelectorAll('.message.bot');
                const lastBot = msgs[msgs.length - 1];
                if (lastBot && lastBot.textContent === thinkingText) {
                    lastBot.remove();
                }

                // Antwort anzeigen + AUTO VORLESEN
                addMessage('bot', answer);
                if (responseText) responseText.textContent = answer;
                speak(answer);  // 🎯 Auto Text-to-Speech
                
                if (sendBtn) sendBtn.disabled = false;
            }, wait);

        } catch (err) {
            console.error('Fehler beim Request:', err);
            
            const elapsed = Date.now() - start;
            const wait = Math.max(0, MIN_WAIT_MS - elapsed);
            setTimeout(() => {
                const msgs = chatBox.querySelectorAll('.message.bot');
                const lastBot = msgs[msgs.length - 1];
                if (lastBot && lastBot.textContent === thinkingText) {
                    lastBot.remove();
                }
                addMessage('bot', 'Fehler beim Kontakt zum LLM Backend.');
                if (sendBtn) sendBtn.disabled = false;
            }, wait);
        }
    };

    // === EVENTS ===
    if (sendBtn) {
        sendBtn.addEventListener('click', send);
    }

    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            send();
        }
    });
});
