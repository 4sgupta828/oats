// services/ui/src/components/Message.js
import React from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import remarkGfm from 'remark-gfm';

const Message = ({ message }) => {
  const { sender, text } = message;

  return (
    <div className={`message message-${sender}`}>
      <div className="message-label">{sender === 'user' ? 'You' : 'Agent'}</div>
      <div className="message-content">
        <ReactMarkdown
          children={text}
          remarkPlugins={[remarkGfm]} // Adds support for tables, strikethrough, etc.
          components={{
            // This is the custom renderer for code blocks
            code({ node, inline, className, children, ...props }) {
              const match = /language-(\w+)/.exec(className || '');
              return !inline && match ? (
                <SyntaxHighlighter
                  children={String(children).replace(/\n$/, '')}
                  style={vscDarkPlus}
                  language={match[1]}
                  PreTag="div"
                  {...props}
                />
              ) : (
                <code className={className} {...props}>
                  {children}
                </code>
              );
            },
          }}
        />
      </div>
    </div>
  );
};

export default Message;