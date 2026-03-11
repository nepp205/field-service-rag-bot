const sendButton = document.getElementById('send-button');

sendButton?.addEventListener('click', () => {
    const userInputEl = document.getElementById('user-input');
    if (userInputEl && 'value' in userInputEl) {
        console.log(userInputEl.value);
    } else {
        // fallback to logging the literal string if no input element found
        console.log('user-input');
    }
});