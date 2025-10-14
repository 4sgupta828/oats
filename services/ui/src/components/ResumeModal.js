import React, { useState } from 'react';
import './ResumeModal.css';

/**
 * ResumeModal - Modal for resuming/continuing execution with new goal
 *
 * Provides two modes:
 * - NEW: Start fresh (resets turns, clears history)
 * - CONTINUE: Keep learnings, summarize old turns
 */
function ResumeModal({ isOpen, onClose, onSubmit, executionSummary }) {
  const [goal, setGoal] = useState('');
  const [mode, setMode] = useState('continue'); // default to continue
  const [keepLastNTurns, setKeepLastNTurns] = useState(3);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!goal.trim()) {
      setError('Please enter a goal');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      await onSubmit(mode, goal.trim(), keepLastNTurns);
      // Reset form
      setGoal('');
      setMode('continue');
      setKeepLastNTurns(3);
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to resume execution');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    if (!isSubmitting) {
      setGoal('');
      setError(null);
      onClose();
    }
  };

  return (
    <div className="resume-modal-overlay" onClick={handleClose}>
      <div className="resume-modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="resume-modal-header">
          <h2>Resume Investigation</h2>
          <button
            className="close-button"
            onClick={handleClose}
            disabled={isSubmitting}
          >
            ×
          </button>
        </div>

        {executionSummary && (
          <div className="execution-summary">
            <h3>Previous Execution Summary</h3>
            <div className="summary-stats">
              <div className="stat">
                <span className="stat-label">Turns:</span>
                <span className="stat-value">{executionSummary.turns || 0}</span>
              </div>
              <div className="stat">
                <span className="stat-label">Status:</span>
                <span className="stat-value">{executionSummary.status || 'unknown'}</span>
              </div>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Resume Mode</label>
            <div className="mode-options">
              <label className={`mode-option ${mode === 'continue' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="mode"
                  value="continue"
                  checked={mode === 'continue'}
                  onChange={(e) => setMode(e.target.value)}
                  disabled={isSubmitting}
                />
                <div className="mode-details">
                  <div className="mode-title">🔄 Continue</div>
                  <div className="mode-description">
                    Keep learnings (facts, ruled-out hypotheses, diagnosis) but summarize old turns to prevent context bloat
                  </div>
                </div>
              </label>

              <label className={`mode-option ${mode === 'new' ? 'selected' : ''}`}>
                <input
                  type="radio"
                  name="mode"
                  value="new"
                  checked={mode === 'new'}
                  onChange={(e) => setMode(e.target.value)}
                  disabled={isSubmitting}
                />
                <div className="mode-details">
                  <div className="mode-title">🆕 New</div>
                  <div className="mode-description">
                    Start completely fresh (resets turns, clears all history)
                  </div>
                </div>
              </label>
            </div>
          </div>

          {mode === 'continue' && (
            <div className="form-group">
              <label htmlFor="keepTurns">
                Keep Last N Turns
                <span className="help-text">How many recent turns to keep for immediate context</span>
              </label>
              <input
                id="keepTurns"
                type="number"
                min="1"
                max="10"
                value={keepLastNTurns}
                onChange={(e) => setKeepLastNTurns(parseInt(e.target.value, 10))}
                disabled={isSubmitting}
              />
            </div>
          )}

          <div className="form-group">
            <label htmlFor="goal">
              {mode === 'new' ? 'New Goal' : 'Refined Goal'}
            </label>
            <textarea
              id="goal"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              placeholder={
                mode === 'new'
                  ? "Enter a completely new investigation goal..."
                  : "Refine or adjust your investigation goal..."
              }
              rows={4}
              disabled={isSubmitting}
              autoFocus
            />
          </div>

          {error && (
            <div className="error-message">
              ⚠️ {error}
            </div>
          )}

          <div className="modal-actions">
            <button
              type="button"
              onClick={handleClose}
              className="cancel-button"
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="submit-button"
              disabled={isSubmitting || !goal.trim()}
            >
              {isSubmitting ? 'Resuming...' : mode === 'new' ? 'Start New' : 'Continue'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default ResumeModal;
