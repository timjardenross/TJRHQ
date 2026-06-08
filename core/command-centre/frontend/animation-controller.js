/**
 * Animation Controller
 * Manages animation intensity and effects throughout the dashboard
 * MSN-0042 Track 2
 */

class AnimationController {
  constructor(preferences) {
    this.prefs = preferences;
    this.animationFrames = {};
    this.activeAnimations = new Map();
    this.maxSimultaneousAnimations = 5;
    this.initializeAnimations();
  }

  /**
   * Initialize animation system
   */
  initializeAnimations() {
    this.createAnimationStylesheet();
    this.applyAnimationSettings();
  }

  /**
   * Create dynamic animation stylesheet
   */
  createAnimationStylesheet() {
    let styleId = 'animation-controller-styles';
    let existingStyle = document.getElementById(styleId);
    if (existingStyle) existingStyle.remove();

    const style = document.createElement('style');
    style.id = styleId;

    const intensity = this.prefs.get('animationIntensity');
    const baseDuration = 300;
    const durationMs = Math.max(100, baseDuration / Math.max(0.1, intensity));

    style.textContent = `
      :root {
        --animation-intensity: ${intensity};
        --animation-duration: ${durationMs}ms;
        --animation-multiplier: ${1 / intensity};
        --transition-fast: ${Math.round(150 / intensity)}ms ease;
        --transition-normal: ${Math.round(300 / intensity)}ms ease;
        --transition-slow: ${Math.round(600 / intensity)}ms ease;
      }

      /* Sensor Sweep Animation */
      @keyframes sensor-sweep {
        0% {
          left: -100%;
          box-shadow: 0 0 20px rgba(255, 215, 0, 0.5);
        }
        50% {
          box-shadow: 0 0 40px rgba(255, 215, 0, 0.8);
        }
        100% {
          left: 100%;
          box-shadow: 0 0 20px rgba(255, 215, 0, 0.5);
        }
      }

      .sensor-sweep {
        position: relative;
        overflow: hidden;
      }

      .sensor-sweep::after {
        content: '';
        position: absolute;
        left: -100%;
        top: 0;
        width: 20%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(255, 215, 0, 0.3), transparent);
        animation: sensor-sweep calc(2s * var(--animation-multiplier)) ease-in-out infinite;
      }

      /* Pulsing Indicators */
      @keyframes pulse-online {
        0%, 100% { box-shadow: 0 0 10px rgba(76, 175, 80, 0.3); }
        50% { box-shadow: 0 0 20px rgba(76, 175, 80, 0.6); }
      }

      @keyframes pulse-warning {
        0%, 100% { box-shadow: 0 0 10px rgba(255, 152, 0, 0.3); }
        50% { box-shadow: 0 0 20px rgba(255, 152, 0, 0.6); }
      }

      @keyframes pulse-critical {
        0%, 100% { box-shadow: 0 0 10px rgba(244, 67, 54, 0.3); }
        50% { box-shadow: 0 0 20px rgba(244, 67, 54, 0.8); }
      }

      .pulse-online {
        animation: pulse-online calc(2s * var(--animation-multiplier)) infinite;
      }

      .pulse-warning {
        animation: pulse-warning calc(2s * var(--animation-multiplier)) infinite;
      }

      .pulse-critical {
        animation: pulse-critical calc(1s * var(--animation-multiplier)) infinite;
      }

      /* Glitch Effect */
      @keyframes glitch {
        0% { transform: translate(0); }
        20% { transform: translate(-2px, 2px); }
        40% { transform: translate(-2px, -2px); }
        60% { transform: translate(2px, 2px); }
        80% { transform: translate(2px, -2px); }
        100% { transform: translate(0); }
      }

      .glitch {
        animation: glitch calc(0.3s * var(--animation-multiplier)) ease-in-out;
      }

      /* Fade In/Out */
      @keyframes fade-in {
        from {
          opacity: 0;
          transform: translateY(10px);
        }
        to {
          opacity: 1;
          transform: translateY(0);
        }
      }

      @keyframes fade-out {
        from {
          opacity: 1;
          transform: translateY(0);
        }
        to {
          opacity: 0;
          transform: translateY(-10px);
        }
      }

      .fade-in {
        animation: fade-in var(--transition-normal);
      }

      .fade-out {
        animation: fade-out var(--transition-normal);
      }

      /* Smooth Transitions */
      .smooth-transition {
        transition: all var(--transition-normal);
      }

      /* Reduce Motion Support */
      @media (prefers-reduced-motion: reduce) {
        * {
          animation-duration: 0.01ms !important;
          animation-iteration-count: 1 !important;
          transition-duration: 0.01ms !important;
        }
      }

      /* Disable animations when intensity is 0 */
      .no-animations * {
        animation: none !important;
        transition: none !important;
      }
    `;

    document.head.appendChild(style);
  }

  /**
   * Apply animation settings to DOM
   */
  applyAnimationSettings() {
    const intensity = this.prefs.get('animationIntensity');
    const enabled = this.prefs.get('animationsEnabled');

    const root = document.documentElement;
    root.style.setProperty('--animation-intensity', intensity);

    if (!enabled || intensity === 0) {
      document.body.classList.add('no-animations');
    } else {
      document.body.classList.remove('no-animations');
    }
  }

  /**
   * Add sensor sweep effect to element
   */
  addSensorSweep(element) {
    if (!this.prefs.get('animationsEnabled')) return;
    element.classList.add('sensor-sweep');
  }

  /**
   * Remove sensor sweep effect
   */
  removeSensorSweep(element) {
    element.classList.remove('sensor-sweep');
  }

  /**
   * Add pulsing indicator based on status
   */
  addPulse(element, status) {
    if (!this.prefs.get('animationsEnabled')) return;

    const pulseClass = {
      online: 'pulse-online',
      warning: 'pulse-warning',
      offline: 'pulse-critical',
      critical: 'pulse-critical'
    }[status];

    if (pulseClass) {
      this.removePulse(element);
      element.classList.add(pulseClass);
    }
  }

  /**
   * Remove pulsing indicator
   */
  removePulse(element) {
    element.classList.remove('pulse-online', 'pulse-warning', 'pulse-critical');
  }

  /**
   * Add glitch effect (critical alerts)
   */
  addGlitch(element) {
    if (!this.prefs.get('animationsEnabled')) return;

    element.classList.add('glitch');
    setTimeout(() => {
      element.classList.remove('glitch');
    }, 300 * (1 / this.prefs.get('animationIntensity')));
  }

  /**
   * Fade in element
   */
  fadeIn(element) {
    if (!this.prefs.get('animationsEnabled')) {
      element.style.opacity = '1';
      return;
    }

    element.classList.add('fade-in');
    element.style.opacity = '1';

    setTimeout(() => {
      element.classList.remove('fade-in');
    }, 300 * (1 / this.prefs.get('animationIntensity')));
  }

  /**
   * Fade out element
   */
  fadeOut(element) {
    if (!this.prefs.get('animationsEnabled')) {
      element.style.opacity = '0';
      return;
    }

    element.classList.add('fade-out');
    element.style.opacity = '0';

    setTimeout(() => {
      element.classList.remove('fade-out');
    }, 300 * (1 / this.prefs.get('animationIntensity')));
  }

  /**
   * Smooth transition property change
   */
  smoothTransition(element, property, value) {
    element.classList.add('smooth-transition');
    element.style[property] = value;

    setTimeout(() => {
      element.classList.remove('smooth-transition');
    }, 300 * (1 / this.prefs.get('animationIntensity')));
  }

  /**
   * Update animation intensity
   */
  setIntensity(intensity) {
    const clamped = Math.max(0, Math.min(1, intensity));
    this.prefs.set('animationIntensity', clamped);
    this.createAnimationStylesheet();
    this.applyAnimationSettings();
  }

  /**
   * Toggle animations on/off
   */
  toggleAnimations() {
    const enabled = !this.prefs.get('animationsEnabled');
    this.prefs.set('animationsEnabled', enabled);
    this.applyAnimationSettings();
    return enabled;
  }

  /**
   * Get animation duration in milliseconds
   */
  getDuration(type = 'normal') {
    const baseMap = {
      fast: 150,
      normal: 300,
      slow: 600
    };
    const base = baseMap[type] || baseMap.normal;
    const intensity = this.prefs.get('animationIntensity');
    return Math.max(50, base / Math.max(0.1, intensity));
  }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = AnimationController;
}
