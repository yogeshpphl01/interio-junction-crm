/*
  <module name="lib/utils">
    <purpose>cn(): merge conditional class names (clsx) and de-duplicate
    conflicting Tailwind classes (tailwind-merge). Used by the shadcn/ui parts.</purpose>
  </module>
*/
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge"

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
