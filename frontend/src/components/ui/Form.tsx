'use client';

import { forwardRef, useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

const CONTROL =
  'w-full rounded-md border border-surface-border bg-surface px-3 text-base text-content placeholder:text-content-muted/70 ' +
  'focus:border-primary focus:outline-none focus-visible:outline-2 focus-visible:outline-primary disabled:bg-surface-muted disabled:opacity-70';

const CONTROL_INVALID = 'border-danger focus:border-danger';

interface FieldShellProps {
  id: string;
  label: string;
  help?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
  className?: string;
}

function FieldShell({ id, label, help, error, required, children, className }: FieldShellProps) {
  return (
    <div className={cn('space-y-1', className)}>
      <label htmlFor={id} className="block text-sm font-medium text-content">
        {label}
        {required ? <span aria-hidden="true" className="ml-0.5 text-danger">*</span> : null}
        {required ? <span className="sr-only"> (required)</span> : null}
      </label>
      {children}
      {help && !error ? (
        <p id={`${id}-help`} className="text-xs text-content-muted">
          {help}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs font-medium text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function describedBy(id: string, help?: string, error?: string): string | undefined {
  const ids = [help && !error ? `${id}-help` : null, error ? `${id}-error` : null].filter(Boolean);
  return ids.length > 0 ? ids.join(' ') : undefined;
}

export interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id' | 'className'> {
  label: string;
  help?: string;
  error?: string;
  containerClassName?: string;
}

export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField(
  { label, help, error, required, containerClassName, ...props },
  ref
) {
  const generated = useId();
  const id = props.name ? `${props.name}-${generated}` : generated;
  return (
    <FieldShell id={id} label={label} help={help} error={error} required={required} className={containerClassName}>
      <input
        ref={ref}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, help, error)}
        required={required}
        className={cn(CONTROL, 'h-11', error && CONTROL_INVALID)}
        {...props}
      />
    </FieldShell>
  );
});

export interface TextAreaFieldProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'id' | 'className'> {
  label: string;
  help?: string;
  error?: string;
  containerClassName?: string;
}

export const TextAreaField = forwardRef<HTMLTextAreaElement, TextAreaFieldProps>(function TextAreaField(
  { label, help, error, required, containerClassName, rows = 4, ...props },
  ref
) {
  const generated = useId();
  const id = props.name ? `${props.name}-${generated}` : generated;
  return (
    <FieldShell id={id} label={label} help={help} error={error} required={required} className={containerClassName}>
      <textarea
        ref={ref}
        id={id}
        rows={rows}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, help, error)}
        required={required}
        className={cn(CONTROL, 'py-2', error && CONTROL_INVALID)}
        {...props}
      />
    </FieldShell>
  );
});

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectFieldProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'id' | 'className' | 'children'> {
  label: string;
  options: SelectOption[];
  placeholder?: string;
  help?: string;
  error?: string;
  containerClassName?: string;
}

export const SelectField = forwardRef<HTMLSelectElement, SelectFieldProps>(function SelectField(
  { label, options, placeholder, help, error, required, containerClassName, ...props },
  ref
) {
  const generated = useId();
  const id = props.name ? `${props.name}-${generated}` : generated;
  return (
    <FieldShell id={id} label={label} help={help} error={error} required={required} className={containerClassName}>
      <select
        ref={ref}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(id, help, error)}
        required={required}
        className={cn(CONTROL, 'h-11', error && CONTROL_INVALID)}
        {...props}
      >
        {placeholder ? <option value="">{placeholder}</option> : null}
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
    </FieldShell>
  );
});

export interface CheckboxFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id' | 'className' | 'type'> {
  label: string;
  help?: string;
  error?: string;
}

export const CheckboxField = forwardRef<HTMLInputElement, CheckboxFieldProps>(function CheckboxField(
  { label, help, error, ...props },
  ref
) {
  const generated = useId();
  const id = props.name ? `${props.name}-${generated}` : generated;
  return (
    <div className="space-y-1">
      <div className="flex items-start gap-2">
        <input
          ref={ref}
          id={id}
          type="checkbox"
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy(id, help, error)}
          className="mt-0.5 h-5 w-5 rounded border-surface-border text-primary"
          {...props}
        />
        <label htmlFor={id} className="text-sm text-content">
          {label}
        </label>
      </div>
      {help && !error ? (
        <p id={`${id}-help`} className="text-xs text-content-muted">
          {help}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs font-medium text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
});

export function Switch({
  checked,
  onChange,
  label,
  disabled,
  name
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
  name?: string;
}) {
  const id = useId();
  return (
    <div className="flex items-center justify-between gap-3">
      <label htmlFor={id} className="text-sm text-content">
        {label}
      </label>
      <button
        id={id}
        name={name}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors',
          checked ? 'bg-primary' : 'bg-surface-border',
          disabled && 'opacity-60'
        )}
      >
        <span className="sr-only">{label}</span>
        <span className={cn('inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform', checked ? 'translate-x-5' : 'translate-x-0.5')} />
      </button>
    </div>
  );
}