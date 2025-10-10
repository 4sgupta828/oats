// services/ui/src/components/MessageContainer.js
import React, { useEffect, useRef } from 'react';
import Message from './Message';

const MessageContainer = ({ messages, isInvestigating }) => {
  const messagesEndRef = useRef(null);

  // This effect will run every time the 'messages' array changes,
  // ensuring we always scroll to the latest message.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="message-container">
      {messages.map((msg, index) => (
        <Message key={index} message={msg} />
      ))}
      
      {/* Show a spinner while the agent is working */}
      {isInvestigating && <div className="spinner"></div>}

      {/* This empty div is the target for our auto-scrolling */}
      <div ref={messagesEndRef} />
    </div>
  );
};

export default MessageContainer;