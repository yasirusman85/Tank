/**
 * TankClient — Official JavaScript & Browser Client SDK for Tank Web Framework.
 * Supports SSE streaming, WebSockets, and Human-in-the-Loop tool approval workflows.
 */
class TankClient {
  /**
   * @param {Object} options
   * @param {string} options.baseUrl Base URL of the Tank server (e.g. 'http://localhost:8000')
   * @param {string} [options.apiKey] Optional API Key for authentication
   */
  constructor(options = {}) {
    this.baseUrl = options.baseUrl || 'http://localhost:8000';
    this.apiKey = options.apiKey || null;
    this.listeners = {};
  }

  /**
   * Register event callbacks.
   * Event types: 'thought', 'token', 'tool_call', 'tool_response', 'approval_required', 'done', 'error'
   */
  on(event, callback) {
    if (!this.listeners[event]) {
      this.listeners[event] = [];
    }
    this.listeners[event].push(callback);
    return this;
  }

  emit(event, data) {
    if (this.listeners[event]) {
      this.listeners[event].forEach(cb => cb(data));
    }
  }

  /**
   * Stream agent execution via Server-Sent Events (SSE).
   * @param {string} endpoint Agent path (e.g. '/chat')
   * @param {string} prompt User query
   * @param {string} [sessionId='default'] Session ID
   */
  async stream(endpoint, prompt, sessionId = 'default') {
    const url = new URL(endpoint, this.baseUrl);
    url.searchParams.set('prompt', prompt);
    url.searchParams.set('session_id', sessionId);

    const headers = {};
    if (this.apiKey) {
      headers['X-API-Key'] = this.apiKey;
    }

    try {
      const response = await fetch(url.toString(), { method: 'POST', headers });
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop();

        for (const block of lines) {
          if (!block.trim()) continue;
          const eventMatch = block.match(/event:\s*(.+)/);
          const dataMatch = block.match(/data:\s*(.+)/);

          if (eventMatch && dataMatch) {
            const eventName = eventMatch[1].trim();
            const eventData = JSON.parse(dataMatch[1].trim());
            this.emit(eventName, eventData);
          }
        }
      }
    } catch (err) {
      this.emit('error', err);
    }
  }

  /**
   * Connect via bidirectional WebSocket.
   * @param {string} endpoint WebSocket path (e.g. '/ws-chat')
   */
  connectWebSocket(endpoint) {
    const wsUrl = this.baseUrl.replace(/^http/, 'ws') + endpoint;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.event && payload.data) {
          this.emit(payload.event, payload.data);
        }
      } catch (e) {
        // ignore raw text
      }
    };

    ws.onerror = (err) => this.emit('error', err);
    return ws;
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { TankClient };
}
