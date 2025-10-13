import { useState, useEffect, useCallback } from 'react';

/**
 * Generic hook for Server-Sent Events streaming
 */
export function useEventStream(url, options = {}) {
  const [events, setEvents] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const [lastEventId, setLastEventId] = useState(options.lastEventId || 0);
  
  const {
    onEvent = () => {},
    onOpen = () => {},
    onError = () => {},
    onClose = () => {},
    autoReconnect = true,
    maxReconnectAttempts = 5,
    reconnectDelay = 2000
  } = options;

  const connect = useCallback(() => {
    if (!url) return null;

    const eventSource = new EventSource(url);
    let reconnectTimeout = null;
    let reconnectAttempts = 0;

    eventSource.onopen = () => {
      console.log('SSE connection opened:', url);
      setIsConnected(true);
      setError(null);
      reconnectAttempts = 0;
      onOpen();
    };

    eventSource.onmessage = (e) => {
      try {
        const event = {
          id: e.lastEventId,
          event: e.type || 'message',
          data: e.data,
          timestamp: new Date().toISOString()
        };
        
        setEvents(prev => [...prev, event]);
        setLastEventId(parseInt(e.lastEventId || '0'));
        onEvent(event);
        
      } catch (err) {
        console.error('Failed to process SSE event:', err);
        setError(`Failed to process event: ${err.message}`);
      }
    };

    eventSource.onerror = (e) => {
      console.error('SSE connection error:', e);
      setIsConnected(false);
      onError(e);
      
      if (autoReconnect && reconnectAttempts < maxReconnectAttempts) {
        reconnectAttempts++;
        console.log(`Reconnection attempt ${reconnectAttempts}/${maxReconnectAttempts}`);
        reconnectTimeout = setTimeout(() => {
          eventSource.close();
          connect();
        }, reconnectDelay * reconnectAttempts);
      } else {
        setError('Failed to reconnect after multiple attempts');
        eventSource.close();
      }
    };

    eventSource.addEventListener('close', () => {
      console.log('SSE connection closed');
      setIsConnected(false);
      onClose();
    });

    return eventSource;
  }, [url, onEvent, onOpen, onError, onClose, autoReconnect, maxReconnectAttempts, reconnectDelay]);

  useEffect(() => {
    const eventSource = connect();
    
    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [connect]);

  const clearEvents = useCallback(() => {
    setEvents([]);
    setLastEventId(0);
  }, []);

  const close = useCallback(() => {
    setIsConnected(false);
    setError(null);
  }, []);

  return {
    events,
    isConnected,
    error,
    lastEventId,
    clearEvents,
    close
  };
}
