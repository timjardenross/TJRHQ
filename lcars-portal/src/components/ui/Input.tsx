import { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes, forwardRef, useId } from 'react';

const FIELD_CLASSES =
  'w-full rounded-md border border-wb-line bg-wb-surface px-3 py-2 text-[13px] text-wb-ink ' +
  'placeholder:text-wb-ink2 focus-visible:outline focus-visible:outline-2 ' +
  'focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep disabled:cursor-not-allowed disabled:opacity-50';

function FieldWrapper({ id, label, hint, children }: { id: string; label?: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      {label && (
        <label htmlFor={id} className="text-[12px] font-medium text-wb-ink2">
          {label}
        </label>
      )}
      {children}
      {hint && <span className="text-[11px] text-wb-ink2">{hint}</span>}
    </div>
  );
}

export interface TextInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
}

/** TJR Design System — generalized from public-site + workbench form fields. */
export const Input = forwardRef<HTMLInputElement, TextInputProps>(function Input(
  { label, hint, id, className = '', ...props },
  ref
) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  return (
    <FieldWrapper id={fieldId} label={label} hint={hint}>
      <input ref={ref} id={fieldId} className={`${FIELD_CLASSES} ${className}`} {...props} />
    </FieldWrapper>
  );
});

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  hint?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, hint, id, className = '', ...props },
  ref
) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  return (
    <FieldWrapper id={fieldId} label={label} hint={hint}>
      <textarea ref={ref} id={fieldId} className={`${FIELD_CLASSES} ${className}`} {...props} />
    </FieldWrapper>
  );
});

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  hint?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, hint, id, className = '', children, ...props },
  ref
) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  return (
    <FieldWrapper id={fieldId} label={label} hint={hint}>
      <select ref={ref} id={fieldId} className={`${FIELD_CLASSES} ${className}`} {...props}>
        {children}
      </select>
    </FieldWrapper>
  );
});

export interface CheckboxProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(function Checkbox(
  { label, id, className = '', ...props },
  ref
) {
  const autoId = useId();
  const fieldId = id ?? autoId;
  return (
    <div className="flex items-center gap-2">
      <input
        ref={ref}
        id={fieldId}
        type="checkbox"
        className={`h-4 w-4 rounded border-wb-line text-wb-sage-deep focus-visible:outline
          focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-wb-sage-deep ${className}`}
        {...props}
      />
      <label htmlFor={fieldId} className="text-[13px] text-wb-ink">
        {label}
      </label>
    </div>
  );
});
