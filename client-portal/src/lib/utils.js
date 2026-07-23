import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

// cn(): merge conditional class lists, de-duplicating conflicting Tailwind classes.
export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
