const LOCAL_DATE_TIME = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });
const UTC_DATE_TIME = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" });

export function formatDateTime(value: Date | string, utc = false): string | null {
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.valueOf())) return null;
  return `${(utc ? UTC_DATE_TIME : LOCAL_DATE_TIME).format(date)}${utc ? " UTC" : ""}`;
}
