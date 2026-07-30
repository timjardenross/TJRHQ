import { ButtonHTMLAttributes, forwardRef } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
export type ButtonSize = 'sm' | 'md';

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: 'bg-wb-sage-deep text-white hover:bg-wb-ink disabled:hover:bg-wb-sage-deep',
  secondary:
    'border border-wb-line bg-wb-surface text-wb-ink hover:border-wb-sage-deep disabled:hover:border-wb-line',
  danger: 'bg-wb-crit-on text-white hover:bg-wb-crit-on/90 disabled:hover:bg-wb-crit-on',
  ghost: 'text-wb-sage-deep hover:underline disabled:hover:no-underline',
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: 'px-2.5 py-1 text-[12px]',
  md: 'px-4 py-2 text-[13px]',
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
