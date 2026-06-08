/**
 * Preference Manager
 * Handles user customization preferences with localStorage persistence
 * MSN-0042 Track 2
 */

class PreferenceManager {
  constructor() {
    this.storageKey = 'controlDeckPreferences';
    this.prefs = this.loadPreferences();
    this.listeners = [];
    this.applyPreferences();
  }

  /**
   * Get default preferences
   */
  getDefaults() {
    return {
      // Theme & Color
      theme: 'starfleet-dark',
      primaryColor: '#FFD700',
      accentColor: '#00FFFF',
      division: 'command', // command, operations, science, engineering

      // Animations
      animationsEnabled: true,
      animationIntensity: 0.8, // 0.0 - 1.0

      // Audio
      audioEnabled: true,
      audioVolume: 0.5, // 0.0 - 1.0

      // Behavior
      autoRefreshRate: 30, // seconds (5-120)
      dashboardLayout: 'grid', // grid or list
      showStatusIndicators: true,

      // Display
      fontSize: 'normal', // small, normal, large
      compactMode: false,
      highContrast: false,

      // Accessibility
      reduceMotion: false,
      colorBlindMode: false,

      // Metadata
      lastUpdated: new Date().toISOString()
    };
  }

  /**
   * Load preferences from localStorage
   */
  loadPreferences() {
    try {
      const saved = localStorage.getItem(this.storageKey);
      if (saved) {
        const parsed = JSON.parse(saved);
        // Merge with defaults to handle new properties
        return { ...this.getDefaults(), ...parsed };
      }
    } catch (e) {
      console.warn('Failed to load preferences:', e);
    }
    return this.getDefaults();
  }

  /**
   * Save preferences to localStorage
   */
  savePreferences() {
    try {
      this.prefs.lastUpdated = new Date().toISOString();
      localStorage.setItem(this.storageKey, JSON.stringify(this.prefs));
      this.applyPreferences();
      this.notifyListeners();
      console.log('Preferences saved');
    } catch (e) {
      console.error('Failed to save preferences:', e);
    }
  }

  /**
   * Apply preferences to DOM
   */
  applyPreferences() {
    const root = document.documentElement;

    // Color variables
    root.style.setProperty('--primary-color', this.prefs.primaryColor);
    root.style.setProperty('--accent-color', this.prefs.accentColor);

    // Animation intensity
    root.style.setProperty('--animation-intensity', this.prefs.animationIntensity);

    // Disable animations if needed
    if (!this.prefs.animationsEnabled) {
      root.style.setProperty('--animation-duration-multiplier', '0');
    } else {
      root.style.setProperty('--animation-duration-multiplier', '1');
    }

    // Font size
    const fontSizeMap = {
      small: '14px',
      normal: '16px',
      large: '18px'
    };
    root.style.setProperty('--base-font-size', fontSizeMap[this.prefs.fontSize]);

    // Compact mode
    if (this.prefs.compactMode) {
      document.body.classList.add('compact-mode');
    } else {
      document.body.classList.remove('compact-mode');
    }

    // High contrast
    if (this.prefs.highContrast) {
      document.body.classList.add('high-contrast');
    } else {
      document.body.classList.remove('high-contrast');
    }

    // Reduce motion
    if (this.prefs.reduceMotion) {
      document.body.classList.add('reduce-motion');
    } else {
      document.body.classList.remove('reduce-motion');
    }

    // Color blind mode
    if (this.prefs.colorBlindMode) {
      document.body.classList.add('color-blind-mode');
    } else {
      document.body.classList.remove('color-blind-mode');
    }
  }

  /**
   * Set a preference value
   */
  set(key, value) {
    if (key in this.prefs) {
      this.prefs[key] = value;
      this.savePreferences();
      return true;
    }
    return false;
  }

  /**
   * Get a preference value
   */
  get(key) {
    return this.prefs[key] !== undefined ? this.prefs[key] : null;
  }

  /**
   * Get all preferences
   */
  getAll() {
    return { ...this.prefs };
  }

  /**
   * Update multiple preferences at once
   */
  update(updates) {
    Object.entries(updates).forEach(([key, value]) => {
      if (key in this.prefs) {
        this.prefs[key] = value;
      }
    });
    this.savePreferences();
  }

  /**
   * Reset to defaults
   */
  reset() {
    this.prefs = this.getDefaults();
    this.savePreferences();
    console.log('Preferences reset to defaults');
  }

  /**
   * Export preferences as JSON
   */
  export() {
    return JSON.stringify(this.prefs, null, 2);
  }

  /**
   * Import preferences from JSON
   */
  import(jsonString) {
    try {
      const imported = JSON.parse(jsonString);
      this.prefs = { ...this.getDefaults(), ...imported };
      this.savePreferences();
      return true;
    } catch (e) {
      console.error('Failed to import preferences:', e);
      return false;
    }
  }

  /**
   * Register listener for preference changes
   */
  onChange(callback) {
    this.listeners.push(callback);
  }

  /**
   * Notify all listeners
   */
  notifyListeners() {
    this.listeners.forEach(callback => callback(this.prefs));
  }

  /**
   * Set division-specific colors
   */
  setDivision(division) {
    const divisonColors = {
      command: { primary: '#FFD700', accent: '#FFA500' },
      operations: { primary: '#00FFFF', accent: '#00CCCC' },
      science: { primary: '#0099FF', accent: '#00CCFF' },
      engineering: { primary: '#FF9800', accent: '#FFAA00' }
    };

    if (divisonColors[division]) {
      this.prefs.division = division;
      this.prefs.primaryColor = divisonColors[division].primary;
      this.prefs.accentColor = divisonColors[division].accent;
      this.savePreferences();
      return true;
    }
    return false;
  }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = PreferenceManager;
}
