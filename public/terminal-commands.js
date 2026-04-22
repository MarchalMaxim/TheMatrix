// Interactive terminal commands system
(function() {
  const input = document.getElementById('terminal-input');
  const output = document.getElementById('terminal-output');
  const statNotes = document.getElementById('stat-notes');
  const statEntropy = document.getElementById('stat-entropy');
  const statCycles = document.getElementById('stat-cycles');

  if (!input || !output) return;

  // Load and update stats
  async function updateStats() {
    try {
      const notes = await fetch('/api/notes').then(r => r.json());
      if (statNotes) statNotes.textContent = notes.length;
      
      // Random entropy value for effect
      const entropy = Math.floor(Math.random() * 30) + 40;
      if (statEntropy) statEntropy.textContent = entropy + '%';
    } catch (err) {
      console.error('Failed to fetch stats:', err);
    }
  }

  updateStats();
  setInterval(updateStats, 10000);

  // Fortune messages
  const fortunes = [
    "The post-it you seek is already within you.",
    "Chaos is not a pit. Chaos is a ladder.",
    "In 4 hours, everything changes. Again.",
    "The best ideas arrive when you're not looking.",
    "Your next prompt will reshape reality.",
    "The Matrix has you... and that's okay.",
    "Trust the process. Embrace the chaos.",
    "What is real? How do you define 'real'?",
    "There is no spoon. There are only post-its.",
    "The cycle must flow.",
    "Your idea is worth the proof-of-work.",
    "Digital rain cleanses the soul.",
    "The terminal never lies, but it might glitch."
  ];

  // Matrix quotes
  const matrixQuotes = [
    "What is the Matrix? Control.",
    "Free your mind.",
    "There is no spoon.",
    "Welcome to the desert of the real.",
    "The Matrix is everywhere.",
    "I know kung fu.",
    "Guns. Lots of guns.",
    "Choice. The problem is choice."
  ];

  function addOutput(text, className = '') {
    const line = document.createElement('div');
    line.className = 'output-line ' + className;
    line.innerHTML = text;
    output.appendChild(line);
    output.scrollTop = output.scrollHeight;
  }

  function getTimestamp() {
    const now = new Date();
    return now.toLocaleTimeString('en-GB', { hour12: false });
  }

  // Command handlers
  const commands = {
    help: () => {
      addOutput('<span class="yellow">[HELP]</span> Available commands:');
      addOutput('  <span class="cyan">help</span> - Show this help');
      addOutput('  <span class="cyan">status</span> - System status');
      addOutput('  <span class="cyan">stats</span> - Statistics');
      addOutput('  <span class="cyan">fortune</span> - Random fortune');
      addOutput('  <span class="cyan">matrix</span> - Matrix quote');
      addOutput('  <span class="cyan">time</span> - Current time');
      addOutput('  <span class="cyan">clear</span> - Clear screen');
      addOutput('  <span class="cyan">whoami</span> - User info');
      addOutput('  <span class="cyan">chaos</span> - Chaos levels');
      addOutput('&nbsp;');
    },

    status: async () => {
      addOutput('<span class="green">[STATUS]</span> Querying system...');
      try {
        const status = await fetch('/api/worker-status').then(r => r.json());
        addOutput('<span class="cyan">→</span> System: <span class="green">OPERATIONAL</span>');
        addOutput('<span class="cyan">→</span> Cycle ID: <span class="yellow">' + (status.cycle_id || 'N/A') + '</span>');
        if (status.next_run_epoch) {
          const seconds = Math.max(0, Math.ceil(status.next_run_epoch - Date.now() / 1000));
          const hours = Math.floor(seconds / 3600);
          const mins = Math.floor((seconds % 3600) / 60);
          const secs = seconds % 60;
          addOutput('<span class="cyan">→</span> Next cycle in: <span class="red">' + 
            `${hours}h ${mins}m ${secs}s` + '</span>');
        }
        addOutput('<span class="cyan">→</span> Summary: ' + (status.summary || 'Awaiting data...'));
      } catch (err) {
        addOutput('<span class="red">[ERROR]</span> Failed to fetch status');
      }
      addOutput('&nbsp;');
    },

    stats: async () => {
      addOutput('<span class="green">[STATS]</span> Analyzing data...');
      try {
        const notes = await fetch('/api/notes').then(r => r.json());
        addOutput('<span class="cyan">→</span> Active post-its: <span class="yellow">' + notes.length + '</span>');
        
        const colors = {};
        notes.forEach(n => {
          colors[n.color] = (colors[n.color] || 0) + 1;
        });
        addOutput('<span class="cyan">→</span> Unique colors: <span class="yellow">' + Object.keys(colors).length + '</span>');
        
        const avgX = notes.reduce((sum, n) => sum + n.x, 0) / (notes.length || 1);
        const avgY = notes.reduce((sum, n) => sum + n.y, 0) / (notes.length || 1);
        addOutput('<span class="cyan">→</span> Spatial center: <span class="yellow">(' + 
          Math.round(avgX) + ', ' + Math.round(avgY) + ')</span>');
      } catch (err) {
        addOutput('<span class="red">[ERROR]</span> Failed to fetch stats');
      }
      addOutput('&nbsp;');
    },

    fortune: () => {
      const fortune = fortunes[Math.floor(Math.random() * fortunes.length)];
      addOutput('<span class="yellow">[FORTUNE]</span> ' + fortune);
      addOutput('&nbsp;');
    },

    matrix: () => {
      const quote = matrixQuotes[Math.floor(Math.random() * matrixQuotes.length)];
      addOutput('<span class="cyan">[MATRIX]</span> "' + quote + '"');
      addOutput('&nbsp;');
    },

    time: () => {
      const now = new Date();
      addOutput('<span class="green">[TIME]</span> Current time: <span class="yellow">' + 
        now.toLocaleString() + '</span>');
      addOutput('<span class="cyan">→</span> Unix timestamp: <span class="yellow">' + 
        Math.floor(now.getTime() / 1000) + '</span>');
      addOutput('&nbsp;');
    },

    clear: () => {
      output.innerHTML = '';
      addOutput('<span class="green">[SYSTEM]</span> Terminal cleared.');
      addOutput('&nbsp;');
    },

    whoami: () => {
      const userIdEl = document.getElementById('user-id');
      const userId = userIdEl ? userIdEl.textContent : 'UNKNOWN';
      addOutput('<span class="cyan">[USER]</span> ID: <span class="yellow">' + userId + '</span>');
      addOutput('<span class="cyan">→</span> Privilege: <span class="green">GUEST</span>');
      addOutput('<span class="cyan">→</span> Access: <span class="green">POST-IT_CREATION</span>');
      addOutput('&nbsp;');
    },

    chaos: () => {
      const level = Math.floor(Math.random() * 100);
      let status = 'STABLE';
      let color = 'green';
      
      if (level > 70) {
        status = 'CRITICAL';
        color = 'red';
      } else if (level > 40) {
        status = 'ELEVATED';
        color = 'yellow';
      }
      
      addOutput('<span class="yellow">[CHAOS]</span> Current chaos level: <span class="' + color + '">' + 
        level + '% [' + status + ']</span>');
      addOutput('<span class="cyan">→</span> Reality stability: <span class="green">' + 
        (100 - level) + '%</span>');
      addOutput('<span class="cyan">→</span> Entropy: <span class="yellow">Rising</span>');
      addOutput('&nbsp;');
    }
  };

  // Handle command input
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const cmd = input.value.trim().toLowerCase();
      
      if (cmd) {
        // Echo command
        addOutput('<span class="yellow">user@matrix:~$</span> ' + input.value);
        
        // Execute command
        if (commands[cmd]) {
          commands[cmd]();
        } else {
          addOutput('<span class="red">[ERROR]</span> Command not found: ' + cmd);
          addOutput('Type <span class="yellow">help</span> for available commands.');
          addOutput('&nbsp;');
        }
      }
      
      input.value = '';
    }
  });

  // Focus input on click anywhere
  document.addEventListener('click', () => {
    input.focus();
  });

  // Auto-focus on load
  input.focus();
})();
