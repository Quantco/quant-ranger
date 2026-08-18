import { useEffect, useMemo, useState } from "react";

import "./copier-dashboard.css";
import { BooleanChartsSections, DashboardHeader, PieChartsSection, RepositoriesSection } from "./DashboardContent";
import { DashboardSidebar } from "./DashboardSidebar";
import { TextFilterControl, ValueFilterControl } from "./FilterControls";
import { copierDashboardHash, readCopierDashboardUrlState } from "./dashboard-url";
import { COPIER_ANSWERS, REPOSITORIES, TEMPLATE, VALIDATION, VERSION, answerCounts, countAllValues, countBy, filterRowsByTextFilters, filterRowsByValueFilters, removeValueFilter } from "./dashboard";
import type { CountedValue, DashboardRow, DashboardSnapshot, DashboardValue, TextFilter, ValueFilter } from "./dashboard";

function versionDistribution(data: CountedValue[], versions: string[]) {
  const order = new Map(versions.map((version, index) => [version, index]));
  return [...data].sort((left, right) => (order.get(String(left.value)) ?? Infinity) - (order.get(String(right.value)) ?? Infinity));
}

export default function CopierDashboard({ snapshot }: { snapshot: DashboardSnapshot }) {
  const rows = snapshot.rows;
  const [initialUrlState] = useState(() => readCopierDashboardUrlState(snapshot));
  const [hiddenBooleanColumns, setHiddenBooleanColumns] = useState(initialUrlState.hiddenBooleanColumns);
  const [selectedChartColumns, setSelectedChartColumns] = useState(initialUrlState.selectedChartColumns);
  const [selectedFilterColumns, setSelectedFilterColumns] = useState(initialUrlState.selectedFilterColumns);
  const [selectedRows, setSelectedRows] = useState<DashboardRow[] | null>(null);
  const [selectedTableColumns, setSelectedTableColumns] = useState(initialUrlState.selectedTableColumns);
  const [tableSort, setTableSort] = useState(initialUrlState.sort);
  const [textFilters, setTextFilters] = useState<TextFilter[]>(initialUrlState.textFilters);
  const [valueFilters, setValueFilters] = useState<ValueFilter[]>(initialUrlState.valueFilters);

  useEffect(() => {
    const hash = copierDashboardHash({ hiddenBooleanColumns, selectedChartColumns, selectedFilterColumns, selectedTableColumns, sort: tableSort, textFilters, valueFilters });
    if (window.location.hash !== hash) window.history.replaceState(window.history.state, "", hash);
  }, [hiddenBooleanColumns, selectedChartColumns, selectedFilterColumns, selectedTableColumns, tableSort, textFilters, valueFilters]);

  const textFilteredRows = useMemo(() => filterRowsByTextFilters(rows, textFilters), [rows, textFilters]);
  const filteredRows = useMemo(() => filterRowsByValueFilters(textFilteredRows, valueFilters), [textFilteredRows, valueFilters]);
  const textFilterByColumn = useMemo(() => new Map(textFilters.map((filter) => [filter.column, filter])), [textFilters]);
  const valueFilterByColumn = useMemo(() => new Map(valueFilters.map((filter) => [filter.column, filter])), [valueFilters]);

  const answerColumns = new Set(snapshot.answer_groups.flatMap(({ fields }) => fields));
  const valueFilterColumns = new Set([REPOSITORIES, TEMPLATE, VERSION, VALIDATION, ...answerColumns]);
  const filterColumns = snapshot.columns.filter((column) => column !== COPIER_ANSWERS);
  const templateFilter = valueFilterByColumn.get(TEMPLATE);
  const selectedTemplates = templateFilter?.inverted ? [] : (templateFilter?.values.filter((value): value is string => typeof value === "string") ?? []);
  const effectiveTemplate = selectedTemplates.length === 1 ? selectedTemplates[0] : null;
  const booleanColumns = [...new Set(snapshot.answer_groups.filter(({ template }) => template === effectiveTemplate).flatMap(({ fields }) => fields))];
  const selectedBooleanColumns = new Set(booleanColumns.filter((column) => !hiddenBooleanColumns.has(column)));
  const versions = [
    ...new Set(
      snapshot.version_options.filter(({ template }) => selectedTemplates.length === 0 || template == null || selectedTemplates.includes(template)).flatMap(({ versions: options }) => options),
    ),
  ];

  const availableTableColumns = selectedTemplates.length === 0 ? snapshot.columns : snapshot.columns.filter((column) => column !== COPIER_ANSWERS);
  const visibleTableColumns = availableTableColumns.filter((column) => column === REPOSITORIES || selectedTableColumns.has(column));
  const filteredRowSet = new Set(filteredRows);
  const repositoryNames = (selectedRows ?? filteredRows).filter((row) => filteredRowSet.has(row)).map((row) => row.repository);

  const setTextQuery = (column: string, query: string) => {
    setTextFilters((current) => {
      const otherFilters = current.filter((filter) => filter.column !== column);
      const existingFilter = current.find((filter) => filter.column === column);
      return query.trim() === "" ? otherFilters : [...otherFilters, { column, inverted: existingFilter?.inverted, query }];
    });
  };

  const setSelectedValues = (column: string, values: DashboardValue[]) => {
    setValueFilters((current) => {
      const otherFilters = removeValueFilter(current, column);
      const existingFilter = current.find((filter) => filter.column === column);
      return values.length === 0 ? otherFilters : [...otherFilters, { column, inverted: existingFilter?.inverted, values }];
    });
  };

  const setTextFilterInverted = (column: string, inverted: boolean) =>
    setTextFilters((current) => current.map((filter) => (filter.column === column ? { ...filter, inverted: inverted || undefined } : filter)));

  const setValueFilterInverted = (column: string, inverted: boolean) =>
    setValueFilters((current) => current.map((filter) => (filter.column === column ? { ...filter, inverted: inverted || undefined } : filter)));

  const updateFilterColumns = (columns: Set<string>) => {
    const removedColumns = new Set([...selectedFilterColumns].filter((column) => !columns.has(column)));
    setSelectedFilterColumns(columns);
    if (removedColumns.size === 0) return;
    setTextFilters((current) => current.filter(({ column }) => !removedColumns.has(column)));
    setValueFilters((current) => current.filter(({ column }) => !removedColumns.has(column)));
  };

  const resetFilters = () => {
    setTextFilters([]);
    setValueFilters([]);
  };

  const setSelectedBooleanColumns = (columns: Set<string>) => {
    setHiddenBooleanColumns((current) => {
      const next = new Set(current);
      for (const column of booleanColumns) {
        if (columns.has(column)) next.delete(column);
        else next.add(column);
      }
      return next;
    });
  };

  const filterOptionsFor = (column: string) => {
    const countValues = answerColumns.has(column) ? answerCounts : countBy;
    const options = countValues(filterRowsByValueFilters(textFilteredRows, valueFilters, column), column);
    const selectedValues = valueFilterByColumn.get(column)?.values ?? [];
    const missingOptions = selectedValues.filter((selectedValue) => !options.some(({ value }) => Object.is(value, selectedValue))).map((value) => ({ count: 0, value }));
    const allOptions = [...missingOptions, ...options];
    return column === VERSION ? versionDistribution(allOptions, versions) : allOptions;
  };

  const textFilterOptionsFor = (column: string) =>
    countBy(
      filterRowsByValueFilters(
        filterRowsByTextFilters(
          rows,
          textFilters.filter((filter) => filter.column !== column),
        ),
        valueFilters,
      ),
      column,
    );

  const filterControls = [...selectedFilterColumns]
    .filter((column) => filterColumns.includes(column))
    .map((column) =>
      valueFilterColumns.has(column) ? (
        <ValueFilterControl
          column={column}
          filter={valueFilterByColumn.get(column)}
          key={column}
          onChange={(values) => setSelectedValues(column, values)}
          onInvert={(inverted) => setValueFilterInverted(column, inverted)}
          options={filterOptionsFor(column)}
        />
      ) : (
        <TextFilterControl
          column={column}
          filter={textFilterByColumn.get(column)}
          key={column}
          onChange={(query) => setTextQuery(column, query)}
          onInvert={(inverted) => setTextFilterInverted(column, inverted)}
          options={textFilterOptionsFor(column)}
        />
      ),
    );

  const pieCharts = snapshot.columns.filter((column) => selectedChartColumns.has(column)).map((column) => ({ column, data: countAllValues(filteredRows, column) }));
  const booleanChartGroups = snapshot.answer_groups
    .filter(({ template }) => template === effectiveTemplate)
    .map((group) => ({
      ...group,
      charts: group.fields
        .filter((column) => selectedBooleanColumns.has(column))
        .map((column) => ({ column, rows: filteredRows }))
        .filter(({ column }) => answerCounts(filteredRows, column).length > 0),
    }))
    .filter(({ charts }) => charts.length > 0);

  return (
    <main>
      <DashboardHeader generatedAt={snapshot.generated_at} repositoryCount={rows.length} />

      <div className="copier-dashboard-layout">
        <DashboardSidebar
          activeFilterCount={textFilters.length + valueFilters.length}
          booleanOptions={{ fields: booleanColumns, onChange: setSelectedBooleanColumns, selected: selectedBooleanColumns }}
          filters={{ controls: filterControls, fields: filterColumns, onChange: updateFilterColumns, selected: selectedFilterColumns }}
          onResetFilters={resetFilters}
          pieCharts={{ fields: snapshot.columns, onChange: setSelectedChartColumns, selected: selectedChartColumns }}
          tableColumns={{ fields: availableTableColumns, onChange: setSelectedTableColumns, selected: selectedTableColumns, visibleCount: visibleTableColumns.length }}
        />

        <div className="copier-dashboard-content">
          <RepositoriesSection columns={visibleTableColumns} onSelectionChange={setSelectedRows} onSortChange={setTableSort} repositoryNames={repositoryNames} rows={filteredRows} sort={tableSort} />
          <PieChartsSection charts={pieCharts} />
          <BooleanChartsSections groups={booleanChartGroups} />
        </div>
      </div>
    </main>
  );
}
