import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Props {
  text: string;
  className?: string;
}

export function AgentMarkdown({text, className}: Props) {
  return (
    <div className={className ?? 'agent-markdown'}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({children}) => <p>{children}</p>,
          strong: ({children}) => <strong>{children}</strong>,
          ol: ({children}) => <ol>{children}</ol>,
          ul: ({children}) => <ul>{children}</ul>,
          li: ({children}) => <li>{children}</li>,
          code: ({children}) => <code>{children}</code>,
          table: ({children}) => (
            <div className="md-table-wrap">
              <table>{children}</table>
            </div>
          ),
          thead: ({children}) => <thead>{children}</thead>,
          tbody: ({children}) => <tbody>{children}</tbody>,
          tr: ({children}) => <tr>{children}</tr>,
          th: ({children}) => <th>{children}</th>,
          td: ({children}) => <td>{children}</td>,
        }}>
        {text}
      </ReactMarkdown>
    </div>
  );
}
