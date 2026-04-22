// CRT monitor flicker and glitch effects
(function() {
  const overlay = document.getElementById('crt-overlay');
  if (!overlay) return;

  // Random intense flicker
  function intenseFlic() {
    if (Math.random() < 0.05) {
      overlay.style.opacity = Math.random() * 0.3 + 0.7;
      setTimeout(() => {
        overlay.style.opacity = '';
      }, 50);
    }
  }

  setInterval(intenseFlic, 1000);

  // Glitch elements occasionally
  function glitchElements() {
    const elements = document.querySelectorAll('.panel-title, .nav-button, .status-value');
    if (elements.length === 0) return;
    
    const target = elements[Math.floor(Math.random() * elements.length)];
    const original = target.textContent;
    
    // Replace random characters with glitch symbols
    const glitchChars = '█▓▒░│┤╡╢╖╕╣║╗╝╜╛┐└┴┬├─┼';
    let glitched = '';
    for (let i = 0; i < original.length; i++) {
      glitched += Math.random() < 0.3 ? glitchChars[Math.floor(Math.random() * glitchChars.length)] : original[i];
    }
    
    target.textContent = glitched;
    setTimeout(() => {
      target.textContent = original;
    }, 100);
  }

  // Occasional glitch every 8-15 seconds
  function scheduleGlitch() {
    const delay = 8000 + Math.random() * 7000;
    setTimeout(() => {
      if (Math.random() < 0.7) {
        glitchElements();
      }
      scheduleGlitch();
    }, delay);
  }

  scheduleGlitch();

  // Screen shake on major events
  let shakeTimeout = null;
  window.screenShake = function() {
    const container = document.querySelector('.container');
    if (!container) return;
    
    container.style.transform = 'translate(2px, 1px)';
    setTimeout(() => {
      container.style.transform = 'translate(-1px, -2px)';
    }, 50);
    setTimeout(() => {
      container.style.transform = 'translate(-2px, 0px)';
    }, 100);
    setTimeout(() => {
      container.style.transform = 'translate(1px, 2px)';
    }, 150);
    setTimeout(() => {
      container.style.transform = '';
    }, 200);
  };

  // Power surge effect
  window.powerSurge = function() {
    overlay.style.animation = 'none';
    overlay.style.opacity = '0.3';
    setTimeout(() => {
      overlay.style.opacity = '1';
    }, 50);
    setTimeout(() => {
      overlay.style.opacity = '0.5';
    }, 100);
    setTimeout(() => {
      overlay.style.opacity = '';
      overlay.style.animation = '';
    }, 200);
  };
})();
