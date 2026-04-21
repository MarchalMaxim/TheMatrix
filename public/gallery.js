// Random SVG Art Generator
const dynamicContainer = document.getElementById('dynamic-art-container');
const generateBtn = document.getElementById('generate-btn');

// Color palettes for random generation
const colorPalettes = [
  ['#ff1493', '#00ffff', '#ffd700', '#ff00ff'],
  ['#ff0066', '#00ff00', '#0066ff', '#ffff00'],
  ['#ff6600', '#00ffff', '#ff00ff', '#66ff00'],
  ['#ff1493', '#ffd700', '#00ff00', '#0066ff'],
  ['#ff00ff', '#00ffff', '#ff6600', '#00ff00'],
];

function getRandomColor(palette) {
  return palette[Math.floor(Math.random() * palette.length)];
}

function getRandomPalette() {
  return colorPalettes[Math.floor(Math.random() * colorPalettes.length)];
}

function random(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

// Generator functions for different art styles
function generateCircleArt() {
  const palette = getRandomPalette();
  const numCircles = random(5, 12);
  let circles = '';
  
  for (let i = 0; i < numCircles; i++) {
    const cx = random(50, 250);
    const cy = random(50, 250);
    const r = random(10, 60);
    const color = getRandomColor(palette);
    const opacity = (Math.random() * 0.5 + 0.4).toFixed(2);
    circles += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${color}" opacity="${opacity}" />`;
  }
  
  return `
    <svg viewBox="0 0 300 300" xmlns="http://www.w3.org/2000/svg">
      <rect x="0" y="0" width="300" height="300" fill="#0a0a0a" />
      ${circles}
    </svg>
  `;
}

function generatePolygonArt() {
  const palette = getRandomPalette();
  const numPolygons = random(3, 8);
  let polygons = '';
  
  for (let i = 0; i < numPolygons; i++) {
    const sides = random(3, 8);
    const cx = 150;
    const cy = 150;
    const radius = random(50, 140 - i * 15);
    let points = [];
    
    for (let j = 0; j < sides; j++) {
      const angle = (j * 2 * Math.PI) / sides;
      const x = cx + radius * Math.cos(angle);
      const y = cy + radius * Math.sin(angle);
      points.push(`${x.toFixed(2)},${y.toFixed(2)}`);
    }
    
    const color = getRandomColor(palette);
    const strokeWidth = random(1, 4);
    polygons += `<polygon points="${points.join(' ')}" fill="none" stroke="${color}" stroke-width="${strokeWidth}" />`;
  }
  
  return `
    <svg viewBox="0 0 300 300" xmlns="http://www.w3.org/2000/svg">
      <rect x="0" y="0" width="300" height="300" fill="#1a1a2e" />
      ${polygons}
      <circle cx="150" cy="150" r="10" fill="${getRandomColor(palette)}" />
    </svg>
  `;
}

function generateLineArt() {
  const palette = getRandomPalette();
  const numLines = random(10, 25);
  let lines = '';
  
  for (let i = 0; i < numLines; i++) {
    const x1 = random(0, 300);
    const y1 = random(0, 300);
    const x2 = random(0, 300);
    const y2 = random(0, 300);
    const color = getRandomColor(palette);
    const strokeWidth = random(1, 4);
    const opacity = (Math.random() * 0.5 + 0.3).toFixed(2);
    lines += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="${strokeWidth}" opacity="${opacity}" />`;
  }
  
  return `
    <svg viewBox="0 0 300 300" xmlns="http://www.w3.org/2000/svg">
      <rect x="0" y="0" width="300" height="300" fill="#0f0f1e" />
      ${lines}
    </svg>
  `;
}

function generateRectArt() {
  const palette = getRandomPalette();
  const numRects = random(8, 20);
  let rects = '';
  
  for (let i = 0; i < numRects; i++) {
    const x = random(0, 250);
    const y = random(0, 250);
    const width = random(20, 100);
    const height = random(20, 100);
    const color = getRandomColor(palette);
    const opacity = (Math.random() * 0.6 + 0.3).toFixed(2);
    const rotation = random(0, 360);
    rects += `<rect x="${x}" y="${y}" width="${width}" height="${height}" fill="${color}" opacity="${opacity}" transform="rotate(${rotation} ${x + width/2} ${y + height/2})" />`;
  }
  
  return `
    <svg viewBox="0 0 300 300" xmlns="http://www.w3.org/2000/svg">
      <rect x="0" y="0" width="300" height="300" fill="#16213e" />
      ${rects}
    </svg>
  `;
}

function generateSpiralArt() {
  const palette = getRandomPalette();
  const numSpirals = random(2, 5);
  let spirals = '';
  
  for (let s = 0; s < numSpirals; s++) {
    let points = '';
    const centerX = 150;
    const centerY = 150;
    const maxRadius = 100 - s * 20;
    const turns = random(3, 6);
    const steps = 100;
    
    for (let i = 0; i <= steps; i++) {
      const angle = (i / steps) * turns * 2 * Math.PI;
      const radius = (i / steps) * maxRadius;
      const x = centerX + radius * Math.cos(angle);
      const y = centerY + radius * Math.sin(angle);
      points += `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)} `;
    }
    
    const color = getRandomColor(palette);
    const strokeWidth = random(1, 3);
    spirals += `<path d="${points}" fill="none" stroke="${color}" stroke-width="${strokeWidth}" />`;
  }
  
  return `
    <svg viewBox="0 0 300 300" xmlns="http://www.w3.org/2000/svg">
      <rect x="0" y="0" width="300" height="300" fill="#000033" />
      ${spirals}
      <circle cx="150" cy="150" r="5" fill="${getRandomColor(palette)}" />
    </svg>
  `;
}

function generateWaveArt() {
  const palette = getRandomPalette();
  const numWaves = random(4, 10);
  let waves = '';
  
  for (let i = 0; i < numWaves; i++) {
    const y = 50 + i * 20;
    const amplitude = random(10, 40);
    const frequency = random(2, 5);
    let path = `M 0 ${y} `;
    
    for (let x = 0; x <= 300; x += 10) {
      const yPos = y + amplitude * Math.sin((x / 300) * frequency * 2 * Math.PI);
      path += `L ${x} ${yPos} `;
    }
    
    const color = getRandomColor(palette);
    const strokeWidth = random(1, 3);
    waves += `<path d="${path}" fill="none" stroke="${color}" stroke-width="${strokeWidth}" />`;
  }
  
  return `
    <svg viewBox="0 0 300 300" xmlns="http://www.w3.org/2000/svg">
      <rect x="0" y="0" width="300" height="300" fill="#0a0a0a" />
      ${waves}
    </svg>
  `;
}

function generateStarBurstArt() {
  const palette = getRandomPalette();
  const numRays = random(12, 24);
  let rays = '';
  
  const centerX = 150;
  const centerY = 150;
  
  for (let i = 0; i < numRays; i++) {
    const angle = (i / numRays) * 2 * Math.PI;
    const length = random(60, 120);
    const x2 = centerX + length * Math.cos(angle);
    const y2 = centerY + length * Math.sin(angle);
    const color = getRandomColor(palette);
    const strokeWidth = random(1, 4);
    rays += `<line x1="${centerX}" y1="${centerY}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="${strokeWidth}" />`;
  }
  
  return `
    <svg viewBox="0 0 300 300" xmlns="http://www.w3.org/2000/svg">
      <rect x="0" y="0" width="300" height="300" fill="#1a1a2e" />
      ${rays}
      <circle cx="150" cy="150" r="20" fill="${getRandomColor(palette)}" />
    </svg>
  `;
}

const artGenerators = [
  { name: 'Random Circles', generator: generateCircleArt },
  { name: 'Polygon Dreams', generator: generatePolygonArt },
  { name: 'Line Chaos', generator: generateLineArt },
  { name: 'Rectangle Matrix', generator: generateRectArt },
  { name: 'Spiral Galaxy', generator: generateSpiralArt },
  { name: 'Wave Patterns', generator: generateWaveArt },
  { name: 'Star Burst', generator: generateStarBurstArt },
];

function generateRandomArt() {
  const art = artGenerators[Math.floor(Math.random() * artGenerators.length)];
  const svgContent = art.generator();
  
  const artPiece = document.createElement('div');
  artPiece.className = 'art-piece';
  artPiece.innerHTML = `
    ${svgContent}
    <p class="art-caption">${art.name} #${random(1000, 9999)}</p>
  `;
  
  return artPiece;
}

function addNewArt() {
  const artPiece = generateRandomArt();
  dynamicContainer.appendChild(artPiece);
  
  // Scroll into view
  artPiece.scrollIntoView({ behavior: 'smooth', block: 'center' });
  
  // Add entrance animation
  artPiece.style.opacity = '0';
  artPiece.style.transform = 'scale(0.5) rotate(-15deg)';
  setTimeout(() => {
    artPiece.style.transition = 'all 0.8s cubic-bezier(0.68, -0.55, 0.265, 1.55)';
    artPiece.style.opacity = '1';
    artPiece.style.transform = 'scale(1) rotate(0deg)';
  }, 50);
}

// Generate 3 random pieces on load
for (let i = 0; i < 3; i++) {
  addNewArt();
}

// Button to generate more
generateBtn.addEventListener('click', () => {
  addNewArt();
});

// Auto-generate a new piece every 10 seconds
setInterval(() => {
  addNewArt();
}, 10000);
