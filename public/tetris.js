// WW2-themed Tetris Game
const canvas = document.getElementById('game-canvas');
const ctx = canvas.getContext('2d');
const nextCanvas = document.getElementById('next-canvas');
const nextCtx = nextCanvas.getContext('2d');

const scoreEl = document.getElementById('score');
const linesEl = document.getElementById('lines');
const levelEl = document.getElementById('level');
const gameOverOverlay = document.getElementById('game-over-overlay');
const finalScoreEl = document.getElementById('final-score');
const restartBtn = document.getElementById('restart-btn');

const BLOCK_SIZE = 30;
const BOARD_WIDTH = 10;
const BOARD_HEIGHT = 20;

// WW2 military colors - feldgrau, olive, khaki variations
const COLORS = [
  '#4a5a3c', // olive
  '#4d5d53', // feldgrau
  '#6b7c5b', // olive-light
  '#c3b091', // khaki
  '#8b7355', // brown
  '#5a6b4a', // green-grey
  '#b7a57a', // tan
];

// Tetromino shapes (standard Tetris pieces)
const SHAPES = [
  [[1, 1, 1, 1]], // I
  [[1, 1], [1, 1]], // O
  [[0, 1, 0], [1, 1, 1]], // T
  [[1, 0, 0], [1, 1, 1]], // L
  [[0, 0, 1], [1, 1, 1]], // J
  [[0, 1, 1], [1, 1, 0]], // S
  [[1, 1, 0], [0, 1, 1]], // Z
];

let board = [];
let currentPiece = null;
let nextPiece = null;
let currentX = 0;
let currentY = 0;
let score = 0;
let lines = 0;
let level = 1;
let gameOver = false;
let paused = false;
let dropCounter = 0;
let dropInterval = 1000;
let lastTime = 0;

// Initialize the game board
function createBoard() {
  board = Array(BOARD_HEIGHT).fill(null).map(() => Array(BOARD_WIDTH).fill(0));
}

// Create a new piece
function createPiece() {
  const shapeIndex = Math.floor(Math.random() * SHAPES.length);
  const colorIndex = Math.floor(Math.random() * COLORS.length);
  return {
    shape: SHAPES[shapeIndex],
    color: COLORS[colorIndex],
  };
}

// Draw a single block with military styling
function drawBlock(x, y, color) {
  // Main block
  ctx.fillStyle = color;
  ctx.fillRect(x * BLOCK_SIZE, y * BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE);
  
  // Military rivet/bolt effect in corners
  ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
  ctx.fillRect(x * BLOCK_SIZE + 2, y * BLOCK_SIZE + 2, 3, 3);
  ctx.fillRect(x * BLOCK_SIZE + BLOCK_SIZE - 5, y * BLOCK_SIZE + 2, 3, 3);
  ctx.fillRect(x * BLOCK_SIZE + 2, y * BLOCK_SIZE + BLOCK_SIZE - 5, 3, 3);
  ctx.fillRect(x * BLOCK_SIZE + BLOCK_SIZE - 5, y * BLOCK_SIZE + BLOCK_SIZE - 5, 3, 3);
  
  // Border for tank armor effect
  ctx.strokeStyle = 'rgba(0, 0, 0, 0.5)';
  ctx.lineWidth = 2;
  ctx.strokeRect(x * BLOCK_SIZE, y * BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE);
  
  // Highlight for 3D effect
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(x * BLOCK_SIZE, y * BLOCK_SIZE + BLOCK_SIZE);
  ctx.lineTo(x * BLOCK_SIZE, y * BLOCK_SIZE);
  ctx.lineTo(x * BLOCK_SIZE + BLOCK_SIZE, y * BLOCK_SIZE);
  ctx.stroke();
}

// Draw the board
function drawBoard() {
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  
  // Draw grid lines (battlefield grid)
  ctx.strokeStyle = 'rgba(74, 90, 60, 0.2)';
  ctx.lineWidth = 1;
  for (let x = 0; x <= BOARD_WIDTH; x++) {
    ctx.beginPath();
    ctx.moveTo(x * BLOCK_SIZE, 0);
    ctx.lineTo(x * BLOCK_SIZE, canvas.height);
    ctx.stroke();
  }
  for (let y = 0; y <= BOARD_HEIGHT; y++) {
    ctx.beginPath();
    ctx.moveTo(0, y * BLOCK_SIZE);
    ctx.lineTo(canvas.width, y * BLOCK_SIZE);
    ctx.stroke();
  }
  
  // Draw placed blocks
  for (let y = 0; y < BOARD_HEIGHT; y++) {
    for (let x = 0; x < BOARD_WIDTH; x++) {
      if (board[y][x]) {
        drawBlock(x, y, board[y][x]);
      }
    }
  }
}

// Draw the current piece
function drawPiece() {
  if (!currentPiece) return;
  
  const shape = currentPiece.shape;
  const color = currentPiece.color;
  
  for (let y = 0; y < shape.length; y++) {
    for (let x = 0; x < shape[y].length; x++) {
      if (shape[y][x]) {
        drawBlock(currentX + x, currentY + y, color);
      }
    }
  }
}

// Draw next piece preview
function drawNextPiece() {
  nextCtx.fillStyle = '#000';
  nextCtx.fillRect(0, 0, nextCanvas.width, nextCanvas.height);
  
  if (!nextPiece) return;
  
  const shape = nextPiece.shape;
  const color = nextPiece.color;
  const offsetX = (4 - shape[0].length) / 2;
  const offsetY = (4 - shape.length) / 2;
  
  for (let y = 0; y < shape.length; y++) {
    for (let x = 0; x < shape[y].length; x++) {
      if (shape[y][x]) {
        const px = (offsetX + x) * BLOCK_SIZE;
        const py = (offsetY + y) * BLOCK_SIZE;
        
        nextCtx.fillStyle = color;
        nextCtx.fillRect(px, py, BLOCK_SIZE, BLOCK_SIZE);
        
        // Rivets
        nextCtx.fillStyle = 'rgba(0, 0, 0, 0.3)';
        nextCtx.fillRect(px + 2, py + 2, 3, 3);
        nextCtx.fillRect(px + BLOCK_SIZE - 5, py + 2, 3, 3);
        
        // Border
        nextCtx.strokeStyle = 'rgba(0, 0, 0, 0.5)';
        nextCtx.lineWidth = 2;
        nextCtx.strokeRect(px, py, BLOCK_SIZE, BLOCK_SIZE);
      }
    }
  }
}

// Check collision
function collision(piece, x, y) {
  const shape = piece.shape;
  for (let py = 0; py < shape.length; py++) {
    for (let px = 0; px < shape[py].length; px++) {
      if (shape[py][px]) {
        const boardX = x + px;
        const boardY = y + py;
        
        if (boardX < 0 || boardX >= BOARD_WIDTH || boardY >= BOARD_HEIGHT) {
          return true;
        }
        if (boardY >= 0 && board[boardY][boardX]) {
          return true;
        }
      }
    }
  }
  return false;
}

// Merge piece to board
function mergePiece() {
  const shape = currentPiece.shape;
  const color = currentPiece.color;
  
  for (let y = 0; y < shape.length; y++) {
    for (let x = 0; x < shape[y].length; x++) {
      if (shape[y][x]) {
        const boardY = currentY + y;
        const boardX = currentX + x;
        if (boardY >= 0) {
          board[boardY][boardX] = color;
        }
      }
    }
  }
}

// Clear completed lines
function clearLines() {
  let linesCleared = 0;
  
  for (let y = BOARD_HEIGHT - 1; y >= 0; y--) {
    if (board[y].every(cell => cell !== 0)) {
      board.splice(y, 1);
      board.unshift(Array(BOARD_WIDTH).fill(0));
      linesCleared++;
      y++; // Check same row again
    }
  }
  
  if (linesCleared > 0) {
    lines += linesCleared;
    
    // WW2-themed scoring
    const baseScores = [0, 100, 300, 500, 800]; // BLITZKRIEG for 4 lines!
    score += baseScores[linesCleared] * level;
    
    // Level up every 10 lines
    level = Math.floor(lines / 10) + 1;
    dropInterval = Math.max(100, 1000 - (level - 1) * 100);
    
    updateStats();
  }
  
  return linesCleared;
}

// Rotate piece
function rotate(piece) {
  const shape = piece.shape;
  const rotated = shape[0].map((_, i) =>
    shape.map(row => row[i]).reverse()
  );
  return { ...piece, shape: rotated };
}

// Move piece
function move(dx, dy) {
  if (!currentPiece || gameOver || paused) return false;
  
  const newX = currentX + dx;
  const newY = currentY + dy;
  
  if (!collision(currentPiece, newX, newY)) {
    currentX = newX;
    currentY = newY;
    if (dy > 0) dropCounter = 0;
    return true;
  }
  
  if (dy > 0) {
    mergePiece();
    clearLines();
    spawnPiece();
  }
  
  return false;
}

// Rotate current piece
function rotatePiece() {
  if (!currentPiece || gameOver || paused) return;
  
  const rotated = rotate(currentPiece);
  if (!collision(rotated, currentX, currentY)) {
    currentPiece = rotated;
  } else {
    // Try wall kicks
    const kicks = [[-1, 0], [1, 0], [-2, 0], [2, 0], [0, -1]];
    for (const [dx, dy] of kicks) {
      if (!collision(rotated, currentX + dx, currentY + dy)) {
        currentPiece = rotated;
        currentX += dx;
        currentY += dy;
        break;
      }
    }
  }
}

// Spawn new piece
function spawnPiece() {
  currentPiece = nextPiece || createPiece();
  nextPiece = createPiece();
  currentX = Math.floor(BOARD_WIDTH / 2) - Math.floor(currentPiece.shape[0].length / 2);
  currentY = 0;
  
  if (collision(currentPiece, currentX, currentY)) {
    endGame();
  }
  
  drawNextPiece();
}

// Update stats display
function updateStats() {
  scoreEl.textContent = score;
  linesEl.textContent = lines;
  levelEl.textContent = level;
}

// End game
function endGame() {
  gameOver = true;
  finalScoreEl.textContent = score;
  gameOverOverlay.style.display = 'flex';
}

// Reset game
function resetGame() {
  createBoard();
  score = 0;
  lines = 0;
  level = 1;
  dropInterval = 1000;
  gameOver = false;
  paused = false;
  dropCounter = 0;
  gameOverOverlay.style.display = 'none';
  updateStats();
  spawnPiece();
}

// Game loop
function update(time = 0) {
  if (!gameOver && !paused) {
    const deltaTime = time - lastTime;
    lastTime = time;
    dropCounter += deltaTime;
    
    if (dropCounter > dropInterval) {
      move(0, 1);
    }
  }
  
  drawBoard();
  drawPiece();
  
  requestAnimationFrame(update);
}

// Keyboard controls
document.addEventListener('keydown', (e) => {
  if (gameOver) return;
  
  switch (e.key) {
    case 'ArrowLeft':
      e.preventDefault();
      move(-1, 0);
      break;
    case 'ArrowRight':
      e.preventDefault();
      move(1, 0);
      break;
    case 'ArrowDown':
      e.preventDefault();
      move(0, 1);
      break;
    case 'ArrowUp':
    case ' ':
      e.preventDefault();
      rotatePiece();
      break;
    case 'p':
    case 'P':
      e.preventDefault();
      paused = !paused;
      if (paused) {
        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#ffd700';
        ctx.font = 'bold 48px "Bebas Neue", sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('PAUSE', canvas.width / 2, canvas.height / 2 - 20);
        ctx.font = 'bold 24px "Bebas Neue", sans-serif';
        ctx.fillText('PAUSIERT', canvas.width / 2, canvas.height / 2 + 20);
      }
      break;
    case 'r':
    case 'R':
      e.preventDefault();
      if (confirm('Neustart? / Restart?')) {
        resetGame();
      }
      break;
  }
});

// Restart button
restartBtn.addEventListener('click', () => {
  resetGame();
});

// Initialize game
createBoard();
updateStats();
spawnPiece();
update();
