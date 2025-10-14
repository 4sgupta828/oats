import React, { useState } from 'react';
import './FeedbackModal.css';

const FeedbackModal = ({ isOpen, onClose, onSubmit }) => {
  const [feedback, setFeedback] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!feedback.trim()) return;

    setIsSubmitting(true);
    try {
      await onSubmit(feedback.trim());
      setFeedback('');
      onClose();
    } catch (error) {
      console.error('Failed to submit feedback:', error);
      alert('Failed to submit feedback. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div className="feedback-modal-backdrop" onClick={handleBackdropClick}>
      <div className="feedback-modal">
        <div className="feedback-modal-header">
          <h2>💬 Provide Guidance to Agent</h2>
          <button
            className="feedback-modal-close"
            onClick={onClose}
            disabled={isSubmitting}
          >
            ×
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="feedback-modal-body">
            <p className="feedback-instructions">
              Provide guidance to help the agent. The agent will see your feedback and continue execution with this context.
              Use this to redirect the agent's focus or provide additional information.
            </p>

            <textarea
              className="feedback-textarea"
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="Enter your guidance here...&#10;&#10;Examples:&#10;• Focus on checking database connections first&#10;• Look at the error logs from the last hour&#10;• The issue is likely in the authentication service"
              rows={8}
              autoFocus
              disabled={isSubmitting}
            />
          </div>

          <div className="feedback-modal-footer">
            <button
              type="button"
              className="feedback-modal-button feedback-modal-cancel"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="feedback-modal-button feedback-modal-submit"
              disabled={!feedback.trim() || isSubmitting}
            >
              {isSubmitting ? 'Submitting...' : 'Submit Guidance'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default FeedbackModal;
