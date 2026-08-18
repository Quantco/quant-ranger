import type { DataTableSort } from "../components/DataTable";
import { COPIER_ANSWERS, REPOSITORIES, TEMPLATE, VALIDATION, VERSION } from "./dashboard";
import type { DashboardSnapshot, DashboardValue, TextFilter, ValueFilter } from "./dashboard";

export const DEFAULT_FILTER_COLUMNS = [REPOSITORIES, TEMPLATE, VERSION];
export const DEFAULT_TABLE_COLUMNS = [VALIDATION, TEMPLATE, VERSION];

export interface CopierDashboardUrlState {
  hiddenBooleanColumns: Set<string>;
  selectedChartColumns: Set<string>;
  selectedFilterColumns: Set<string>;
  selectedTableColumns: Set<string>;
  sort: DataTableSort | null;
  textFilters: TextFilter[];
  valueFilters: ValueFilter[];
}

function queryParameters(hash: string): URLSearchParams {
  const queryStart = hash.indexOf("?");
  return new URLSearchParams(queryStart === -1 ? "" : hash.slice(queryStart + 1));
}

function isDashboardValue(value: unknown): value is DashboardValue {
  return value == null || typeof value === "boolean" || typeof value === "number" || typeof value === "string";
}

function parseValueFilter(rawFilter: string, columns: Set<string>): ValueFilter | null {
  try {
    const parsed: unknown = JSON.parse(rawFilter);
    if (!Array.isArray(parsed)) return null;
    const column = parsed[0];
    let inverted = false;
    let rawValues: unknown[] = [];
    if (parsed.length === 2 || (parsed.length === 3 && typeof parsed[2] === "boolean")) {
      rawValues = Array.isArray(parsed[1]) ? parsed[1] : [parsed[1]];
      inverted = parsed[2] === true;
    } else if (parsed.length === 3 && (parsed[1] === "include" || parsed[1] === "exclude")) {
      rawValues = [parsed[2]];
      inverted = parsed[1] === "exclude";
    }
    if (typeof column !== "string" || !columns.has(column) || rawValues.length === 0 || !rawValues.every(isDashboardValue)) return null;
    return { column, inverted: inverted || undefined, values: rawValues };
  } catch {
    return null;
  }
}

function parseTextFilter(rawFilter: string, columns: Set<string>): TextFilter | null {
  try {
    const parsed: unknown = JSON.parse(rawFilter);
    if (!Array.isArray(parsed) || (parsed.length !== 2 && parsed.length !== 3)) return null;
    const [column, query] = parsed;
    const inverted = parsed[2];
    return typeof column === "string" && columns.has(column) && typeof query === "string" && query.trim() !== "" && (inverted == null || typeof inverted === "boolean")
      ? { column, inverted: inverted === true || undefined, query }
      : null;
  } catch {
    return null;
  }
}

function repositoriesMatching(snapshot: DashboardSnapshot, query: string): string[] {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const matches = [...new Set(snapshot.rows.map(({ repository }) => repository).filter((repository) => repository.toLocaleLowerCase().includes(normalizedQuery)))];
  return matches.length === 0 ? [query] : matches;
}

export function readCopierDashboardUrlState(snapshot: DashboardSnapshot, hash = window.location.hash): CopierDashboardUrlState {
  const parameters = queryParameters(hash);
  const columns = new Set(snapshot.columns);
  const filterColumns = new Set(snapshot.columns.filter((column) => column !== COPIER_ANSWERS));
  const booleanColumns = new Set(snapshot.answer_groups.flatMap(({ fields }) => fields));
  const valueFilterColumns = new Set([REPOSITORIES, TEMPLATE, VERSION, VALIDATION, ...booleanColumns]);
  const textFilterColumns = new Set([...filterColumns].filter((column) => !valueFilterColumns.has(column)));
  const valueFilterByColumn = new Map<string, ValueFilter>();
  const textFilterByColumn = new Map<string, TextFilter>();

  for (const rawFilter of parameters.getAll("filter")) {
    const filter = parseValueFilter(rawFilter, valueFilterColumns);
    if (filter != null) valueFilterByColumn.set(filter.column, filter);
  }
  for (const rawFilter of parameters.getAll("search")) {
    const filter = parseTextFilter(rawFilter, filterColumns);
    if (filter == null) continue;
    if (filter.column === REPOSITORIES) {
      if (!valueFilterByColumn.has(REPOSITORIES)) valueFilterByColumn.set(REPOSITORIES, { column: REPOSITORIES, inverted: filter.inverted, values: repositoriesMatching(snapshot, filter.query) });
    } else if (textFilterColumns.has(filter.column)) {
      textFilterByColumn.set(filter.column, filter);
    }
  }

  const legacyQuery = parameters.get("q");
  if (legacyQuery?.trim() && !valueFilterByColumn.has(REPOSITORIES)) valueFilterByColumn.set(REPOSITORIES, { column: REPOSITORIES, values: repositoriesMatching(snapshot, legacyQuery) });
  const legacyTemplate = parameters.get("template");
  if (legacyTemplate != null && snapshot.template_options.includes(legacyTemplate)) valueFilterByColumn.set(TEMPLATE, { column: TEMPLATE, values: [legacyTemplate] });
  const versions = new Set(snapshot.version_options.flatMap(({ versions: options }) => options));
  const legacyVersion = parameters.get("version");
  if (legacyVersion != null && versions.has(legacyVersion)) valueFilterByColumn.set(VERSION, { column: VERSION, values: [legacyVersion] });

  const selectedFilterColumns = parameters.has("field") ? new Set(parameters.getAll("field").filter((column) => filterColumns.has(column))) : new Set(DEFAULT_FILTER_COLUMNS);
  for (const column of [...textFilterByColumn.keys(), ...valueFilterByColumn.keys()]) selectedFilterColumns.add(column);
  const selectedChartColumns = new Set(parameters.getAll("chart").filter((column) => columns.has(column)));
  const hiddenBooleanColumns = new Set(parameters.getAll("hide-boolean").filter((column) => booleanColumns.has(column)));

  const selectedTableColumns = parameters.has("column") ? new Set(parameters.getAll("column").filter((column) => column !== REPOSITORIES && columns.has(column))) : new Set(DEFAULT_TABLE_COLUMNS);
  const sortColumn = parameters.get("sort");
  const sortDirection = parameters.get("direction");
  const sort: DataTableSort | null =
    sortColumn != null && columns.has(sortColumn) && (sortDirection === "ascending" || sortDirection === "descending") ? { direction: sortDirection, id: sortColumn } : null;

  return {
    hiddenBooleanColumns,
    selectedChartColumns,
    selectedFilterColumns,
    selectedTableColumns,
    sort,
    textFilters: [...textFilterByColumn.values()],
    valueFilters: [...valueFilterByColumn.values()],
  };
}

function setsEqual(left: Set<string>, right: Set<string>): boolean {
  return left.size === right.size && [...left].every((value) => right.has(value));
}

export function copierDashboardHash({ hiddenBooleanColumns, selectedChartColumns, selectedFilterColumns, selectedTableColumns, sort, textFilters, valueFilters }: CopierDashboardUrlState): string {
  const parameters = new URLSearchParams();
  for (const { column, inverted, query } of textFilters) parameters.append("search", JSON.stringify(inverted ? [column, query, true] : [column, query]));
  for (const { column, inverted, values } of valueFilters) parameters.append("filter", JSON.stringify(inverted ? [column, values, true] : [column, values]));
  for (const column of [...selectedChartColumns].sort()) parameters.append("chart", column);
  for (const column of [...hiddenBooleanColumns].sort()) parameters.append("hide-boolean", column);

  if (!setsEqual(selectedFilterColumns, new Set(DEFAULT_FILTER_COLUMNS))) {
    if (selectedFilterColumns.size === 0) parameters.append("field", "");
    else for (const column of selectedFilterColumns) parameters.append("field", column);
  }
  if (!setsEqual(selectedTableColumns, new Set(DEFAULT_TABLE_COLUMNS))) {
    if (selectedTableColumns.size === 0) parameters.append("column", "");
    else for (const column of [...selectedTableColumns].sort()) parameters.append("column", column);
  }
  if (sort != null) {
    parameters.set("sort", sort.id);
    parameters.set("direction", sort.direction);
  }

  const query = parameters.toString();
  return `#/copier${query === "" ? "" : `?${query}`}`;
}
