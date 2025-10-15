import React, { useState } from 'react';
import './FeedbackModal.css'; // Reuse the same styles

const ResetModal = ({ isOpen, onClose, onSubmit }) => {
  const [newGoal, setNewGoal] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!newGoal.trim()) return;

    setIsSubmitting(true);
    try {
      await onSubmit(newGoal.trim());
      setNewGoal('');
      onClose();
    } catch (error) {
      console.error('Failed to reset:', error);
      alert('Failed to reset execution. Please try again.');
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
          <h2>🔄 Reset with New Goal</h2>
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
              <strong>⚠️ This will force complete the current goal and start completely fresh.</strong>
              <br /><br />
              All previous context, learnings, and investigation history will be cleared.
              The turn count will start from 1 again.
              <br /><br />
              Enter a new goal to investigate:
            </p>

            <textarea
              className="feedback-textarea"
              value={newGoal}
              onChange={(e) => setNewGoal(e.target.value)}
              placeholder="Describe your new infrastructure issue...&#10;&#10;Examples:&#10;• Database connection pool exhausted on production&#10;• High CPU usage on web servers after deployment&#10;• User authentication failing intermittently"
              rows={6}
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
              disabled={!newGoal.trim() || isSubmitting}
              style={{ backgroundColor: '#dc3545' }}
            >
              {isSubmitting ? 'Resetting...' : 'Reset & Start Fresh'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default ResetModal;
