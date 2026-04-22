// Floating candle that follows the mouse cursor
(function() {
  // Create candle element
  const candle = document.createElement('div');
  candle.id = 'floating-candle';
  candle.innerHTML = `
    <svg width="30" height="50" viewBox="0 0 30 50" xmlns="http://www.w3.org/2000/svg">
      <!-- Flame -->
      <ellipse cx="15" cy="8" rx="6" ry="10" fill="#d04423" opacity="0.3">
        <animate attributeName="ry" values="10;12;10" dur="1.5s" repeatCount="indefinite"/>
      </ellipse>
      <ellipse cx="15" cy="8" rx="4" ry="8" fill="#c9a961">
        <animate attributeName="ry" values="8;10;8" dur="1.2s" repeatCount="indefinite"/>
      </ellipse>
      <ellipse cx="15" cy="8" rx="2" ry="5" fill="#faf5e8">
        <animate attributeName="ry" values="5;6;5" dur="0.8s" repeatCount="indefinite"/>
      </ellipse>
      <!-- Candle body -->
      <rect x="10" y="18" width="10" height="25" fill="#e0d4b8" stroke="#a8864f" stroke-width="1"/>
      <rect x="10" y="18" width="10" height="3" fill="#c9a961"/>
      <!-- Melted wax drip -->
      <path d="M 13,43 Q 12,45 13,47 Q 14,45 13,43" fill="#e0d4b8"/>
    </svg>
  `;
  
  // Style the candle
  const style = document.createElement('style');
  style.textContent = `
    #floating-candle {
      position: fixed;
      pointer-events: none;
      z-index: 9999;
      opacity: 0;
      transition: opacity 0.3s ease;
      filter: drop-shadow(0 0 15px rgba(201, 169, 97, 0.6));
    }
    
    body:hover #floating-candle {
      opacity: 0.8;
    }
  `;
  
  document.head.appendChild(style);
  document.body.appendChild(candle);
  
  let mouseX = 0;
  let mouseY = 0;
  let candleX = 0;
  let candleY = 0;
  
  // Track mouse position
  document.addEventListener('mousemove', (e) => {
    mouseX = e.clientX;
    mouseY = e.clientY;
  });
  
  // Smooth follow animation
  function updateCandle() {
    // Ease towards mouse position
    const ease = 0.1;
    candleX += (mouseX - candleX) * ease;
    candleY += (mouseY - candleY) * ease;
    
    // Add slight wobble
    const wobble = Math.sin(Date.now() * 0.003) * 2;
    
    // Position candle slightly offset from cursor
    candle.style.left = `${candleX - 15}px`;
    candle.style.top = `${candleY - 60 + wobble}px`;
    
    requestAnimationFrame(updateCandle);
  }
  
  updateCandle();
})();
