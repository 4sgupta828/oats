import { useState, useEffect, useCallback } from 'react';

/**
 * Hook for managing agent execution with event-driven architecture
 */
export function useAgentExecution(executionId) {
  const [events, setEvents] = useState([]);
  const [status, setStatus] = useState('running');
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const [lastEventId, setLastEventId] = useState(0);
  
  const backendUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';

  // Reset state when execution ID changes
  useEffect(() => {
    if (executionId) {
      setEvents([]);
      setStatus('running');
      setLastEventId(0);
      setError(null);
    }
  }, [executionId]);

  // Event stream connection
  useEffect(() => {
    if (!executionId) return;

    let eventSource = null;
    let reconnectTimeout = null;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;
    const reconnectDelay = 2000;

    const connect = () => {
      if (eventSource) {
        eventSource.close();
      }
      
      const url = `${backendUrl}/executions/${executionId}/events?last_event_id=${lastEventId}`;
      console.log('Connecting to SSE:', url);
      
      eventSource = new EventSource(url);
      
      eventSource.onopen = () => {
        console.log('SSE connection opened');
        setIsConnected(true);
        setError(null);
        reconnectAttempts = 0;
      };
      
      eventSource.onmessage = (e) => {
        try {
          const event = JSON.parse(e.data);
          console.log('Received SSE event:', event);
          
          setEvents(prev => [...prev, event]);
          setLastEventId(parseInt(e.lastEventId || '0'));
          
          // Update status based on event type
          if (event.event === 'execution_completed') {
            setStatus('completed');
          } else if (event.event === 'execution_failed') {
            setStatus('failed');
          } else if (event.event === 'llm_requests_input' || event.event === 'llm_requests_approval') {
            setStatus('paused');
          } else if (event.event === 'user_interrupt') {
            setStatus('paused');
          }
          
        } catch (err) {
          console.error('Failed to parse SSE event:', err);
          setError(`Failed to parse event: ${err.message}`);
        }
      };
      
      eventSource.onerror = (e) => {
        console.error('SSE connection error:', e);
        setIsConnected(false);
        eventSource?.close();
        
        // Attempt reconnection
        if (reconnectAttempts < maxReconnectAttempts) {
          reconnectAttempts++;
          console.log(`Reconnection attempt ${reconnectAttempts}/${maxReconnectAttempts}`);
          reconnectTimeout = setTimeout(connect, reconnectDelay * reconnectAttempts);
        } else {
          setError('Failed to reconnect after multiple attempts');
        }
      };
    };

    connect();

    return () => {
      if (eventSource) eventSource.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, [executionId, lastEventId, backendUrl]);

  const submitFeedback = useCallback(async (turnNumber, type, data) => {
    if (!executionId) {
      throw new Error('No active execution');
    }

    try {
      const response = await fetch(`${backendUrl}/executions/${executionId}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          turn_number: turnNumber, 
          feedback_type: type, 
          data 
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      console.log('Feedback submitted:', result);
      return result;
      
    } catch (err) {
      console.error('Failed to submit feedback:', err);
      setError(`Failed to submit feedback: ${err.message}`);
      throw err;
    }
  }, [executionId, backendUrl]);

  return { 
    events, 
    status, 
    isConnected, 
    error, 
    submitFeedback 
  };
}
