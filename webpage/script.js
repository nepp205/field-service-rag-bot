// Hell/Dunkel-Modus umschalten
document.getElementById('theme-toggle').onclick = () => {
    const dunkel = document.documentElement.dataset.theme === 'dark';
    document.documentElement.dataset.theme = dunkel ? 'light' : 'dark';
    document.getElementById('theme-toggle').textContent = dunkel ? '🌙' : '☀️';
};

// Sprachausgabe (TTS) ein-/ausschalten
let ttsAktiv = false;

document.getElementById('tts-toggle').onclick = () => {
    ttsAktiv = !ttsAktiv;
    document.getElementById('tts-toggle').textContent = ttsAktiv ? '🔊' : '🔇';
    if (!ttsAktiv) speechSynthesis.cancel(); // laufende Ausgabe stoppen
};


document.addEventListener('DOMContentLoaded', () => {
    // DOM-Elemente holen
    const sendeBtn  = document.getElementById('send-button');
    const eingabe   = document.getElementById('user-input');
    const mikBtn    = document.getElementById('mic-button');
    const chatBox   = document.getElementById('chat-box');
    const scrollBtn = document.getElementById('scroll-down-btn');

    if (!eingabe || !chatBox) return; // Abbruch wenn Pflicht-Elemente fehlen

    // Scroll-Button ein-/ausblenden je nach Position
    function scrollPruefen() {
        const amEnde = chatBox.scrollHeight - chatBox.scrollTop <= chatBox.clientHeight + 1;
        scrollBtn.classList.toggle('show', !amEnde);
    }

    // Sanft zum Ende der Chat-Liste scrollen
    function scrollNachUnten() {
        chatBox.scrollTo({ top: chatBox.scrollHeight, behavior: 'smooth' });
        scrollBtn.classList.remove('show');
    }

    scrollBtn?.addEventListener('click', scrollNachUnten);
    chatBox.addEventListener('scroll', scrollPruefen);
    const beobachter = new MutationObserver(scrollPruefen);
    beobachter.observe(chatBox, { childList: true, subtree: true }); // bei neuen Nachrichten prüfen

    // Spracheingabe (STT) einrichten
    let erkennung;
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        erkennung = new SpeechRecognition();
        erkennung.continuous     = false; // stoppt nach erster Aussage
        erkennung.interimResults = true;  // Zwischenergebnisse erlaubt
        erkennung.lang           = 'de-DE';
        erkennung.onresult = (e) => { eingabe.value = e.results[0][0].transcript; }; // Text ins Eingabefeld schreiben
        erkennung.onerror  = (e) => { console.error('Sprachfehler:', e.error); };
    }

    if (mikBtn) {
        mikBtn.addEventListener('click', () => {
            if (erkennung) {
                erkennung.start();
                mikBtn.textContent = '⏹️'; // Aufnahme läuft
            } else {
                alert('Spracherkennung nicht unterstützt (Chrome/Edge/Safari)');
            }
        });
        erkennung?.addEventListener('end', () => { mikBtn.textContent = '🎤'; }); // Icon zurücksetzen
    }

    // Text über Web Speech API vorlesen
    function vorlesen(text) {
        if (!ttsAktiv || !('speechSynthesis' in window)) return;
        speechSynthesis.cancel(); // vorherige Ausgabe abbrechen
        const sprecher  = new SpeechSynthesisUtterance(text);
        sprecher.lang   = 'de-DE';
        sprecher.rate   = 0.9;
        sprecher.pitch  = 1.0;
        sprecher.volume = 0.8;
        // Deutsche Stimme bevorzugen wenn vorhanden
        const stimme = speechSynthesis.getVoices().find(v =>
            v.lang.startsWith('de-DE') && (v.name.includes('Google') || v.name.includes('Hedda') || v.name.includes('Deutsch'))
        );
        if (stimme) sprecher.voice = stimme;
        speechSynthesis.speak(sprecher);
    }

    // Neue Nachrichtenblase in den Chat einfügen
    function nachrichtAnzeigen(rolle, text, optionen = {}) {
        const msg = document.createElement('div');
        msg.className = `message ${rolle}`;
        if (optionen.platzhalter) msg.classList.add('placeholder'); // Ladezustand markieren

        const blase = document.createElement('div');
        blase.className = 'bubble';

        if (rolle === 'bot' && typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
            blase.innerHTML = DOMPurify.sanitize(marked.parse(text)); // Markdown rendern + XSS-Schutz
        } else {
            blase.textContent = text;
        }

        msg.appendChild(blase);

        // Quelldokument-Panel nur bei Bot-Nachrichten mit Quellen
        if (rolle === 'bot' && optionen.sources?.length > 0) {
            const quelle = optionen.sources[0]; // nur die erste Quelle zeigen

            const toggle = document.createElement('div');
            toggle.className   = 'source-toggle';
            toggle.textContent = 'Dokumentation anzeigen';

            const panel = document.createElement('div');
            panel.className = 'source-panel';

            const info = document.createElement('div');
            info.textContent = quelle.title || 'Dokumentation';
            panel.appendChild(info);

            const iframe = document.createElement('iframe');
            iframe.src     = quelle.url;
            iframe.loading = 'lazy';
            panel.appendChild(iframe);

            toggle.addEventListener('click', () => {
                const sichtbar = panel.style.display === 'block';
                panel.style.display = sichtbar ? 'none' : 'block'; // Panel ein-/ausklappen
                toggle.textContent  = sichtbar ? 'Dokumentation anzeigen' : 'Dokumentation ausblenden';
            });

            msg.appendChild(toggle);
            msg.appendChild(panel);
        }

        chatBox.appendChild(msg);
        scrollNachUnten();
        return { messageEl: msg, bubbleEl: blase };
    }

    // API-Endpunkt und eindeutige Sitzungs-ID (kryptografisch sicher)
    const API_URL    = 'http://localhost:8000/api/chat';
    const SESSION_ID = crypto?.randomUUID?.() ??
        `session-${[...crypto.getRandomValues(new Uint32Array(4))].map(n => n.toString(36)).join('')}`;
    console.log('[Sitzung] ID:', SESSION_ID);

    // Eingabe sperren bis Sitzung bereit ist
    [sendeBtn, eingabe, mikBtn].forEach(el => { if (el) el.disabled = true; });

    // Sitzung beim Backend initialisieren
    fetch('http://localhost:8000/api/session/init', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId: SESSION_ID })
    })
    .then(() => {
        console.log('[Sitzung] Bereit:', SESSION_ID);
        [sendeBtn, eingabe, mikBtn].forEach(el => { if (el) el.disabled = false; }); // Eingabe freischalten
    })
    .catch(err => {
        console.error('[Sitzung] Fehler:', err);
        [sendeBtn, eingabe, mikBtn].forEach(el => { if (el) el.disabled = false; }); // auch bei Fehler freischalten
    });

    // Nachricht ans Backend senden und Antwort anzeigen
    const senden = async () => {
        const text = (eingabe.value || '').trim();
        if (!text) return;

        nachrichtAnzeigen('user', text);
        eingabe.value = '';

        // Ladeplatzhalter während der Anfrage anzeigen
        const ladeAnzeige = nachrichtAnzeigen('bot', 'Diagnose wird erstellt...', { platzhalter: true });
        if (sendeBtn) sendeBtn.disabled = true;

        const startZeit = Date.now();
        const MIN_WARTE = 500; // mindestens 500ms Ladezeit anzeigen

        try {
            const antwort = await fetch(API_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text, sessionId: SESSION_ID })
            });

            if (!antwort.ok) throw new Error(`HTTP ${antwort.status}`);

            const daten   = await antwort.json();
            const botText = daten.answer || 'Keine Antwort vom LLM erhalten.';
            const warte   = Math.max(0, MIN_WARTE - (Date.now() - startZeit));

            setTimeout(() => {
                // Platzhalter durch echte Antwort ersetzen
                if (ladeAnzeige?.bubbleEl) {
                    if (typeof marked !== 'undefined' && typeof DOMPurify !== 'undefined') {
                        ladeAnzeige.bubbleEl.innerHTML = DOMPurify.sanitize(marked.parse(botText));
                    } else {
                        ladeAnzeige.bubbleEl.textContent = botText;
                    }
                    ladeAnzeige.messageEl.classList.remove('placeholder');
                } else {
                    nachrichtAnzeigen('bot', botText);
                }
                vorlesen(botText);
                if (sendeBtn) sendeBtn.disabled = false;
            }, warte);

        } catch (fehler) {
            console.error('Fehler beim Request:', fehler);
            const warte = Math.max(0, MIN_WARTE - (Date.now() - startZeit));
            setTimeout(() => {
                // Fehlermeldung anzeigen
                if (ladeAnzeige?.bubbleEl) {
                    ladeAnzeige.bubbleEl.textContent = 'Fehler beim Kontakt zum LLM Backend.';
                    ladeAnzeige.messageEl.classList.remove('placeholder');
                } else {
                    nachrichtAnzeigen('bot', 'Fehler beim Kontakt zum LLM Backend.');
                }
                if (sendeBtn) sendeBtn.disabled = false;
            }, warte);
        }
    };

    // Sende-Button und Enter-Taste binden
    sendeBtn?.addEventListener('click', senden);
    eingabe.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); senden(); } // Enter = Senden
    });
});
