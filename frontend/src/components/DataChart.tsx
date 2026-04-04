import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  Cell,
} from "recharts";

interface DataChartProps {
  columns: string[];
  rows: (string | number | null)[][];
}

type ChartType = "bar" | "grouped-bar" | "line" | "pie" | "none";
type ColType = "date" | "numeric" | "label";

const COLORS = ["#1e3a5f", "#e8a838", "#2d5a8e", "#16a34a", "#d97706"];

function classifyColumns(
  columns: string[],
  rows: (string | number | null)[][]
): ColType[] {
  const sample = rows.slice(0, 10);
  const datePattern = /^\d{4}-\d{2}/;
  const dateNamePattern = /date|month|year|quarter/i;

  return columns.map((colName, colIdx) => {
    let dateCount = 0;
    let numCount = 0;
    let total = 0;

    for (const row of sample) {
      const val = row[colIdx];
      if (val == null) continue;
      total++;
      if (typeof val === "number") {
        numCount++;
      } else if (
        typeof val === "string" &&
        datePattern.test(val)
      ) {
        dateCount++;
      }
    }

    if (dateNamePattern.test(colName) || (total > 0 && dateCount / total > 0.5))
      return "date";
    if (total > 0 && numCount / total > 0.5) return "numeric";
    return "label";
  });
}

function selectChartType(
  colTypes: ColType[],
  rowCount: number
): ChartType {
  const dateCols = colTypes.filter((t) => t === "date").length;
  const numCols = colTypes.filter((t) => t === "numeric").length;
  const labelCols = colTypes.filter((t) => t === "label").length;

  if (dateCols >= 1 && numCols >= 1) return "line";
  if (labelCols >= 1 && numCols === 1 && rowCount <= 8) return "pie";
  if (labelCols >= 1 && numCols === 1) return "bar";
  if (labelCols >= 1 && numCols >= 2) return "grouped-bar";
  if (rowCount > 30) return "none";
  return "none";
}

export default function DataChart({ columns, rows }: DataChartProps) {
  const colTypes = classifyColumns(columns, rows);
  const chartType = selectChartType(colTypes, rows.length);

  if (chartType === "none") return null;

  // Convert rows to recharts data format
  const data = rows.map((row) => {
    const obj: Record<string, string | number | null> = {};
    columns.forEach((col, i) => {
      obj[col] = row[i];
    });
    return obj;
  });

  // Find key columns by type
  const xCol =
    columns[colTypes.findIndex((t) => t === "date")] ??
    columns[colTypes.findIndex((t) => t === "label")];
  const numericCols = columns.filter((_, i) => colTypes[i] === "numeric");

  return (
    <div className="rounded-lg border border-gray-200 p-3">
      <ResponsiveContainer width="100%" height={300}>
        {chartType === "line" ? (
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey={xCol} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend />
            {numericCols.map((col, i) => (
              <Line
                key={col}
                type="monotone"
                dataKey={col}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={2}
                dot={false}
              />
            ))}
          </LineChart>
        ) : chartType === "bar" ? (
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey={xCol} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend />
            <Bar dataKey={numericCols[0]} fill={COLORS[0]} />
          </BarChart>
        ) : chartType === "grouped-bar" ? (
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey={xCol} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Legend />
            {numericCols.map((col, i) => (
              <Bar key={col} dataKey={col} fill={COLORS[i % COLORS.length]} />
            ))}
          </BarChart>
        ) : (
          <PieChart>
            <Tooltip />
            <Legend />
            <Pie
              data={data}
              dataKey={numericCols[0]}
              nameKey={xCol}
              cx="50%"
              cy="50%"
              outerRadius={100}
              label
            >
              {data.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Pie>
          </PieChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
