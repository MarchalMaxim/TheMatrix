// Floating butterflies and leaves animation
const canvas = document.getElementById('floating-particles');
if (canvas) {
  const ctx = canvas.getContext('2d');
  let width = canvas.width = window.innerWidth;
  let height = canvas.height = window.innerHeight;

  // Particle types: butterfly and leaf
  class Particle {
    constructor() {
      this.reset();
      this.y = Math.random() * height; // Start at random position initially
    }

    reset() {
      this.x = Math.random() * width;
      this.y = -20;
      this.speed = 0.3 + Math.random() * 0.8;
      this.size = 12 + Math.random() * 16;
      this.type = Math.random() > 0.5 ? 'butterfly' : 'leaf';
      this.angle = Math.random() * Math.PI * 2;
      this.swaySpeed = 0.02 + Math.random() * 0.03;
      this.swayAmount = 15 + Math.random() * 25;
      this.rotation = Math.random() * Math.PI * 2;
      this.rotationSpeed = (Math.random() - 0.5) * 0.05;
      
      // Color variations
      if (this.type === 'butterfly') {
        const colors = [
          { r: 200, g: 184, b: 219 }, // lavender
          { r: 244, g: 194, b: 167 }, // peach
          { r: 156, g: 175, b: 136 }, // sage
        ];
        this.color = colors[Math.floor(Math.random() * colors.length)];
      } else {
        const colors = [
          { r: 156, g: 175, b: 136 }, // sage
          { r: 122, g: 143, b: 111 }, // sage dark
          { r: 139, g: 115, b: 85 },  // soft brown
        ];
        this.color = colors[Math.floor(Math.random() * colors.length)];
      }
    }

    update() {
      this.y += this.speed;
      this.angle += this.swaySpeed;
      this.rotation += this.rotationSpeed;
      
      // Sway side to side
      const sway = Math.sin(this.angle) * this.swayAmount;
      this.currentX = this.x + sway;

      // Reset when off screen
      if (this.y > height + 20) {
        this.reset();
      }
    }

    draw() {
      ctx.save();
      ctx.translate(this.currentX, this.y);
      ctx.rotate(this.rotation);
      ctx.globalAlpha = 0.6 + Math.sin(this.angle * 2) * 0.2;

      const { r, g, b } = this.color;
      ctx.fillStyle = `rgb(${r}, ${g}, ${b})`;
      ctx.strokeStyle = `rgba(${r * 0.7}, ${g * 0.7}, ${b * 0.7}, 0.8)`;
      ctx.lineWidth = 1;

      if (this.type === 'butterfly') {
        // Draw butterfly with two wings
        ctx.beginPath();
        // Left wing
        ctx.moveTo(0, 0);
        ctx.bezierCurveTo(
          -this.size * 0.6, -this.size * 0.5,
          -this.size * 0.8, -this.size * 0.2,
          -this.size * 0.4, 0
        );
        ctx.bezierCurveTo(
          -this.size * 0.8, this.size * 0.2,
          -this.size * 0.6, this.size * 0.5,
          0, 0
        );
        ctx.fill();
        ctx.stroke();

        // Right wing
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.bezierCurveTo(
          this.size * 0.6, -this.size * 0.5,
          this.size * 0.8, -this.size * 0.2,
          this.size * 0.4, 0
        );
        ctx.bezierCurveTo(
          this.size * 0.8, this.size * 0.2,
          this.size * 0.6, this.size * 0.5,
          0, 0
        );
        ctx.fill();
        ctx.stroke();

        // Body
        ctx.fillStyle = `rgba(${r * 0.6}, ${g * 0.6}, ${b * 0.6}, 0.9)`;
        ctx.beginPath();
        ctx.ellipse(0, 0, this.size * 0.1, this.size * 0.4, 0, 0, Math.PI * 2);
        ctx.fill();
      } else {
        // Draw leaf
        ctx.beginPath();
        ctx.moveTo(0, -this.size * 0.5);
        ctx.bezierCurveTo(
          this.size * 0.4, -this.size * 0.3,
          this.size * 0.5, this.size * 0.2,
          0, this.size * 0.5
        );
        ctx.bezierCurveTo(
          -this.size * 0.5, this.size * 0.2,
          -this.size * 0.4, -this.size * 0.3,
          0, -this.size * 0.5
        );
        ctx.fill();
        ctx.stroke();

        // Leaf vein
        ctx.beginPath();
        ctx.moveTo(0, -this.size * 0.5);
        ctx.lineTo(0, this.size * 0.5);
        ctx.strokeStyle = `rgba(${r * 0.6}, ${g * 0.6}, ${b * 0.6}, 0.5)`;
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      ctx.restore();
    }
  }

  // Create particles
  const particles = [];
  const particleCount = 20;
  for (let i = 0; i < particleCount; i++) {
    particles.push(new Particle());
  }

  function animate() {
    ctx.clearRect(0, 0, width, height);
    
    particles.forEach(particle => {
      particle.update();
      particle.draw();
    });

    requestAnimationFrame(animate);
  }

  animate();

  // Handle resize
  window.addEventListener('resize', () => {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  });
}
