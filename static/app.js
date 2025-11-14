(() => {
  const list = document.getElementById('chatList');
  const typing = document.getElementById('typing');
  const form = document.getElementById('composer');
  const input = document.getElementById('message');
  const chips = document.getElementById('suggestions');
  const newChatBtn = document.getElementById('newChatBtn');
  const themeToggle = document.getElementById('themeToggle');
  const startChatBtn = document.getElementById('startChatBtn');

  let lastRole = null;

  function autoResize(el){
    el.style.height = 'auto';
    el.style.height = Math.min(160, el.scrollHeight) + 'px';
  }

  function addRow(role, text){
    const row = document.createElement('div');
    row.className = `row ${role}`;

    if (lastRole === role) row.classList.add('grouped');
    lastRole = role;

    if (role === 'bot'){
      const av = document.createElement('div');
      av.className = 'avatar bot-avatar';
      const img = document.createElement('img');
      img.src = 'https://img.icons8.com/windows/64/chatbot.png';
      img.alt = 'chatbot';
      img.style.width = '24px';
      img.style.height = '24px';
      img.style.objectFit = 'contain';
      av.appendChild(img);
      row.appendChild(av);
    }

    const bubble = document.createElement('div');
    bubble.className = 'bubble';

    if (typeof text === 'string' && /<\w+[^>]*>/.test(text)) {
      bubble.innerHTML = text;
    } else {
      bubble.textContent = text;
    }
    row.appendChild(bubble);

    list.appendChild(row);
    list.scrollTop = list.scrollHeight;
  }

  function showTyping(show){
    if (!typing || !list) return;
    if (show){
      if (typing.parentElement !== list || list.lastElementChild !== typing) {
        list.appendChild(typing);
      }
      typing.classList.remove('hidden');
      list.scrollTop = list.scrollHeight;
    } else {
      typing.classList.add('hidden');
    }
  }

  function updateSendState(){
    const btn = form.querySelector('button');
    if (!btn) return;
    const hasText = input && input.value.trim().length > 0;
    btn.disabled = !hasText;
  }

  function applyTheme(theme) {
    if (theme === 'light') document.body.classList.add('theme-light');
    else document.body.classList.remove('theme-light');
    updateThemeIcon();
  }
  function currentTheme(){
    return document.body.classList.contains('theme-light') ? 'light' : 'dark';
  }
  function updateThemeIcon(){
    if (!themeToggle) return;
    const isLight = currentTheme() === 'light';
    themeToggle.innerHTML = isLight
      ? '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>'
      : '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2m-2.93 7.07-1.41-1.41M6.34 6.34 4.93 4.93m12.73 0-1.41 1.41M6.34 17.66l-1.41 1.41"/></svg>';
  }

  const savedTheme = localStorage.getItem('theme');
  if (savedTheme) applyTheme(savedTheme);
  else applyTheme('dark');
  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      const next = currentTheme() === 'light' ? 'dark' : 'light';
      localStorage.setItem('theme', next);
      applyTheme(next);
    });
  }

  async function sendMessage(text){
    addRow('user', text);
    showTyping(true);
    form.querySelector('button').disabled = true;
    input.disabled = true;

    try{
      const res = await fetch('/api/chat', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ message:text })
      });
  const data = await res.json();
  showTyping(false);
  addRow('bot', data.reply || 'Sorry, something went wrong.');
    }catch(err){
      showTyping(false);
      addRow('bot', 'Network error. Please try again.');
    }finally{
      form.querySelector('button').disabled = false;
      input.disabled = false;
      input.focus();
      updateSendState();
    }
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    autoResize(input);
    updateSendState();
    sendMessage(text);
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey){
      e.preventDefault();
      form.requestSubmit();
    }
  });
  input.addEventListener('input', () => { autoResize(input); updateSendState(); });


  if (chips) {
    chips.addEventListener('click', (e) => {
      const btn = e.target.closest('.chip');
      if (!btn) return;
      input.value = btn.textContent.trim();
      autoResize(input);
      updateSendState();
      form.requestSubmit();
    });
  }

  if (newChatBtn && list) {
    newChatBtn.addEventListener('click', () => {
      list.innerHTML = '';
      lastRole = null;
      addRow('bot', "New chat started. Ask me anything about DPWH projects.");
      input && input.focus();
    });
  }

  if (startChatBtn) {
  }

  if (list) addRow('bot', "Hi! I'm your DPWH Agent. Ask me anything.");

  if (form && input) updateSendState();
})();
