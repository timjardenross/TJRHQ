import { HTMLAttributes, ReactNode } from 'react';

export type CardVariant = 'elevated' | 'outlined';

export interface CardProps extends HTMLAttributes<HTMLElement> {
  title?: string;
  variant?: CardVariant;
  children: ReactNode;
}

const VARIANT_CLASSES: Record<CardVariant, string> = {
  elevated: 'shadow-sm',
  outlined: 'shadow-none',
};

/** TJR Design System — extracted from intelligence-workbench/_components/Shell.tsx. */
export function Card({ title, variant = 'elevated', className = '', children, ...props }: CardProps) {
  return (
    <section
      className={`rounded-lg border border-wb-line bg-wb-surface p-6 ${VARIANT_CLASSES[variant]} ${className}`}
      {...props}
    >
      {title && <h2 className="mb-3 border-b border-wb-line pb-3 font-serif text-lg text-wb-ink">{title}</h2>}
      {children}
    </section>
  );
}
