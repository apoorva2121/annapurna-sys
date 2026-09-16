import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/** Merge Tailwind classes so a caller's override actually wins, rather than losing to source order. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
