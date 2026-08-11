import { ButtonHTMLAttributes, forwardRef } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
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
  danger: 'bg-wb-crit-on text-white hover:bg-wb-crit-on/90 active:bg-wb-crit-on/80 disabled:hover:bg-wb-crit-on disabled:active:bg-wb-crit-on',
  ghost: 'text-wb-sage-deep hover:underline active:underline disabled:hover:no-underline disabled:active:no-underline',
};

// 2026-08-09 mobile/iPad review (P1): sm was ~24-26px tall (px-2.5 py-1,
// 12px text), md ~34px (px-4 py-2, 13px text) - both below the 44px
// touch-target minimum (Apple HIG / Material). Desktop mouse precision
// doesn't need 44px, but this component has no way to know which input
// is being used, so both sizes now clear the touch minimum; density-
// sensitive call sites can still reach for `sm` deliberately, it's just
// no longer touch-unsafe by default.
const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: 'px-3 py-2.5 text-[12px]',
  md: 'px-4 py-3 text-[13px]',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

/** TJR Design System — extracted from intelligence-workbench inline button classes. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'md', className = '', type = 'button', ...props },
  ref
) {
  return (
    <button
      ref={ref}
      type={type}
      className={`inline-flex items-center justify-center gap-1.5 rounded-md font-medium
        transition-colors focus-visible:outline focus-visible:outline-2
        focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep
        disabled:cursor-not-allowed disabled:opacity-50
        ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`}
      {...props}
    />
  );
});
