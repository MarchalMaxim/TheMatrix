// Military-themed visual effects for the main page

// Add some typewriter effect to certain elements on load
function typewriterEffect(element, text, speed = 50) {
  if (!element) return;
  element.textContent = '';
  let i = 0;
  
  function type() {
    if (i < text.length) {
      element.textContent += text.charAt(i);
      i++;
      setTimeout(type, speed);
    }
  }
  
  type();
}

// Add alert blink to countdown when under 1 hour
setInterval(() => {
  const countdown = document.getElementById('generation-countdown');
  if (!countdown) return;
  
  const text = countdown.textContent;
  const parts = text.split(':');
  
  if (parts.length >= 2) {
    const hours = parseInt(parts[0]) || 0;
    const minutes = parseInt(parts[1]) || 0;
    
    if (hours === 0 && minutes < 60) {
      countdown.classList.add('alert-text');
    }
  }
}, 5000);

// Random telegraph/morse code sound simulator (visual only - no actual sound)
// Creates flashing effect like old military telegraph
function createTelegraphEffect() {
  const header = document.querySelector('.command-header');
  if (!header) return;
  
  setInterval(() => {
    if (Math.random() > 0.95) {
      header.style.boxShadow = '0 10px 40px rgba(0, 0, 0, 0.6), inset 0 0 100px rgba(255, 215, 0, 0.2)';
      setTimeout(() => {
        header.style.boxShadow = '0 10px 40px rgba(0, 0, 0, 0.6), inset 0 0 100px rgba(0, 0, 0, 0.3)';
      }, 100);
    }
  }, 2000);
}

// Simulate old military document stamp effect on notes
function addStampEffect() {
  const canvas = document.getElementById('canvas');
  if (!canvas) return;
  
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach((node) => {
        if (node.classList && node.classList.contains('note')) {
          // Add slight delay for stamp effect
          setTimeout(() => {
            const stamp = node.querySelector('.note-stamp');
            if (stamp) {
              stamp.style.transition = 'opacity 0.3s ease-in';
              stamp.style.opacity = '0.5';
            }
          }, 300);
        }
      });
    });
  });
  
  observer.observe(canvas, { childList: true });
}

// Add military grid animation to operations board
function animateGridLines() {
  const grid = document.querySelector('.grid-overlay');
  if (!grid) return;
  
  let opacity = 0.15;
  let direction = 1;
  
  setInterval(() => {
    opacity += direction * 0.01;
    if (opacity >= 0.25 || opacity <= 0.1) {
      direction *= -1;
    }
    
    grid.style.opacity = opacity;
  }, 100);
}

// Initialize effects when DOM is loaded
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initEffects);
} else {
  initEffects();
}

function initEffects() {
  createTelegraphEffect();
  addStampEffect();
  animateGridLines();
  
  // Add hover sound effect simulation (visual pulse) to buttons
  const buttons = document.querySelectorAll('.deploy-button, .nav-btn');
  buttons.forEach(btn => {
    btn.addEventListener('mouseenter', () => {
      btn.style.transition = 'all 0.1s ease';
    });
  });
}

// Konami code easter egg - changes all text to full German
let konamiCode = [];
const konamiSequence = ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'b', 'a'];

document.addEventListener('keydown', (e) => {
  konamiCode.push(e.key);
  konamiCode = konamiCode.slice(-konamiSequence.length);
  
  if (konamiCode.join(',') === konamiSequence.join(',')) {
    // Easter egg activated!
    const toast = document.querySelector('.toast') || document.createElement('div');
    toast.className = 'toast';
    if (!document.body.contains(toast)) {
      document.body.appendChild(toast);
    }
    toast.textContent = 'GEHEIMCODE AKTIVIERT! / SECRET CODE ACTIVATED!';
    toast.classList.add('show');
    
    setTimeout(() => {
      toast.classList.remove('show');
    }, 3000);
    
    konamiCode = [];
  }
});
