export type DisplayValue = boolean | Date | null | number | string | undefined;

export function displayValue(value: DisplayValue): string {
  if (value == null || value === "") return "-";
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? "-" : value.toISOString();
  return String(value);
}
