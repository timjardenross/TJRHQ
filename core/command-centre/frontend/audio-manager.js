/**
 * Audio Manager
 * Handles audio notifications for operational status changes
 * MSN-0042 Track 2
 */

class AudioManager {
  constructor(preferences) {
    this.prefs = preferences;
    this.sounds = {};
    this.initialized = false;
    this.soundPaths = {
      critical: '/assets/sounds/alert-critical.mp3',
      warning: '/assets/sounds/alert-warning.mp3',
      recovery: '/assets/sounds/alert-recovery.mp3',
      notification: '/assets/sounds/notification-subtle.mp3'
    };

    this.initialize();
  }

  /**
   * Initialize audio system
   */
  async initialize() {
    try {
      // Create audio elements for each sound
      Object.entries(this.soundPaths).forEach(([name, path]) => {
        const audio = new Audio();
        audio.src = path;
        audio.volume = this.prefs.get('audioVolume');
        this.sounds[name] = audio;
      });
      this.initialized = true;
      console.log('Audio Manager initialized');
    } catch (e) {
      console.warn('Audio Manager initialization failed:', e);
    }
  }

  /**
   * Play a sound
   */
  play(soundType, volume = null) {
    if (!this.initialized || !this.prefs.get('audioEnabled')) {
      return;
    }

    const sound = this.sounds[soundType];
    if (!sound) {
      console.warn(`Sound type "${soundType}" not found`);
      return;
    }

    try {
      sound.volume = volume !== null ? volume : this.prefs.get('audioVolume');
      sound.currentTime = 0;
      sound.play().catch(e => {
        console.warn('Audio playback failed:', e);
      });
    } catch (e) {
      console.warn('Failed to play sound:', e);
    }
  }

  /**
   * Play critical alert sound
   */
  playCritical() {
    this.play('critical');
  }

  /**
   * Play warning sound
   */
  playWarning() {
    this.play('warning');
  }

  /**
   * Play recovery sound
   */
  playRecovery() {
    this.play('recovery');
  }

  /**
   * Play notification sound
   */
  playNotification() {
    this.play('notification');
  }

  /**
   * Set volume for all sounds
   */
  setVolume(level) {
    const volume = Math.max(0, Math.min(1, level));
    Object.values(this.sounds).forEach(sound => {
      sound.volume = volume;
    });
    this.prefs.set('audioVolume', volume);
  }

  /**
   * Toggle audio on/off
   */
  toggle() {
    const enabled = !this.prefs.get('audioEnabled');
    this.prefs.set('audioEnabled', enabled);
    return enabled;
  }

  /**
   * Test audio playback
   */
  test() {
    console.log('Testing audio playback...');
    this.playNotification();
    setTimeout(() => this.playWarning(), 600);
    setTimeout(() => this.playRecovery(), 1200);
  }

  /**
   * Emit alert based on status
   */
  onStatusChange(status, previousStatus = null) {
    if (!this.prefs.get('audioEnabled')) {
      return;
    }

    // Service went offline
    if (status === 'offline' && previousStatus !== 'offline') {
      this.playCritical();
    }
    // Service recovered
    else if (status === 'online' && previousStatus === 'offline') {
      this.playRecovery();
    }
    // Service degraded
    else if (status === 'degraded' && previousStatus === 'online') {
      this.playWarning();
    }
    // New notification
    else if (status === 'notification') {
      this.playNotification();
    }
  }

  /**
   * Check browser audio support
   */
  static isSupported() {
    return !!document.createElement('audio').canPlayType;
  }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = AudioManager;
}
