import { ButtonHTMLAttributes, forwardRef } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'link';
export type ButtonSize = 'sm' | 'md';

// 2026-08-09 mobile/iPad review (P1): every variant's only state change
// beyond the default was `hover:`, which never fires on touch - a press
// on mobile gave zero visual feedback. Added an `active:` (touch's
// equivalent of hover) to each variant, distinct enough from `hover:` to
// register as "yes, that registered" on a tap.
const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: 'bg-wb-sage-deep text-white hover:bg-wb-ink active:bg-wb-ink disabled:hover:bg-wb-sage-deep disabled:active:bg-wb-sage-deep',
  secondary:
    'border border-wb-line bg-wb-surface text-wb-ink hover:border-wb-sage-deep active:border-wb-sage-deep active:bg-wb-line/40 disabled:hover:border-wb-line disabled:active:border-wb-line disabled:active:bg-transparent',
  danger: 'bg-wb-crit-fill text-white hover:bg-wb-crit-fill/90 active:bg-wb-crit-fill/80 disabled:hover:bg-wb-crit-fill disabled:active:bg-wb-crit-fill',
  ghost: 'text-wb-sage-deep hover:underline active:underline disabled:hover:no-underline disabled:active:no-underline',
  // Quiet inline action that reads as a link (e.g. "Forgot password?", "Retry"): muted, underlined,
  // no padding of its own. Added in Stage B follow-up; ~20 hand-built buttons share this look.
  link: 'text-wb-ink2 underline underline-offset-2 hover:text-wb-ink',
};

// 2026-08-09 mobile/iPad review (P1): sm was ~24-26px tall (px-2.5 py-1,
// 12px text), md ~34px (px-4 py-2, 13px text) - both below the 44px
// touch-target minimum (Apple HIG / Material). Desktop mouse precision
// doesn't need 44px, but this component has no way to know which input
// is being used, so both sizes now clear the touch minimum; density-
// sensitive call sites can still reach for `sm` deliberately, it's just
// no longer touch-unsafe by default.
const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: 'px-3 py-2.5 text-wb-label',
  md: 'px-4 py-3 text-wb-body',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Uppercase, wide-tracked, bold label: the "Access Bridge" style used on the auth screens. */
  caps?: boolean;
  /** Fill the container's width. */
  fullWidth?: boolean;
}

/** TJR Design System — extracted from intelligence-workbench inline button classes. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'md', caps = false, fullWidth = false, className = '', type = 'button', ...props },
  ref
) {
  return (
    <button
      ref={ref}
      type={type}
      className={`inline-flex items-center justify-center gap-1.5 rounded-md ${caps ? 'font-bold' : variant === 'link' ? 'font-normal' : 'font-medium'}
        transition-colors focus-visible:outline focus-visible:outline-2
        focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep
        disabled:cursor-not-allowed ${variant === 'link' ? 'disabled:opacity-40' : 'disabled:opacity-50'}
        ${VARIANT_CLASSES[variant]} ${variant === 'link' ? 'self-start text-wb-label' : SIZE_CLASSES[size]}
        ${caps ? 'uppercase tracking-[0.2em]' : ''} ${fullWidth ? 'w-full' : ''} ${className}`}
      {...props}
    />
  );
});
