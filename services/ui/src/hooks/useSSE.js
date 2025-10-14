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
      'user_interrupt',
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

          // Deduplicate events
          if (!processedEventIds.current.has(event.id)) {
            processedEventIds.current.add(event.id);
            setEvents(prev => [...prev, event]);

            // Check if execution is complete
            if (eventType === 'execution_completed' || eventType === 'execution_failed') {
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

  const stopExecution = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      setIsConnected(false);
      setIsExecuting(false);
    }
  }, []);

  return {
    startExecution,
    stopExecution,
    events,
    isConnected,
    isExecuting,
    executionId
  };
}
