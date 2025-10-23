"""Simple HTML frontend for manual testing."""

from fastapi.responses import HTMLResponse


class FrontendHandler:
    async def handle(self) -> HTMLResponse:
        html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>NaraninYeo Assistant</title>
    <style>
        :root {
            color-scheme: light dark;
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            font-family: "Inter", "Segoe UI", sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            background: linear-gradient(160deg, #f4f7fb, #dfe7ff);
            color: #1f2933;
        }

        .chat-wrapper {
            width: min(960px, 100% - 32px);
            height: min(720px, 90vh);
            background: rgba(255, 255, 255, 0.85);
            backdrop-filter: blur(8px);
            border-radius: 24px;
            box-shadow: 0 24px 48px rgba(15, 23, 42, 0.2);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            border: 1px solid rgba(148, 163, 184, 0.35);
        }

        .chat-header {
            padding: 20px 28px;
            background: linear-gradient(135deg, #1e3a8a, #2e82ff);
            color: #f9fbff;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .chat-header h1 {
            margin: 0;
            font-size: 1.5rem;
            font-weight: 600;
        }

        .header-meta {
            font-size: 0.85rem;
            opacity: 0.85;
        }

        .chat-body {
            flex: 1;
            padding: 24px;
            overflow-y: auto;
            background: rgba(15, 23, 42, 0.04);
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .message {
            max-width: 75%;
            padding: 14px 18px;
            border-radius: 18px;
            line-height: 1.5;
            font-size: 0.95rem;
            position: relative;
            word-break: break-word;
            box-shadow: 0 8px 18px rgba(15, 23, 42, 0.12);
        }

        .message.user {
            align-self: flex-end;
            background: #2563eb;
            color: #f8fafc;
            border-bottom-right-radius: 6px;
        }

        .message.bot {
            align-self: flex-start;
            background: #f1f5f9;
            color: #1f2937;
            border-bottom-left-radius: 6px;
        }

        .message-meta {
            font-size: 0.72rem;
            margin-top: 6px;
            opacity: 0.65;
        }

        .chat-input {
            padding: 16px 24px;
            background: rgba(15, 23, 42, 0.06);
            border-top: 1px solid rgba(148, 163, 184, 0.3);
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 12px;
            align-items: end;
        }

        .chat-input textarea {
            width: 100%;
            resize: none;
            min-height: 60px;
            max-height: 120px;
            border-radius: 16px;
            padding: 14px 16px;
            border: 1px solid rgba(148, 163, 184, 0.4);
            font-family: inherit;
            font-size: 1rem;
            background: rgba(255, 255, 255, 0.9);
            box-shadow: inset 0 2px 6px rgba(15, 23, 42, 0.08);
        }

        .chat-input textarea:focus {
            outline: 2px solid rgba(59, 130, 246, 0.4);
            border-color: rgba(59, 130, 246, 0.7);
            background: #fff;
        }

        .chat-input button {
            padding: 15px 22px;
            border-radius: 16px;
            border: none;
            font-size: 0.95rem;
            font-weight: 600;
            background: linear-gradient(130deg, #2563eb, #4f46e5);
            color: #f8fafc;
            cursor: pointer;
            box-shadow: 0 12px 20px rgba(37, 99, 235, 0.25);
            transition: transform 0.18s ease, box-shadow 0.18s ease;
        }

        .chat-input button:hover {
            transform: translateY(-1px);
            box-shadow: 0 18px 28px rgba(37, 99, 235, 0.35);
        }

        .chat-input button:disabled {
            cursor: not-allowed;
            background: rgba(148, 163, 184, 0.4);
            color: rgba(15, 23, 42, 0.55);
            box-shadow: none;
        }

        .system-message {
            align-self: center;
            background: rgba(59, 130, 246, 0.12);
            color: #1e40af;
            border-radius: 12px;
            padding: 10px 14px;
            font-size: 0.8rem;
            box-shadow: none;
        }

        .controls {
            display: flex;
            gap: 12px;
            margin-top: 12px;
        }

        .controls input {
            flex: 1;
            border-radius: 12px;
            border: 1px solid rgba(148, 163, 184, 0.5);
            padding: 10px 12px;
        }

        @media (max-width: 640px) {
            .chat-wrapper {
                height: 100vh;
                border-radius: 0;
                width: 100%;
            }

            .chat-header {
                flex-direction: column;
                align-items: flex-start;
                gap: 4px;
            }
        }
    </style>
</head>
<body>
    <div class="chat-wrapper">
        <header class="chat-header">
            <div>
                <h1>NaraninYeo Concierge</h1>
                <div class="header-meta">Interactive test client for the assistant API</div>
            </div>
            <div class="header-meta" id="status">Idle</div>
        </header>
        <main class="chat-body" id="transcript">
            <div class="system-message">Messages appear here as you chat with the assistant.</div>
        </main>
        <footer class="chat-input">
            <div>
                <div class="controls">
                    <input id="tenantId" placeholder="Tenant ID" value="demo-tenant" />
                    <input id="botId" placeholder="Bot ID" value="demo-bot" />
                    <input id="channelId" placeholder="Channel ID" value="demo-channel" />
                </div>
                <textarea id="messageInput" placeholder="Type your message and press Enter..."></textarea>
            </div>
            <div>
                <button id="sendButton">Send</button>
            </div>
        </footer>
    </div>
    <script>
        const transcript = document.getElementById('transcript');
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        const tenantInput = document.getElementById('tenantId');
        const botInput = document.getElementById('botId');
        const channelInput = document.getElementById('channelId');
        const statusLabel = document.getElementById('status');

        let lastMessageId = null;
        const history = [];

        function appendMessage(role, text, meta = '') {
            const wrapper = document.createElement('div');
            wrapper.className = `message ${role}`;
            wrapper.textContent = text;
            if (meta) {
                const detail = document.createElement('div');
                detail.className = 'message-meta';
                detail.textContent = meta;
                wrapper.appendChild(detail);
            }
            transcript.appendChild(wrapper);
            transcript.scrollTo({ top: transcript.scrollHeight, behavior: 'smooth' });
        }

        function appendSystem(text) {
            const badge = document.createElement('div');
            badge.className = 'system-message';
            badge.textContent = text;
            transcript.appendChild(badge);
            transcript.scrollTo({ top: transcript.scrollHeight, behavior: 'smooth' });
        }

        async function sendMessage() {
            const text = messageInput.value.trim();
            if (!text) {
                return;
            }

            const tenantId = tenantInput.value || 'demo-tenant';
            const botId = botInput.value || 'demo-bot';
            const channelId = channelInput.value || 'demo-channel';

            const payload = {
                tenant_id: tenantId,
                bot_id: botId,
                channel: { channel_id: channelId, channel_name: 'Demo Channel' },
                author: { author_id: 'user', display_name: 'You' },
                text,
            };

            messageInput.value = '';
            messageInput.disabled = true;
            sendButton.disabled = true;
            statusLabel.textContent = 'Sending…';
            appendMessage('user', text, new Date().toLocaleTimeString());

            try {
                const response = await fetch('/api/messages', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });

                if (!response.ok) {
                    throw new Error(`Server error: ${response.status}`);
                }

                const result = await response.json();
                lastMessageId = result?.message?.message_id ?? null;
                history.push({ role: 'user', text, timestamp: new Date() });

                if (result.message?.text) {
                    appendMessage('bot', result.message.text, new Date().toLocaleTimeString());
                    history.push({ role: 'bot', text: result.message.text, timestamp: new Date() });
                } else {
                    appendSystem('No reply generated. Try requesting a reply explicitly.');
                }
            } catch (error) {
                appendSystem(`Error: ${error.message}`);
            } finally {
                messageInput.disabled = false;
                sendButton.disabled = false;
                messageInput.focus();
                statusLabel.textContent = 'Idle';
            }
        }

        async function requestReply() {
            if (!lastMessageId) {
                appendSystem('No prior message to reply to. Send a message first.');
                return;
            }

            const tenantId = tenantInput.value || 'demo-tenant';
            const botId = botInput.value || 'demo-bot';
            const channelId = channelInput.value || 'demo-channel';

            const payload = {
                tenant_id: tenantId,
                bot_id: botId,
                channel_id: channelId,
                message_id: lastMessageId,
            };

            statusLabel.textContent = 'Requesting reply…';

            try {
                const response = await fetch('/api/replies', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });

                if (!response.ok) {
                    throw new Error(`Server error: ${response.status}`);
                }

                const result = await response.json();
                if (result.message?.text) {
                    appendMessage('bot', result.message.text, new Date().toLocaleTimeString());
                    history.push({ role: 'bot', text: result.message.text, timestamp: new Date() });
                } else {
                    appendSystem('Reply request successful but no message returned.');
                }
            } catch (error) {
                appendSystem(`Error: ${error.message}`);
            } finally {
                statusLabel.textContent = 'Idle';
            }
        }

        function handleInputKey(event) {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                sendMessage();
            }
        }

        messageInput.addEventListener('keydown', handleInputKey);
        sendButton.addEventListener('click', sendMessage);

        const replyShortcut = document.createElement('button');
        replyShortcut.textContent = 'Request Reply';
        replyShortcut.style.marginTop = '12px';
        replyShortcut.className = 'request-reply';
        replyShortcut.addEventListener('click', requestReply);
        document.querySelector('.chat-input > div').appendChild(replyShortcut);

        appendSystem('Welcome! Fill in tenant/bot info if needed and start chatting.');
    </script>
</body>
</html>

"""
        return HTMLResponse(content=html)
