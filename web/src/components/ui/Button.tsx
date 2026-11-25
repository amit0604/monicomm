import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

// Shared button (PROJECT.md 6A). Keep one primary button per view.
export function Button({
  variant = "secondary",
  className,
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  const cls = ["button", `button--${variant}`, className].filter(Boolean).join(" ");
  return <button type={type} className={cls} {...props} />;
}
