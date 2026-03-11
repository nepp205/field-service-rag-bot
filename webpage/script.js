document.addEventListener('DOMContentLoaded', () => {
    const sendBtn = document.getElementById('send-button');
    const userInput = document.getElementById('user-input');

    if (!userInput) return;
    const chatBox = document.getElementById('chat-box');
    const responseText = document.getElementById('response-text');

    function scrollToBottom() {
        if (!chatBox) return;
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function addMessage(role, text) {
        if (!chatBox) return;
        const m = document.createElement('div');
        m.className = `message ${role}`;
        const b = document.createElement('div');
        b.className = 'bubble';
        b.textContent = text;
        m.appendChild(b);
        chatBox.appendChild(m);
        scrollToBottom();
    }

    const API_URL = 'http://localhost:8000/api/chat'; // Python LLM Handler
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
        const MIN_WAIT_MS = 500; // ensure spinner visible for at least this duration

        try {
            const response = await fetch(API_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: value,
                    sessionId: SESSION_ID
                })
            });

            const data = await response.json(); // erwartet { answer: '...' }
            const demo = data.answer || 'Keine Antwort vom LLM erhalten.';

            const elapsed = Date.now() - start;
            const wait = Math.max(0, MIN_WAIT_MS - elapsed);
            setTimeout(() => {
                const msgs = chatBox.querySelectorAll('.message.bot');
                const lastBot = msgs[msgs.length - 1];
                if (lastBot && lastBot.textContent === thinkingText) {
                    lastBot.remove();
                }
                addMessage('bot', demo);
                if (responseText) responseText.textContent = demo;
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
