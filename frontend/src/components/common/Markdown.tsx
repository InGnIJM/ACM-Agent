import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import Typography from "@mui/material/Typography";
import type { Components } from "react-markdown";

const components: Partial<Components> = {
  h1: ({ children }) => <Typography variant="h4" gutterBottom>{children}</Typography>,
  h2: ({ children }) => <Typography variant="h5" gutterBottom>{children}</Typography>,
  h3: ({ children }) => <Typography variant="h6" gutterBottom>{children}</Typography>,
  p: ({ children }) => <Typography variant="body1" sx={{ mb: 1.5, lineHeight: 1.8 }}>{children}</Typography>,
  code: ({ className, children }: any) => {
    const isInline = !className;
    if (isInline) {
      return <code style={{ backgroundColor: "#f0f0f0", padding: "2px 6px", borderRadius: 4, fontSize: "0.9em" }}>{children}</code>;
    }
    return (
      <pre style={{ backgroundColor: "#1e1e2e", color: "#cdd6f4", padding: 16, borderRadius: 8, overflowX: "auto", fontSize: "0.85em", lineHeight: 1.6 }}>
        <code>{children}</code>
      </pre>
    );
  },
};

interface MarkdownProps {
  content: string;
}

export function Markdown({ content }: MarkdownProps) {
  if (!content) return <Typography color="text.secondary">暂无内容</Typography>;
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]} components={components}>
      {content}
    </ReactMarkdown>
  );
}
