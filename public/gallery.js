// Gallery generative art system
(function() {
  const generateBtn = document.getElementById('generate-btn');
  const dynamicContainer = document.getElementById('dynamic-art-container');

  if (!generateBtn || !dynamicContainer) return;

  // Generate random terminal-themed SVG art
  function generateRandomArt() {
    const type = Math.floor(Math.random() * 5);
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 300 300');
    svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');

    // Always start with black background
    const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    bg.setAttribute('x', '0');
    bg.setAttribute('y', '0');
    bg.setAttribute('width', '300');
    bg.setAttribute('height', '300');
    bg.setAttribute('fill', '#0a0e0a');
    svg.appendChild(bg);

    const colors = ['#00ff41', '#00ffff', '#ffff00', '#ff0040'];

    switch(type) {
      case 0: // Random circles
        for (let i = 0; i < 8; i++) {
          const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
          circle.setAttribute('cx', Math.random() * 300);
          circle.setAttribute('cy', Math.random() * 300);
          circle.setAttribute('r', Math.random() * 40 + 10);
          circle.setAttribute('fill', 'none');
          circle.setAttribute('stroke', colors[Math.floor(Math.random() * colors.length)]);
          circle.setAttribute('stroke-width', Math.random() * 3 + 1);
          circle.setAttribute('opacity', Math.random() * 0.5 + 0.5);
          svg.appendChild(circle);
        }
        return { svg, caption: 'RANDOM_CIRCLES_' + Math.floor(Math.random() * 9999) };

      case 1: // Grid pattern
        const gridSize = 20 + Math.floor(Math.random() * 20);
        for (let x = 0; x < 300; x += gridSize) {
          const line1 = document.createElementNS('http://www.w3.org/2000/svg', 'line');
          line1.setAttribute('x1', x);
          line1.setAttribute('y1', '0');
          line1.setAttribute('x2', x);
          line1.setAttribute('y2', '300');
          line1.setAttribute('stroke', colors[Math.floor(Math.random() * colors.length)]);
          line1.setAttribute('stroke-width', '1');
          line1.setAttribute('opacity', '0.3');
          svg.appendChild(line1);
        }
        for (let y = 0; y < 300; y += gridSize) {
          const line2 = document.createElementNS('http://www.w3.org/2000/svg', 'line');
          line2.setAttribute('x1', '0');
          line2.setAttribute('y1', y);
          line2.setAttribute('x2', '300');
          line2.setAttribute('y2', y);
          line2.setAttribute('stroke', colors[Math.floor(Math.random() * colors.length)]);
          line2.setAttribute('stroke-width', '1');
          line2.setAttribute('opacity', '0.3');
          svg.appendChild(line2);
        }
        const centerCircle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        centerCircle.setAttribute('cx', '150');
        centerCircle.setAttribute('cy', '150');
        centerCircle.setAttribute('r', '50');
        centerCircle.setAttribute('fill', colors[0]);
        centerCircle.setAttribute('opacity', '0.4');
        svg.appendChild(centerCircle);
        return { svg, caption: 'GRID_SYSTEM_' + gridSize };

      case 2: // Random polygons
        for (let i = 0; i < 5; i++) {
          const sides = 3 + Math.floor(Math.random() * 5);
          const points = [];
          const cx = 150;
          const cy = 150;
          const r = Math.random() * 80 + 30;
          for (let j = 0; j < sides; j++) {
            const angle = (j / sides) * Math.PI * 2;
            const x = cx + r * Math.cos(angle);
            const y = cy + r * Math.sin(angle);
            points.push(`${x},${y}`);
          }
          const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
          poly.setAttribute('points', points.join(' '));
          poly.setAttribute('fill', 'none');
          poly.setAttribute('stroke', colors[Math.floor(Math.random() * colors.length)]);
          poly.setAttribute('stroke-width', Math.random() * 3 + 1);
          poly.setAttribute('opacity', Math.random() * 0.5 + 0.4);
          svg.appendChild(poly);
        }
        return { svg, caption: 'POLY_CHAOS_' + Math.floor(Math.random() * 9999) };

      case 3: // Concentric shapes
        const shape = Math.random() > 0.5 ? 'circle' : 'rect';
        for (let i = 0; i < 6; i++) {
          const size = 200 - i * 30;
          const color = colors[i % colors.length];
          
          if (shape === 'circle') {
            const circ = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            circ.setAttribute('cx', '150');
            circ.setAttribute('cy', '150');
            circ.setAttribute('r', size / 2);
            circ.setAttribute('fill', 'none');
            circ.setAttribute('stroke', color);
            circ.setAttribute('stroke-width', '2');
            svg.appendChild(circ);
          } else {
            const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            rect.setAttribute('x', 150 - size / 2);
            rect.setAttribute('y', 150 - size / 2);
            rect.setAttribute('width', size);
            rect.setAttribute('height', size);
            rect.setAttribute('fill', 'none');
            rect.setAttribute('stroke', color);
            rect.setAttribute('stroke-width', '2');
            svg.appendChild(rect);
          }
        }
        return { svg, caption: 'CONCENTRIC_' + shape.toUpperCase() + 'S' };

      case 4: // Random lines
        for (let i = 0; i < 15; i++) {
          const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
          line.setAttribute('x1', Math.random() * 300);
          line.setAttribute('y1', Math.random() * 300);
          line.setAttribute('x2', Math.random() * 300);
          line.setAttribute('y2', Math.random() * 300);
          line.setAttribute('stroke', colors[Math.floor(Math.random() * colors.length)]);
          line.setAttribute('stroke-width', Math.random() * 3 + 1);
          line.setAttribute('opacity', Math.random() * 0.5 + 0.3);
          svg.appendChild(line);
        }
        return { svg, caption: 'LINE_NETWORK_' + Math.floor(Math.random() * 9999) };
    }
  }

  function addGeneratedArt() {
    const { svg, caption } = generateRandomArt();
    
    const piece = document.createElement('div');
    piece.className = 'art-piece';
    piece.style.animation = 'noteGlitchIn 0.8s ease';
    
    const frame = document.createElement('div');
    frame.className = 'art-frame';
    frame.appendChild(svg);
    
    const captionEl = document.createElement('p');
    captionEl.className = 'art-caption';
    captionEl.textContent = caption;
    
    piece.appendChild(frame);
    piece.appendChild(captionEl);
    
    dynamicContainer.appendChild(piece);

    // Show toast
    const toast = document.createElement('div');
    toast.className = 'toast show';
    toast.textContent = '> New art generated: ' + caption;
    document.body.appendChild(toast);
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 300);
    }, 2000);
  }

  // Generate button handler
  generateBtn.addEventListener('click', () => {
    addGeneratedArt();
  });

  // Generate one piece on load
  setTimeout(() => addGeneratedArt(), 500);
})();
