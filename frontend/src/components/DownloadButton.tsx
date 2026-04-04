interface DownloadButtonProps {
  columns: string[];
  rows: (string | number | null)[][];
  filename?: string;
}

export default function DownloadButton({
  columns,
  rows,
  filename = "ask-vj-export",
}: DownloadButtonProps) {
  async function handleDownload() {
    const XLSX = await import("xlsx");
    const ws = XLSX.utils.aoa_to_sheet([columns, ...rows]);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Data");
    XLSX.writeFile(wb, `${filename}-${Date.now()}.xlsx`);
  }

  return (
    <button
      onClick={handleDownload}
      className="flex items-center gap-1.5 rounded-md border border-gray-200 px-3 py-1.5 text-xs text-gray-500 transition-colors hover:text-brand"
    >
      <svg
        className="h-3.5 w-3.5"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5m0 0l5-5m-5 5V3"
        />
      </svg>
      Download Excel
    </button>
  );
}
