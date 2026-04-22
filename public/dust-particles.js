// Floating dust particles effect for the manuscript aesthetic
(function() {
  const canvas = document.getElementById('dust-canvas');
  if (!canvas) return;
  
  const ctx = canvas.getContext('2d');
  let width, height;
  
  function resizeCanvas() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  }
  
  resizeCanvas();
  window.addEventListener('resize', resizeCanvas);
  
  // Dust particle class
  class DustParticle {
    constructor() {
      this.reset();
      this.y = Math.random() * height;
    }
    
    reset() {
      this.x = Math.random() * width;
      this.y = -10;
      this.size = Math.random() * 2 + 0.5;
      this.speedY = Math.random() * 0.3 + 0.1;
      this.speedX = Math.random() * 0.4 - 0.2;
      this.opacity = Math.random() * 0.3 + 0.1;
      this.wobble = Math.random() * 0.5;
      this.wobbleSpeed = Math.random() * 0.02 + 0.01;
    }
    
    update() {
      this.y += this.speedY;
      this.x += this.speedX + Math.sin(this.y * this.wobbleSpeed) * this.wobble;
      
      if (this.y > height + 10) {
        this.reset();
      }
      
      if (this.x < -10 || this.x > width + 10) {
        this.x = Math.random() * width;
      }
    }
    
    draw() {
      ctx.fillStyle = `rgba(90, 72, 56, ${this.opacity})`;
      ctx.beginPath();
      ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  
  // Create particles
  const particleCount = 80;
  const particles = [];
  
  for (let i = 0; i < particleCount; i++) {
    particles.push(new DustParticle());
  }
  
  // Animation loop
  function animate() {
    ctx.clearRect(0, 0, width, height);
    
    particles.forEach(particle => {
      particle.update();
      particle.draw();
    });
    
    requestAnimationFrame(animate);
  }
  
  animate();
})();
