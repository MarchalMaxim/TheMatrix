// Radar sweep animation showing note positions
(function() {
  const canvas = document.getElementById('radar-canvas');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  const centerX = canvas.width / 2;
  const centerY = canvas.height / 2;
  const radius = canvas.width / 2 - 10;
  
  let angle = 0;
  const sweepSpeed = 0.02;

  function drawRadar() {
    // Clear with fade effect
    ctx.fillStyle = 'rgba(26, 26, 26, 0.1)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Draw concentric circles
    ctx.strokeStyle = 'rgba(74, 74, 74, 0.5)';
    ctx.lineWidth = 1;
    for (let i = 1; i <= 3; i++) {
      ctx.beginPath();
      ctx.arc(centerX, centerY, (radius / 3) * i, 0, Math.PI * 2);
      ctx.stroke();
    }

    // Draw crosshairs
    ctx.beginPath();
    ctx.moveTo(centerX, centerY - radius);
    ctx.lineTo(centerX, centerY + radius);
    ctx.moveTo(centerX - radius, centerY);
    ctx.lineTo(centerX + radius, centerY);
    ctx.stroke();

    // Draw sweep line
    const sweepEndX = centerX + Math.cos(angle) * radius;
    const sweepEndY = centerY + Math.sin(angle) * radius;
    
    // Gradient for sweep
    const gradient = ctx.createLinearGradient(centerX, centerY, sweepEndX, sweepEndY);
    gradient.addColorStop(0, 'rgba(0, 255, 102, 0)');
    gradient.addColorStop(0.5, 'rgba(0, 255, 102, 0.3)');
    gradient.addColorStop(1, 'rgba(0, 255, 102, 0.8)');
    
    ctx.strokeStyle = gradient;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.lineTo(sweepEndX, sweepEndY);
    ctx.stroke();

    // Draw sweep arc trail
    ctx.strokeStyle = 'rgba(0, 255, 102, 0.2)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, angle - Math.PI / 6, angle);
    ctx.stroke();

    // Draw note blips
    const notesCanvas = document.getElementById('canvas');
    if (notesCanvas) {
      const notes = notesCanvas.querySelectorAll('.note');
      const canvasRect = notesCanvas.getBoundingClientRect();
      const maxX = canvasRect.width;
      const maxY = canvasRect.height;

      notes.forEach(note => {
        const noteX = parseFloat(note.style.left) || 0;
        const noteY = parseFloat(note.style.top) || 0;
        
        // Map to radar coordinates
        const radarX = centerX + ((noteX / maxX) - 0.5) * radius * 1.8;
        const radarY = centerY + ((noteY / maxY) - 0.5) * radius * 1.8;
        
        // Check if within sweep angle (with tolerance)
        const noteAngle = Math.atan2(radarY - centerY, radarX - centerX);
        const angleDiff = Math.abs(((noteAngle - angle + Math.PI) % (2 * Math.PI)) - Math.PI);
        
        if (angleDiff < Math.PI / 8) {
          // Draw blip
          const blipOpacity = 1 - (angleDiff / (Math.PI / 8));
          ctx.fillStyle = `rgba(255, 204, 0, ${blipOpacity * 0.8})`;
          ctx.beginPath();
          ctx.arc(radarX, radarY, 3, 0, Math.PI * 2);
          ctx.fill();
          
          // Draw blip glow
          ctx.fillStyle = `rgba(255, 204, 0, ${blipOpacity * 0.3})`;
          ctx.beginPath();
          ctx.arc(radarX, radarY, 6, 0, Math.PI * 2);
          ctx.fill();
        }
      });
    }

    // Update angle
    angle += sweepSpeed;
    if (angle > Math.PI * 2) {
      angle -= Math.PI * 2;
    }

    requestAnimationFrame(drawRadar);
  }

  drawRadar();
})();
