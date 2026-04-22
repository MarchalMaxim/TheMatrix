// Gentle nature-inspired audio feedback using Web Audio API
// Plays soft tones on interactions

class GardenAudio {
  constructor() {
    this.audioContext = null;
    this.enabled = false;
    this.initOnInteraction();
  }

  initOnInteraction() {
    // Web Audio requires user interaction to start
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

  // Play a soft bell-like tone
  playTone(frequency = 440, duration = 0.3, volume = 0.1) {
    if (!this.enabled || !this.audioContext) return;

    const now = this.audioContext.currentTime;
    const oscillator = this.audioContext.createOscillator();
    const gainNode = this.audioContext.createGain();

    oscillator.connect(gainNode);
    gainNode.connect(this.audioContext.destination);

    // Soft sine wave for gentle tone
    oscillator.type = 'sine';
    oscillator.frequency.setValueAtTime(frequency, now);

    // Envelope for natural sound
    gainNode.gain.setValueAtTime(0, now);
    gainNode.gain.linearRampToValueAtTime(volume, now + 0.01);
    gainNode.gain.exponentialRampToValueAtTime(0.01, now + duration);

    oscillator.start(now);
    oscillator.stop(now + duration);
  }

  // Play a soft chord (multiple notes)
  playChord(baseFreq = 440, duration = 0.4) {
    // Major triad
    this.playTone(baseFreq, duration, 0.05);
    this.playTone(baseFreq * 1.25, duration, 0.04); // major third
    this.playTone(baseFreq * 1.5, duration, 0.03);  // perfect fifth
  }

  // Play on note creation - ascending arpeggio
  noteCreated() {
    const baseFreq = 523.25; // C5
    setTimeout(() => this.playTone(baseFreq, 0.2, 0.08), 0);
    setTimeout(() => this.playTone(baseFreq * 1.25, 0.2, 0.08), 80);
    setTimeout(() => this.playTone(baseFreq * 1.5, 0.3, 0.08), 160);
  }

  // Play on note hover - single gentle tone
  noteHover() {
    this.playTone(659.25, 0.15, 0.04); // E5
  }

  // Play on note delete - descending
  noteDeleted() {
    const baseFreq = 523.25;
    setTimeout(() => this.playTone(baseFreq * 1.5, 0.15, 0.06), 0);
    setTimeout(() => this.playTone(baseFreq, 0.2, 0.06), 100);
  }

  // Play on button click
  buttonClick() {
    this.playTone(783.99, 0.2, 0.06); // G5
  }
}

const gardenAudio = new GardenAudio();

// Hook up audio to interactions
document.addEventListener('DOMContentLoaded', () => {
  // Button clicks
  const plantButton = document.getElementById('new-note-btn');
  if (plantButton) {
    plantButton.addEventListener('click', () => gardenAudio.buttonClick());
  }

  // Note interactions - using event delegation
  const canvas = document.getElementById('canvas');
  if (canvas) {
    canvas.addEventListener('mouseenter', (e) => {
      if (e.target.classList.contains('note')) {
        gardenAudio.noteHover();
      }
    }, true);
  }
});

// Export for use in app.js
window.gardenAudio = gardenAudio;
