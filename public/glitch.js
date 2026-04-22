// Random glitch effects and user ID generator
(function() {
  // Generate random user ID
  const userIdEl = document.getElementById('user-id');
  if (userIdEl) {
    const chars = '0123456789ABCDEF';
    let id = 'GUEST_';
    for (let i = 0; i < 10; i++) {
      id += chars[Math.floor(Math.random() * chars.length)];
    }
    userIdEl.textContent = id;
  }

  // Update uptime
  const uptimeEl = document.getElementById('uptime');
  if (uptimeEl) {
    const startTime = Date.now();
    setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000);
      const hours = Math.floor(elapsed / 3600);
      const minutes = Math.floor((elapsed % 3600) / 60);
      const seconds = elapsed % 60;
      const pad = (n) => String(n).padStart(2, '0');
      uptimeEl.textContent = `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
    }, 1000);
  }

  // Random text glitch effect on ASCII title
  const asciiTitle = document.querySelector('.ascii-border');
  if (asciiTitle) {
    const originalText = asciiTitle.textContent;
    
    function glitchText() {
      if (Math.random() > 0.97) {
        // Temporarily glitch the text
        const chars = '░▒▓█▄▀■□▪▫';
        let glitched = '';
        for (let i = 0; i < originalText.length; i++) {
          if (Math.random() > 0.95) {
            glitched += chars[Math.floor(Math.random() * chars.length)];
          } else {
            glitched += originalText[i];
          }
        }
        asciiTitle.textContent = glitched;
        
        // Restore after a brief moment
        setTimeout(() => {
          asciiTitle.textContent = originalText;
        }, 50);
      }
    }
    
    setInterval(glitchText, 3000);
  }

  // Random screen flicker
  function randomFlicker() {
    if (Math.random() > 0.98) {
      document.body.style.opacity = '0.9';
      setTimeout(() => {
        document.body.style.opacity = '1';
      }, 50);
    }
  }
  
  setInterval(randomFlicker, 5000);

  // Cursor trail effect
  const cursorTrail = [];
  const maxTrailLength = 8;

  document.addEventListener('mousemove', (e) => {
    if (Math.random() > 0.7) {
      const dot = document.createElement('div');
      dot.style.position = 'fixed';
      dot.style.left = e.clientX + 'px';
      dot.style.top = e.clientY + 'px';
      dot.style.width = '3px';
      dot.style.height = '3px';
      dot.style.background = '#00ff41';
      dot.style.borderRadius = '50%';
      dot.style.pointerEvents = 'none';
      dot.style.zIndex = '9999';
      dot.style.boxShadow = '0 0 5px #00ff41';
      dot.style.opacity = '0.6';
      document.body.appendChild(dot);

      cursorTrail.push(dot);
      if (cursorTrail.length > maxTrailLength) {
        const old = cursorTrail.shift();
        old.remove();
      }

      setTimeout(() => {
        dot.style.transition = 'opacity 0.5s ease';
        dot.style.opacity = '0';
        setTimeout(() => dot.remove(), 500);
      }, 100);
    }
  });

  // Random terminal messages
  const terminalMessages = [
    '> System integrity: 99.7%',
    '> Quantum flux stabilized',
    '> Neural network synced',
    '> Dimensional anchor holding',
    '> Chaos subroutine active',
    '> Reality matrix coherent',
    '> Post-it nodes operational'
  ];

  function showRandomMessage() {
    if (Math.random() > 0.95) {
      const msg = terminalMessages[Math.floor(Math.random() * terminalMessages.length)];
      const toast = document.createElement('div');
      toast.className = 'toast show';
      toast.textContent = msg;
      toast.style.fontSize = '0.85rem';
      toast.style.padding = '0.6rem 1.2rem';
      document.body.appendChild(toast);
      
      setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
      }, 2000);
    }
  }

  setInterval(showRandomMessage, 30000);
})();
