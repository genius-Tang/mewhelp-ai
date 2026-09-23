const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const messageList = document.querySelector("#message-list");
const suggestions = document.querySelector("#suggestions");
const resetButton = document.querySelector("#reset-chat");

const conversation = [];
let isStreaming = false;

function nowLabel() {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date());
}

function scrollToLatest() {
  messageList.scrollTop = messageList.scrollHeight;
}

function appendPlainText(target, text) {
  const lines = text.split("\n");
  lines.forEach((line, index) => {
    if (index > 0) target.append(document.createElement("br"));
    target.append(document.createTextNode(line));
  });
}

function renderAssistantText(target, text) {
  target.replaceChildren();
  const segments = text.split(/(\*\*[\s\S]+?\*\*)/g);

  for (const segment of segments) {
    if (!segment) continue;
    if (segment.startsWith("**") && segment.endsWith("**")) {
      const strong = document.createElement("strong");
      appendPlainText(strong, segment.slice(2, -2));
      target.append(strong);
    } else {
      appendPlainText(target, segment);
    }
  }
}

function createMessage(role, content = "") {
  const article = document.createElement("article");
  article.className = `message ${role}-message`;

  if (role === "assistant") {
    const avatar = document.createElement("div");
    avatar.className = "avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = "M";
    article.append(avatar);
  }

  const stack = document.createElement("div");
  stack.className = "message-stack";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = content;

  const time = document.createElement("time");
  time.textContent = role === "assistant" ? `智能客服 · ${nowLabel()}` : nowLabel();

  stack.append(bubble, time);
  article.append(stack);
  messageList.append(article);
  scrollToLatest();
  return bubble;
}

function setBusy(busy) {
  isStreaming = busy;
  input.disabled = busy;
  sendButton.disabled = busy;
  suggestions.querySelectorAll("button").forEach((button) => {
    button.disabled = busy;
  });
  sendButton.querySelector("span").textContent = busy ? "回复中" : "发送";
}

function resizeInput() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
}

function parseSseBlock(block) {
  let eventName = "message";
  const dataLines = [];

  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (!dataLines.length) {
    return null;
  }

  return { eventName, data: JSON.parse(dataLines.join("\n")) };
}

async function streamReply(messages, bubble) {
  const response = await fetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages }),
  });

  if (!response.ok) {
    let detail = "请求失败，请稍后重试";
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      // Keep the safe fallback message for non-JSON responses.
    }
    throw new Error(detail);
  }

  if (!response.body) {
    throw new Error("浏览器无法读取流式响应");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let assistantText = "";
  let completed = false;

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    buffer = buffer.replaceAll("\r\n", "\n");

    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";

    for (const block of blocks) {
      const parsed = parseSseBlock(block);
      if (!parsed) continue;

      if (parsed.eventName === "token") {
        assistantText += parsed.data.content || "";
        renderAssistantText(bubble, assistantText);
        scrollToLatest();
      } else if (parsed.eventName === "done") {
        completed = true;
      } else if (parsed.eventName === "error") {
        throw new Error(parsed.data.message || "模型服务暂时不可用");
      }
    }

    if (done) break;
  }

  if (!completed || !assistantText.trim()) {
    throw new Error("回复意外中断，请重新发送");
  }

  return assistantText;
}

async function sendMessage() {
  const content = input.value.trim();
  if (!content || isStreaming) return;

  conversation.push({ role: "user", content });
  const requestMessages = conversation.map((message) => ({ ...message }));
  createMessage("user", content);

  input.value = "";
  resizeInput();
  suggestions.hidden = true;
  setBusy(true);

  const assistantBubble = createMessage("assistant");
  assistantBubble.classList.add("typing");

  try {
    const assistantText = await streamReply(requestMessages, assistantBubble);
    conversation.push({ role: "assistant", content: assistantText });
  } catch (error) {
    assistantBubble.classList.add("error-bubble");
    assistantBubble.textContent = error instanceof Error ? error.message : "请求失败，请稍后重试";
  } finally {
    assistantBubble.classList.remove("typing");
    setBusy(false);
    input.focus();
    scrollToLatest();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  void sendMessage();
});

input.addEventListener("input", resizeInput);
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    void sendMessage();
  }
});

suggestions.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-prompt]");
  if (!button) return;
  input.value = button.dataset.prompt || "";
  resizeInput();
  input.focus();
});

resetButton.addEventListener("click", () => {
  if (isStreaming) return;
  conversation.length = 0;
  messageList.querySelectorAll(".message:not(.welcome-message)").forEach((message) => message.remove());
  suggestions.hidden = false;
  input.value = "";
  resizeInput();
  input.focus();
});

input.focus();
