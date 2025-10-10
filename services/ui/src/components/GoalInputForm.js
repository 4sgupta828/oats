// services/ui/src/components/GoalInputForm.js
import React, { useState } from 'react';

const GoalInputForm = ({ onGoalSubmit, isConnected, isInvestigating }) => {
  const [goal, setGoal] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!goal.trim() || !isConnected || isInvestigating) return;
    
    onGoalSubmit(goal);
    setGoal(''); // Clear the input after submitting
  };

  return (
    <footer className="input-form-container">
      <form onSubmit={handleSubmit} className="input-form">
        <input
          type="text"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder={isInvestigating ? "Analysis in progress..." : "Describe an infrastructure issue (e.g., API returning 504 errors)"}
          disabled={!isConnected || isInvestigating}
          autoFocus
        />
        <button type="submit" disabled={!isConnected || isInvestigating}>
          {isInvestigating ? 'Analyzing...' : 'Start Analysis'}
        </button>
      </form>
    </footer>
  );
};

export default GoalInputForm;