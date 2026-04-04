interface DataTableProps {
  columns: string[];
  rows: (string | number | null)[][];
  maxDisplayRows?: number;
}

export default function DataTable({
  columns,
  rows,
  maxDisplayRows = 50,
}: DataTableProps) {
  // Detect numeric columns: >50% of values are numbers
  const numericColumns = new Set<number>();
  columns.forEach((_, colIdx) => {
    let numCount = 0;
    let total = 0;
    for (const row of rows) {
      const val = row[colIdx];
      if (val != null) {
        total++;
        if (typeof val === "number") numCount++;
      }
    }
    if (total > 0 && numCount / total > 0.5) {
      numericColumns.add(colIdx);
    }
  });

  const truncated = rows.length > maxDisplayRows;
  const displayRows = truncated ? rows.slice(0, maxDisplayRows) : rows;

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200">
      <table className="min-w-full text-xs">
        <thead>
          <tr className="bg-brand-dark text-white">
            {columns.map((col, i) => (
              <th
                key={i}
                className={`sticky top-0 bg-brand-dark px-2 py-1.5 font-medium ${
                  numericColumns.has(i) ? "text-right" : "text-left"
                }`}
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {displayRows.map((row, rowIdx) => (
            <tr key={rowIdx} className="even:bg-gray-50">
              {columns.map((_, colIdx) => {
                const val = row[colIdx];
                return (
                  <td
                    key={colIdx}
                    className={`px-2 py-1.5 ${
                      numericColumns.has(colIdx) ? "text-right" : "text-left"
                    }`}
                  >
                    {val == null ? "—" : String(val)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {truncated && (
        <div className="border-t border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-500">
          Showing {maxDisplayRows} of {rows.length} rows. Download for full
          data.
        </div>
      )}
    </div>
  );
}
