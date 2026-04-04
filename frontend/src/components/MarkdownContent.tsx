import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownContentProps {
  content: string;
}

export default function MarkdownContent({ content }: MarkdownContentProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        // Custom styles for chat bubble context - compact and clean
        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
        strong: ({ children }) => (
          <strong className="font-semibold">{children}</strong>
        ),
        ul: ({ children }) => (
          <ul className="mb-2 list-disc pl-4">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="mb-2 list-decimal pl-4">{children}</ol>
        ),
        li: ({ children }) => <li className="mb-0.5">{children}</li>,
        table: ({ children }) => (
          <div className="my-2 overflow-x-auto rounded border border-gray-200">
            <table className="min-w-full text-xs">{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="bg-gray-50">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="px-2 py-1 text-left font-medium text-gray-600">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="px-2 py-1 text-gray-700">{children}</td>
        ),
        code: ({ children }) => (
          <code className="rounded bg-gray-100 px-1 py-0.5 font-mono text-xs">
            {children}
          </code>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
