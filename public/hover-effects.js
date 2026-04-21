// EXTREMELY HOVERY EFFECTS for ALL buttons and interactive elements

// Add extra hover effects to all buttons
document.addEventListener('DOMContentLoaded', () => {
  // Enhanced button hover tracking
  const buttons = document.querySelectorAll('button, .festive-link, .nav-link');
  
  buttons.forEach(button => {
    // Add sparkle effect on hover
    button.addEventListener('mouseenter', (e) => {
      createSparkles(e.target);
    });
    
    // Add ripple effect on click
    button.addEventListener('click', (e) => {
      createRipple(e);
    });
  });
  
  // Add hover effect to bright divs to make them EXTRA hovery
  const brightDivs = document.querySelectorAll('.bright-div');
  
  brightDivs.forEach(div => {
    div.addEventListener('mouseenter', () => {
      div.style.animation = 'none';
      setTimeout(() => {
        div.style.animation = 'megaHover 0.5s ease forwards';
      }, 10);
    });
    
    div.addEventListener('mouseleave', () => {
      div.style.animation = 'brightPulse 2s ease-in-out infinite';
    });
  });
  
  // Add CSS for mega hover animation
  const style = document.createElement('style');
  style.textContent = `
    @keyframes megaHover {
      0% {
        transform: scale(1) rotate(0deg);
      }
      50% {
        transform: scale(2) rotate(180deg);
      }
      100% {
        transform: scale(1.8) rotate(360deg);
      }
    }
    
    @keyframes sparkle {
      0% {
        opacity: 1;
        transform: translate(0, 0) scale(0);
      }
      50% {
        opacity: 1;
        transform: translate(var(--tx), var(--ty)) scale(1);
      }
      100% {
        opacity: 0;
        transform: translate(calc(var(--tx) * 2), calc(var(--ty) * 2)) scale(0);
      }
    }
    
    .sparkle {
      position: absolute;
      pointer-events: none;
      z-index: 10000;
      animation: sparkle 1s ease-out forwards;
    }
    
    @keyframes ripple {
      0% {
        transform: scale(0);
        opacity: 1;
      }
      100% {
        transform: scale(4);
        opacity: 0;
      }
    }
    
    .ripple {
      position: absolute;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.5);
      pointer-events: none;
      animation: ripple 0.8s ease-out;
    }
  `;
  document.head.appendChild(style);
});

// Create sparkle effect
function createSparkles(element) {
  const rect = element.getBoundingClientRect();
  const numSparkles = 8;
  
  for (let i = 0; i < numSparkles; i++) {
    const sparkle = document.createElement('div');
    sparkle.className = 'sparkle';
    sparkle.textContent = ['✨', '⭐', '💫', '🌟'][Math.floor(Math.random() * 4)];
    sparkle.style.fontSize = `${Math.random() * 20 + 15}px`;
    sparkle.style.left = `${rect.left + rect.width / 2}px`;
    sparkle.style.top = `${rect.top + rect.height / 2}px`;
    
    const angle = (i / numSparkles) * Math.PI * 2;
    const distance = 50 + Math.random() * 30;
    const tx = Math.cos(angle) * distance;
    const ty = Math.sin(angle) * distance;
    
    sparkle.style.setProperty('--tx', `${tx}px`);
    sparkle.style.setProperty('--ty', `${ty}px`);
    
    document.body.appendChild(sparkle);
    
    setTimeout(() => {
      sparkle.remove();
    }, 1000);
  }
}

// Create ripple effect
function createRipple(event) {
  const button = event.currentTarget;
  const rect = button.getBoundingClientRect();
  
  const ripple = document.createElement('span');
  ripple.className = 'ripple';
  const size = Math.max(rect.width, rect.height);
  ripple.style.width = ripple.style.height = `${size}px`;
  ripple.style.left = `${event.clientX - rect.left - size / 2}px`;
  ripple.style.top = `${event.clientY - rect.top - size / 2}px`;
  
  button.style.position = 'relative';
  button.style.overflow = 'hidden';
  button.appendChild(ripple);
  
  setTimeout(() => {
    ripple.remove();
  }, 800);
}

// Add mouse trail effect
let mouseTrail = [];
const maxTrailLength = 20;

document.addEventListener('mousemove', (e) => {
  // Only add trail on the festive side or if over interactive elements
  const rightSide = document.querySelector('.right-side');
  if (!rightSide) return;
  
  const rightRect = rightSide.getBoundingClientRect();
  const isInFestiveSide = e.clientX >= rightRect.left && e.clientX <= rightRect.right;
  
  if (isInFestiveSide) {
    const trail = document.createElement('div');
    trail.style.position = 'fixed';
    trail.style.left = `${e.clientX}px`;
    trail.style.top = `${e.clientY}px`;
    trail.style.width = '10px';
    trail.style.height = '10px';
    trail.style.borderRadius = '50%';
    trail.style.background = `hsl(${Math.random() * 360}, 100%, 70%)`;
    trail.style.pointerEvents = 'none';
    trail.style.zIndex = '9999';
    trail.style.transform = 'translate(-50%, -50%)';
    trail.style.transition = 'all 0.5s ease-out';
    trail.style.opacity = '0.8';
    
    document.body.appendChild(trail);
    mouseTrail.push(trail);
    
    setTimeout(() => {
      trail.style.opacity = '0';
      trail.style.transform = 'translate(-50%, -50%) scale(0)';
    }, 50);
    
    setTimeout(() => {
      trail.remove();
    }, 550);
    
    if (mouseTrail.length > maxTrailLength) {
      const old = mouseTrail.shift();
      if (old && old.parentNode) {
        old.remove();
      }
    }
  }
});

// Add floating emojis on festive side
function createFloatingEmoji() {
  const rightSide = document.querySelector('.right-side');
  if (!rightSide) return;
  
  const emojis = ['✨', '🎉', '🎊', '⭐', '🌟', '💫', '🎪', '🎨', '💡', '🦋'];
  const emoji = document.createElement('div');
  emoji.textContent = emojis[Math.floor(Math.random() * emojis.length)];
  emoji.style.position = 'absolute';
  emoji.style.fontSize = `${Math.random() * 30 + 20}px`;
  emoji.style.left = `${Math.random() * 100}%`;
  emoji.style.top = '100%';
  emoji.style.pointerEvents = 'none';
  emoji.style.zIndex = '5';
  emoji.style.opacity = '0.7';
  emoji.style.transition = 'all 8s linear';
  
  rightSide.appendChild(emoji);
  
  setTimeout(() => {
    emoji.style.top = '-10%';
    emoji.style.transform = `rotate(${Math.random() * 720 - 360}deg)`;
    emoji.style.opacity = '0';
  }, 50);
  
  setTimeout(() => {
    emoji.remove();
  }, 8000);
}

// Spawn floating emojis periodically on the festive side
setInterval(createFloatingEmoji, 2000);

// Make notes extra bouncy on hover
document.addEventListener('DOMContentLoaded', () => {
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach((node) => {
        if (node.classList && node.classList.contains('note')) {
          enhanceNoteHover(node);
        }
      });
    });
  });
  
  const canvas = document.getElementById('canvas');
  if (canvas) {
    observer.observe(canvas, { childList: true });
    
    // Enhance existing notes
    document.querySelectorAll('.note').forEach(enhanceNoteHover);
  }
});

function enhanceNoteHover(note) {
  note.addEventListener('mouseenter', () => {
    note.style.transition = 'all 0.3s cubic-bezier(0.68, -0.55, 0.265, 1.55)';
    note.style.transform = 'scale(1.15) rotate(5deg) translateY(-10px)';
    note.style.zIndex = '1000';
  });
  
  note.addEventListener('mouseleave', () => {
    note.style.transform = 'scale(1) rotate(0deg) translateY(0)';
    note.style.zIndex = '';
  });
}

// Add pulsating glow to buttons
setInterval(() => {
  const buttons = document.querySelectorAll('button:not(:disabled)');
  buttons.forEach(button => {
    button.style.transition = 'filter 0.3s ease';
    button.style.filter = 'brightness(1.3) saturate(1.5)';
    setTimeout(() => {
      button.style.filter = 'brightness(1) saturate(1)';
    }, 300);
  });
}, 3000);

console.log('🎉 EXTREME HOVER EFFECTS ACTIVATED! 🎉');
