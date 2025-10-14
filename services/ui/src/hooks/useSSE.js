import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * Hook for Server-Sent Events streaming
 */
export function useSSE(backendUrl) {
  // Persist execution ID in localStorage for reconnection after refresh
  const [executionId, setExecutionId] = useState(() => {
    return localStorage.getItem('oats_execution_id') || null;
  });

  const [events, setEvents] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isExecuting, setIsExecuting] = useState(() => {
    return localStorage.getItem('oats_is_executing') === 'true';
  });

  const eventSourceRef = useRef(null);
  const processedEventIds = useRef(new Set());
  const lastEventIdRef = useRef(0);

  // Persist execution state to localStorage
  useEffect(() => {
    if (executionId) {
      localStorage.setItem('oats_execution_id', executionId);
    } else {
      localStorage.removeItem('oats_execution_id');
    }
  }, [executionId]);

  useEffect(() => {
    localStorage.setItem('oats_is_executing', isExecuting.toString());
  }, [isExecuting]);

  // Start a new execution
  const startExecution = useCallback(async (goal, maxTurns = 15) => {
    try {
      setIsExecuting(true);
      setEvents([]);
      processedEventIds.current.clear();
      lastEventIdRef.current = 0;

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

  // Reconnect to an existing execution
  const reconnectToExecution = useCallback(async (execId) => {
    try {
      // Check if execution exists and is still running
      const response = await fetch(`${backendUrl}/api/v1/executions/${execId}/status`);

      if (!response.ok) {
        throw new Error(`Execution not found: ${execId}`);
      }

      const status = await response.json();

      // Set execution ID and state based on backend status
      setExecutionId(execId);
      setIsExecuting(status.status === 'running');

      console.log(`Reconnected to execution ${execId} with status: ${status.status}`);
      return status;

    } catch (error) {
      console.error('Failed to reconnect to execution:', error);
      // Clear stale execution ID
      setExecutionId(null);
      setIsExecuting(false);
      throw error;
    }
  }, [backendUrl]);

  // Listen for events when execution ID changes
  useEffect(() => {
    if (!executionId) return;

    // Use last_event_id for reconnection support
    const eventSource = new EventSource(
      `${backendUrl}/api/v1/executions/${executionId}/events?last_event_id=${lastEventIdRef.current}`
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
      'execution_aborted',
      'execution_stopped',
      'user_interrupt',
      'interrupt_received',
      'feedback_injected',
      'llm_requests_input',
      'llm_requests_approval'
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

          // Deduplicate events and track last event ID
          if (!processedEventIds.current.has(event.id)) {
            processedEventIds.current.add(event.id);
            setEvents(prev => [...prev, event]);

            // Update last event ID for reconnection
            const eventId = parseInt(event.id, 10);
            if (!isNaN(eventId) && eventId > lastEventIdRef.current) {
              lastEventIdRef.current = eventId;
            }

            // Check if execution is complete
            if (eventType === 'execution_completed' || eventType === 'execution_failed' || eventType === 'execution_aborted' || eventType === 'execution_stopped') {
              setIsExecuting(false);
              // Close connection after completion
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

  // Auto-reconnect on mount if there's a persisted execution ID
  useEffect(() => {
    const persistedId = localStorage.getItem('oats_execution_id');
    const wasExecuting = localStorage.getItem('oats_is_executing') === 'true';

    if (persistedId && wasExecuting) {
      console.log('Detected persisted execution, attempting to reconnect...');
      reconnectToExecution(persistedId).catch(err => {
        console.error('Auto-reconnect failed:', err);
      });
    }
  }, []); // Run only once on mount

  return {
    startExecution,
    stopExecution,
    submitFeedback,
    reconnectToExecution,
    events,
    isConnected,
    isExecuting,
    executionId
  };
}
