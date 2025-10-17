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
        const errorText = await response.text().catch(() => response.statusText);
        console.error('[SSE] Failed to start execution - HTTP error', {
          status: response.status,
          statusText: response.statusText,
          errorText,
          goal: goal?.substring(0, 100),
          maxTurns,
          backendUrl
        });
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      setExecutionId(result.execution_id);
      console.log('[SSE] Execution started successfully', {
        execution_id: result.execution_id,
        goal: goal?.substring(0, 100),
        maxTurns
      });
      return result.execution_id;

    } catch (error) {
      console.error('[SSE] Failed to start execution - exception', {
        error: error.message,
        errorType: error.name,
        stack: error.stack,
        goal: goal?.substring(0, 100),
        maxTurns,
        backendUrl
      });
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
      console.log('[SSE] Connection opened', {
        execution_id: executionId,
        url: `${backendUrl}/api/v1/executions/${executionId}/events`,
        readyState: eventSource.readyState
      });
      setIsConnected(true);
    };

    eventSource.onerror = (error) => {
      console.error('[SSE] Connection error', {
        error,
        execution_id: executionId,
        readyState: eventSource.readyState,
        url: eventSource.url,
        eventSourceState: {
          CONNECTING: eventSource.CONNECTING,
          OPEN: eventSource.OPEN,
          CLOSED: eventSource.CLOSED,
          current: eventSource.readyState
        }
      });
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
              console.log('[SSE] Execution paused', {
                execution_id: executionId,
                event_id: event.id,
                turn: data.turn
              });
              // Keep connection open - user must continue or reset
            }

            // Only close on cancellation
            if (eventType === 'execution_aborted' || eventType === 'execution_stopped') {
              setIsExecuting(false);
              console.log('[SSE] Execution stopped, closing connection', {
                execution_id: executionId,
                event_type: eventType,
                event_id: event.id
              });
              setTimeout(() => eventSource.close(), 1000);
            }
          }
        } catch (error) {
          console.error('[SSE] Failed to parse SSE event', {
            error: error.message,
            errorType: error.name,
            stack: error.stack,
            execution_id: executionId,
            eventType,
            rawData: e.data?.substring(0, 500),
            lastEventId: e.lastEventId
          });
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
        const errorText = await response.text().catch(() => response.statusText);
        console.error('[SSE] Failed to abort execution - HTTP error', {
          status: response.status,
          statusText: response.statusText,
          errorText,
          execution_id: executionId,
          backendUrl
        });
      } else {
        console.log('[SSE] Execution aborted successfully', {
          execution_id: executionId
        });
      }
    } catch (error) {
      console.error('[SSE] Failed to abort execution - exception', {
        error: error.message,
        errorType: error.name,
        stack: error.stack,
        execution_id: executionId,
        backendUrl
      });
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
        const errorText = await response.text().catch(() => response.statusText);
        console.error('[SSE] Failed to submit feedback - HTTP error', {
          status: response.status,
          statusText: response.statusText,
          errorText,
          execution_id: executionId,
          turnNumber,
          feedbackType,
          feedbackDataPreview: feedbackData?.substring(0, 100),
          backendUrl
        });
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      console.log('[SSE] Feedback submitted successfully', {
        execution_id: executionId,
        turnNumber,
        feedbackType
      });
      return true;
    } catch (error) {
      console.error('[SSE] Failed to submit feedback - exception', {
        error: error.message,
        errorType: error.name,
        stack: error.stack,
        execution_id: executionId,
        turnNumber,
        feedbackType,
        backendUrl
      });
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
        console.error('[SSE] Failed to continue execution - HTTP error', {
          status: response.status,
          statusText: response.statusText,
          errorDetail: errorData.detail,
          execution_id: executionId,
          goal: goal?.substring(0, 100),
          maxTurns,
          backendUrl
        });
        throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      console.log('[SSE] Execution continued successfully', {
        execution_id: result.execution_id,
        goal: goal?.substring(0, 100),
        maxTurns,
        goal_refined: result.goal_refined,
        turns_extended: result.turns_extended
      });
      return result;

    } catch (error) {
      console.error('[SSE] Failed to continue execution - exception', {
        error: error.message,
        errorType: error.name,
        stack: error.stack,
        execution_id: executionId,
        goal: goal?.substring(0, 100),
        maxTurns,
        backendUrl
      });
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
        console.error('[SSE] Failed to reset execution - HTTP error', {
          status: response.status,
          statusText: response.statusText,
          errorDetail: errorData.detail,
          previous_execution_id: executionId,
          goal: goal?.substring(0, 100),
          maxTurns,
          backendUrl
        });
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

      console.log('[SSE] Execution reset successfully', {
        previous_execution_id: result.previous_execution_id,
        new_execution_id: result.execution_id,
        goal: goal?.substring(0, 100),
        maxTurns
      });
      return result;

    } catch (error) {
      console.error('[SSE] Failed to reset execution - exception', {
        error: error.message,
        errorType: error.name,
        stack: error.stack,
        previous_execution_id: executionId,
        goal: goal?.substring(0, 100),
        maxTurns,
        backendUrl
      });
      setIsExecuting(false);
      throw error;
    }
  }, [executionId, backendUrl]);

  // Extend turns with optional goal refinement
  const extendTurns = useCallback(async (additionalTurns, goalRefinement = null) => {
    if (!executionId) {
      throw new Error('No execution to extend');
    }

    try {
      setIsExecuting(true);

      const requestBody = {
        additional_turns: additionalTurns
      };

      // Include goal if provided (allows combining turn extension with goal refinement)
      if (goalRefinement && goalRefinement.trim()) {
        requestBody.goal = goalRefinement.trim();
      }

      const response = await fetch(`${backendUrl}/api/v1/executions/${executionId}/continue`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        console.error('[SSE] Failed to extend execution - HTTP error', {
          status: response.status,
          statusText: response.statusText,
          errorDetail: errorData.detail,
          execution_id: executionId,
          additionalTurns,
          goalRefinement: goalRefinement?.substring(0, 100),
          backendUrl
        });
        throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      console.log('[SSE] Execution extended successfully', {
        execution_id: result.execution_id,
        additionalTurns,
        goal_refined: result.goal_refined,
        turns_extended: result.turns_extended,
        maxTurns: result.max_turns
      });
      return result;

    } catch (error) {
      console.error('[SSE] Failed to extend execution - exception', {
        error: error.message,
        errorType: error.name,
        stack: error.stack,
        execution_id: executionId,
        additionalTurns,
        goalRefinement: goalRefinement?.substring(0, 100),
        backendUrl
      });
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
    extendTurns,
    events,
    isConnected,
    isExecuting,
    executionId
  };
}
