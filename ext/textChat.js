let chatSocket;


let currentHtml = "";
chrome.runtime.onMessage.addListener((message) => {
  if (message.command === "sendPageContent" && message.content) {
    console.log("Updating current HTML");
  }
  // if there is nanobrowser text in html exchange it with "blazejbro"
});

document.addEventListener('DOMContentLoaded', () => {
  const messageInput = document.getElementById('messageInput');
  const sendButton = document.getElementById('sendMessage');
  const conversation = document.getElementById('textConversation');
  const connectButton = document.getElementById('chatConnectButton');
  const disconnectButton = document.getElementById('chatDisconnectButton');

  function updateConnectionStatus(status, text) {
    document.getElementById('chatWsStatus').className = `status-dot ${status}`;
    document.getElementById('chatWsStatusText').textContent = text;

    // Update input controls
    messageInput.disabled = status !== 'connected';
    sendButton.disabled = status !== 'connected';
    connectButton.disabled = status === 'connected' || status === 'connecting';
    disconnectButton.disabled = status !== 'connected';
  }

  function connectChat() {
    updateConnectionStatus('connecting', 'Connecting...');

    chatSocket = new WebSocket('ws://localhost:8000/plugin/chat/ws');

    chatSocket.onopen = () => {
      console.log('Chat connection established');
      updateConnectionStatus('connected', 'Connected');
    };

    chatSocket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      appendMessage('Assistant', message.content);
    };

    chatSocket.onclose = () => {
      console.log('Chat connection closed');
      updateConnectionStatus('disconnected', 'Disconnected');
    };

    chatSocket.onerror = (error) => {
      console.error('WebSocket error:', error);
      updateConnectionStatus('error', 'Connection error');
    };
  }

  function disconnectChat() {
    if (chatSocket) {
      chatSocket.close();
    }
    updateConnectionStatus('disconnected', 'Disconnected');
  }

  function appendMessage(sender, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${sender.toLowerCase()}`;
    messageDiv.innerHTML = `
      <div class="message-sender">${sender}</div>
      <div class="message-content">${content}</div>
    `;
    conversation.appendChild(messageDiv);
    conversation.scrollTop = conversation.scrollHeight;
  }

  function sendMessage() {
    const content = messageInput.value.trim();
    if (!content) return;

    if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
      const message = {
        type: 'message',
        content: content
      };
      chatSocket.send(JSON.stringify(message));
      appendMessage('You', content);
      messageInput.value = '';
    }
  }

  // Event Listeners
  connectButton.addEventListener('click', connectChat);
  disconnectButton.addEventListener('click', disconnectChat);
  sendButton.addEventListener('click', sendMessage);

  messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Initialize UI state
  updateConnectionStatus('disconnected', 'Disconnected');
});
