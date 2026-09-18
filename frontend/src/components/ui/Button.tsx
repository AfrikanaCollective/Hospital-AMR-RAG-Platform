import type { ButtonHTMLAttributes } from "react";

type Variant = "default" | "primary" | "danger";

const VARIANT_CLASSES: Record<Variant, string> = {
  default:
    "bg-surface border-border text-ink hover:bg-surface-alt hover:border-ink-muted/40 active:bg-surface-alt",
  primary:
    "bg-accent-strong border-accent-strong text-on-accent hover:bg-accent hover:border-accent",
  danger:
    "bg-danger border-danger text-on-danger hover:bg-danger-strong hover:border-danger-strong",
};

// Shared button styling (contrast/focus/hover/active audit — DEVIATIONS
// #133): every interactive control in the app should render through this so
// focus-visible/hover/disabled states can't silently drift per call site.
export default function Button({
  variant = "default",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={`rounded-[10px] border px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:border-border disabled:bg-surface-alt disabled:text-ink-muted disabled:hover:bg-surface-alt ${VARIANT_CLASSES[variant]} ${className}`}
      {...props}
    />
  );
}
