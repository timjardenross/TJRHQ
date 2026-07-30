'use strict';

/**
 * Generic runtime-CSS primitives — deliberately free of any Command-Centre
 * or MSN-0315-specific knowledge, so any adopting application can build its
 * own assertions on top (per MSN-0317's "reusable platform capability, not
 * a solution specific to MSN-0315" requirement).
 */

/**
 * Resolves a list of CSS custom properties (design tokens) as the browser
 * actually computed them at runtime, from a given scope (default :root).
 * Catches the case a static guard cannot: a variable that is defined in
 * source but resolves to empty/unset at runtime (load-order bugs, scoping
 * mistakes) — as opposed to merely checking the variable's textual
 * definition exists somewhere in a CSS file.
 */
async function resolveCSSVariables(page, varNames, { selector = ':root' } = {}) {
  return page.evaluate(
    ({ varNames, selector }) => {
      const el = document.querySelector(selector === ':root' ? 'html' : selector);
      const computed = getComputedStyle(el);
      const out = {};
      for (const name of varNames) {
        const value = computed.getPropertyValue(name).trim();
        out[name] = value === '' ? null : value;
      }
      return out;
    },
    { varNames, selector }
  );
}

/**
 * Extracts computed style properties for every element matching a selector.
 * Returns the actual rendered value (e.g. `rgb(12, 90, 130)`), not the
 * source-text declaration — this is what lets a runtime check see the
 * effect of a malformed JS-constructed style (e.g. an invalid `var(...)NN`
 * concatenation that gets silently dropped by the browser and falls back to
 * an inherited/initial value), which is invisible to any static-text tool.
 */
async function getComputedStyles(page, selector, properties) {
  return page.evaluate(
    ({ selector, properties }) => {
      const elements = Array.from(document.querySelectorAll(selector));
      return elements.map((el, index) => {
        const computed = getComputedStyle(el);
        const values = {};
        for (const prop of properties) {
          values[prop] = computed.getPropertyValue(prop);
        }
        return {
          index,
          selector,
          outerHTMLSnippet: el.outerHTML.slice(0, 200),
          values,
        };
      });
    },
    { selector, properties }
  );
}

module.exports = { resolveCSSVariables, getComputedStyles };
