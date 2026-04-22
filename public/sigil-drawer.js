// Interactive sigil drawing canvas
(function() {
  const canvas = document.getElementById('sigil-canvas');
  if (!canvas) return;
  
  const ctx = canvas.getContext('2d');
  let isDrawing = false;
  let symmetryMode = false;
  let goldMode = false;
  
  // Set canvas size
  function resizeCanvas() {
    const container = canvas.parentElement;
    const maxWidth = Math.min(600, container.clientWidth - 40);
    canvas.width = maxWidth;
    canvas.height = maxWidth;
    drawGrid();
  }
  
  resizeCanvas();
  window.addEventListener('resize', resizeCanvas);
  
  // Draw subtle grid
  function drawGrid() {
    ctx.strokeStyle = 'rgba(90, 72, 56, 0.1)';
    ctx.lineWidth = 1;
    
    const size = canvas.width;
    const gridSize = 50;
    
    // Vertical lines
    for (let x = 0; x <= size; x += gridSize) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, size);
      ctx.stroke();
    }
    
    // Horizontal lines
    for (let y = 0; y <= size; y += gridSize) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(size, y);
      ctx.stroke();
    }
    
    // Center cross
    ctx.strokeStyle = 'rgba(201, 169, 97, 0.3)';
    ctx.lineWidth = 2;
    
    // Vertical center
    ctx.beginPath();
    ctx.moveTo(size / 2, 0);
    ctx.lineTo(size / 2, size);
    ctx.stroke();
    
    // Horizontal center
    ctx.beginPath();
    ctx.moveTo(0, size / 2);
    ctx.lineTo(size, size / 2);
    ctx.stroke();
    
    // Center circle
    ctx.beginPath();
    ctx.arc(size / 2, size / 2, 10, 0, Math.PI * 2);
    ctx.stroke();
  }
  
  // Get position relative to canvas
  function getPosition(event) {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    
    if (event.touches && event.touches[0]) {
      return {
        x: (event.touches[0].clientX - rect.left) * scaleX,
        y: (event.touches[0].clientY - rect.top) * scaleY
      };
    }
    
    return {
      x: (event.clientX - rect.left) * scaleX,
      y: (event.clientY - rect.top) * scaleY
    };
  }
  
  // Draw a point with optional symmetry
  function drawPoint(x, y) {
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    
    ctx.strokeStyle = goldMode ? '#c9a961' : '#5a4838';
    ctx.lineWidth = goldMode ? 4 : 2;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    
    // Draw the primary stroke
    ctx.lineTo(x, y);
    ctx.stroke();
    
    if (symmetryMode) {
      // Mirror across vertical axis
      const mirrorX = centerX - (x - centerX);
      ctx.beginPath();
      ctx.moveTo(mirrorX, y);
      ctx.lineTo(mirrorX, y);
      ctx.stroke();
      
      // Mirror across horizontal axis
      const mirrorY = centerY - (y - centerY);
      ctx.beginPath();
      ctx.moveTo(x, mirrorY);
      ctx.lineTo(x, mirrorY);
      ctx.stroke();
      
      // Mirror across both axes
      ctx.beginPath();
      ctx.moveTo(mirrorX, mirrorY);
      ctx.lineTo(mirrorX, mirrorY);
      ctx.stroke();
    }
  }
  
  // Start drawing
  function startDrawing(event) {
    event.preventDefault();
    isDrawing = true;
    const pos = getPosition(event);
    ctx.beginPath();
    ctx.moveTo(pos.x, pos.y);
  }
  
  // Draw
  function draw(event) {
    if (!isDrawing) return;
    event.preventDefault();
    const pos = getPosition(event);
    drawPoint(pos.x, pos.y);
  }
  
  // Stop drawing
  function stopDrawing(event) {
    if (!isDrawing) return;
    event.preventDefault();
    isDrawing = false;
    ctx.beginPath();
  }
  
  // Event listeners for mouse
  canvas.addEventListener('mousedown', startDrawing);
  canvas.addEventListener('mousemove', draw);
  canvas.addEventListener('mouseup', stopDrawing);
  canvas.addEventListener('mouseleave', stopDrawing);
  
  // Event listeners for touch
  canvas.addEventListener('touchstart', startDrawing);
  canvas.addEventListener('touchmove', draw);
  canvas.addEventListener('touchend', stopDrawing);
  canvas.addEventListener('touchcancel', stopDrawing);
  
  // Clear button
  const clearBtn = document.getElementById('clear-btn');
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      drawGrid();
    });
  }
  
  // Symmetry toggle
  const symmetryBtn = document.getElementById('symmetry-btn');
  if (symmetryBtn) {
    symmetryBtn.addEventListener('click', () => {
      symmetryMode = !symmetryMode;
      symmetryBtn.style.background = symmetryMode ? '#c9a961' : '';
      symmetryBtn.style.color = symmetryMode ? '#2a1810' : '';
    });
  }
  
  // Gold mode toggle
  const goldBtn = document.getElementById('gold-btn');
  if (goldBtn) {
    goldBtn.addEventListener('click', () => {
      goldMode = !goldMode;
      goldBtn.style.background = goldMode ? '#c9a961' : '';
      goldBtn.style.color = goldMode ? '#2a1810' : '';
    });
  }
  
  // Initial grid
  drawGrid();
})();
