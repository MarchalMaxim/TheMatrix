// Industrial mechanical audio feedback using Web Audio API
class IndustrialAudio {
  constructor() {
    this.audioContext = null;
    this.enabled = false;
    this.initOnInteraction();
  }

  initOnInteraction() {
    const init = () => {
      if (!this.audioContext) {
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        this.enabled = true;
      }
      document.removeEventListener('click', init);
      document.removeEventListener('touchstart', init);
    };
    document.addEventListener('click', init, { once: true });
    document.addEventListener('touchstart', init, { once: true });
  }

  // Play mechanical click
  playClick(frequency = 800, duration = 0.05, volume = 0.15) {
    if (!this.enabled || !this.audioContext) return;

    const now = this.audioContext.currentTime;
    const oscillator = this.audioContext.createOscillator();
    const gainNode = this.audioContext.createGain();

    oscillator.connect(gainNode);
    gainNode.connect(this.audioContext.destination);

    oscillator.type = 'square';
    oscillator.frequency.setValueAtTime(frequency, now);
    oscillator.frequency.exponentialRampToValueAtTime(frequency * 0.5, now + duration);

    gainNode.gain.setValueAtTime(volume, now);
    gainNode.gain.exponentialRampToValueAtTime(0.01, now + duration);

    oscillator.start(now);
    oscillator.stop(now + duration);
  }

  // Play warning beep
  playWarning(duration = 0.3) {
    if (!this.enabled || !this.audioContext) return;

    const now = this.audioContext.currentTime;
    const oscillator = this.audioContext.createOscillator();
    const gainNode = this.audioContext.createGain();

    oscillator.connect(gainNode);
    gainNode.connect(this.audioContext.destination);

    oscillator.type = 'square';
    oscillator.frequency.setValueAtTime(1000, now);

    gainNode.gain.setValueAtTime(0, now);
    gainNode.gain.linearRampToValueAtTime(0.1, now + 0.01);
    gainNode.gain.linearRampToValueAtTime(0.1, now + duration - 0.01);
    gainNode.gain.linearRampToValueAtTime(0, now + duration);

    oscillator.start(now);
    oscillator.stop(now + duration);
  }

  // Play Geiger counter tick
  playGeigerTick() {
    if (!this.enabled || !this.audioContext) return;

    const now = this.audioContext.currentTime;
    const noise = this.audioContext.createBufferSource();
    const buffer = this.audioContext.createBuffer(1, 4096, this.audioContext.sampleRate);
    const output = buffer.getChannelData(0);
    
    // Generate white noise burst
    for (let i = 0; i < 4096; i++) {
      output[i] = Math.random() * 2 - 1;
    }
    
    noise.buffer = buffer;
    const gainNode = this.audioContext.createGain();
    noise.connect(gainNode);
    gainNode.connect(this.audioContext.destination);

    gainNode.gain.setValueAtTime(0.08, now);
    gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.02);

    noise.start(now);
    noise.stop(now + 0.02);
  }

  // Play servo motor sound
  playServo() {
    if (!this.enabled || !this.audioContext) return;

    const now = this.audioContext.currentTime;
    const oscillator = this.audioContext.createOscillator();
    const gainNode = this.audioContext.createGain();

    oscillator.connect(gainNode);
    gainNode.connect(this.audioContext.destination);

    oscillator.type = 'sawtooth';
    oscillator.frequency.setValueAtTime(200, now);
    oscillator.frequency.linearRampToValueAtTime(250, now + 0.15);

    gainNode.gain.setValueAtTime(0.08, now);
    gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.15);

    oscillator.start(now);
    oscillator.stop(now + 0.15);
  }

  // Play data transmission sound
  playDataTransmission() {
    if (!this.enabled || !this.audioContext) return;
    
    // Series of rapid beeps
    for (let i = 0; i < 5; i++) {
      setTimeout(() => {
        this.playClick(1200 + i * 100, 0.03, 0.08);
      }, i * 40);
    }
  }

  // Note created - data transmission
  noteCreated() {
    this.playDataTransmission();
    setTimeout(() => this.playServo(), 200);
    if (window.screenShake) {
      setTimeout(() => window.screenShake(), 50);
    }
  }

  // Note hover - mechanical click
  noteHover() {
    this.playClick(1000, 0.04, 0.1);
  }

  // Note deleted - warning sequence
  noteDeleted() {
    this.playWarning(0.2);
    setTimeout(() => this.playGeigerTick(), 100);
    setTimeout(() => this.playGeigerTick(), 200);
  }

  // Button click - servo
  buttonClick() {
    this.playServo();
    this.playClick(600, 0.05, 0.12);
  }
}

const industrialAudio = new IndustrialAudio();

document.addEventListener('DOMContentLoaded', () => {
  const commandButton = document.getElementById('new-note-btn');
  if (commandButton) {
    commandButton.addEventListener('click', () => industrialAudio.buttonClick());
  }

  const canvas = document.getElementById('canvas');
  if (canvas) {
    canvas.addEventListener('mouseenter', (e) => {
      if (e.target.classList.contains('note')) {
        industrialAudio.noteHover();
      }
    }, true);
  }

  // Click sounds on nav buttons
  document.querySelectorAll('.nav-button, .command-button').forEach(btn => {
    btn.addEventListener('click', () => industrialAudio.playClick(900, 0.06, 0.1));
  });
});

window.industrialAudio = industrialAudio;
