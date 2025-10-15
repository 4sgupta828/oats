import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * Hook for Server-Sent Events streaming
 */
export function useSSE(backendUrl) {
  const [executionId, setExecutionId] = useState(null);
  const [events, setEvents] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const eventSourceRef = useRef(null);
  const processedEventIds = useRef(new Set());

  // Start a new execution
  const startExecution = useCallback(async (goal, maxTurns = 15) => {
    try {
      setIsExecuting(true);
      setEvents([]);
      processedEventIds.current.clear();

      const response = await fetch(`${backendUrl}/api/v1/executions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal,
          max_turns: maxTurns,
          user_id: 'web_user'
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      setExecutionId(result.execution_id);
      return result.execution_id;

    } catch (error) {
      console.error('Failed to start execution:', error);
      setIsExecuting(false);
      throw error;
    }
  }, [backendUrl]);

  // Listen for events when execution ID changes
  useEffect(() => {
    if (!executionId) return;

    const eventSource = new EventSource(
      `${backendUrl}/api/v1/executions/${executionId}/events`
    );

    eventSourceRef.current = eventSource;
    setIsConnected(true);

    eventSource.onopen = () => {
      console.log('SSE connection opened for execution:', executionId);
      setIsConnected(true);
    };

    eventSource.onerror = (error) => {
      console.error('SSE connection error:', error);
      setIsConnected(false);
    };

    // Handle all event types
    const eventTypes = [
      'execution_started',
      'turn_started',
      'llm_called',
      'llm_response_success',
      'llm_response_failed',
      'tool_started',
      'tool_success',
      'tool_failed',
      'execution_completed',
      'execution_failed',
      'execution_paused',
      'execution_aborted',
      'execution_stopped',
      'execution_reset',
      'user_interrupt',
      'interrupt_received',
      'feedback_injected',
      'llm_requests_input',
      'llm_requests_approval',
      'user_prompt_requested',
      'user_feedback_received',
      'execution_continued'
    ];

    eventTypes.forEach(eventType => {
      eventSource.addEventListener(eventType, (e) => {
        try {
          const data = JSON.parse(e.data);
          const event = {
            id: e.lastEventId,
            type: eventType,
            ...data
          };

          // Deduplicate events
          if (!processedEventIds.current.has(event.id)) {
            processedEventIds.current.add(event.id);
            setEvents(prev => [...prev, event]);

            // Check if execution is paused (never auto-close on pause)
            if (eventType === 'execution_paused') {
              setIsExecuting(false);
              // Keep connection open - user must continue or reset
            }

            // Only close on cancellation
            if (eventType === 'execution_aborted' || eventType === 'execution_stopped') {
              setIsExecuting(false);
              setTimeout(() => eventSource.close(), 1000);
            }
          }
        } catch (error) {
          console.error('Failed to parse SSE event:', error);
        }
      });
    });

    return () => {
      eventSource.close();
      setIsConnected(false);
    };
  }, [executionId, backendUrl]);

  const stopExecution = useCallback(async () => {
    if (!executionId) return;

    try {
      // Call abort endpoint to stop the backend execution
      const response = await fetch(`${backendUrl}/api/v1/executions/${executionId}/abort`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });

      if (!response.ok) {
        console.error('Failed to abort execution:', response.statusText);
      }
    } catch (error) {
      console.error('Failed to abort execution:', error);
    } finally {
      // Close SSE connection and reset UI state
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      setIsConnected(false);
      setIsExecuting(false);
    }
  }, [executionId, backendUrl]);

  const submitFeedback = useCallback(async (feedbackType, feedbackData) => {
    if (!executionId) return;

    try {
      // Get current turn number from latest event
      const turnNumber = events.length > 0 ? (events[events.length - 1].turn || 0) : 0;

      const response = await fetch(`${backendUrl}/api/v1/executions/${executionId}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          turn_number: turnNumber,
          interrupt_type: feedbackType,
          message: feedbackData
        })
      });

      if (!response.ok) {
        console.error('Failed to submit feedback:', response.statusText);
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      console.log('Feedback submitted successfully');
      return true;
    } catch (error) {
      console.error('Failed to submit feedback:', error);
      throw error;
    }
  }, [executionId, backendUrl, events]);

  // Continue execution with refined/additional goal
  const continueExecution = useCallback(async (goal, maxTurns = 15) => {
    if (!executionId) {
      throw new Error('No execution to continue');
    }

    try {
      setIsExecuting(true);

      const response = await fetch(`${backendUrl}/api/v1/executions/${executionId}/continue`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal,
          max_turns: maxTurns
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      console.log('Execution continued successfully:', result);
      return result;

    } catch (error) {
      console.error('Failed to continue execution:', error);
      setIsExecuting(false);
      throw error;
    }
  }, [executionId, backendUrl]);

  // Reset: Force complete current goal and start fresh
  const resetExecution = useCallback(async (goal, maxTurns = 15) => {
    if (!executionId) {
      throw new Error('No execution to reset');
    }

    try {
      setIsExecuting(true);

      const response = await fetch(`${backendUrl}/api/v1/executions/${executionId}/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          goal,
          max_turns: maxTurns
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();

      // Close current SSE connection
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      // Clear events and reset state
      setEvents([]);
      processedEventIds.current.clear();

      // Set new execution ID (this will trigger new SSE connection)
      setExecutionId(result.execution_id);

      console.log('Execution reset successfully:', result);
      return result;

    } catch (error) {
      console.error('Failed to reset execution:', error);
      setIsExecuting(false);
      throw error;
    }
  }, [executionId, backendUrl]);

  return {
    startExecution,
    stopExecution,
    submitFeedback,
    continueExecution,
    resetExecution,
    events,
    isConnected,
    isExecuting,
    executionId
  };
}
