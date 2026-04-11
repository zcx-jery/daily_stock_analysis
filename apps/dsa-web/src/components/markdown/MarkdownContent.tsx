import type React from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownContentProps {
  content: string;
  className?: string;
}

const MarkdownContent: React.FC<MarkdownContentProps> = ({ content, className }) => (
  <div className={className}>
    <Markdown remarkPlugins={[remarkGfm]}>
      {content}
    </Markdown>
  </div>
);

export default MarkdownContent;
