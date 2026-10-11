// Native-access boundary for the synthetic validator.
// Reuse the existing handler so authentication, Captain authorization,
// schema validation, size limits, and no-write behavior cannot diverge.
export { POST } from '../validate/route';
