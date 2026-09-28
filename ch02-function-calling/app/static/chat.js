const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const messageList = document.querySelector("#message-list");
const suggestions = document.querySelector("#suggestions");
const resetButtons = document.querySelectorAll("#reset-chat, #reset-chat-mobile");

const userIdKey = "mewhelp_user_id";
const conversationIdKey = "mewhelp_conversation_id";
let userId = localStorage.getItem(userIdKey);
if (!userId) {
  userId = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `user-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  localStorage.setItem(userIdKey, userId);
}
let isStreaming = false;
let activeController = null;
let requestGeneration = 0;

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

async function streamReply(message, bubble, signal) {
  const storedId = Number(localStorage.getItem(conversationIdKey));
  const conversationId = Number.isSafeInteger(storedId) && storedId > 0 ? storedId : null;
  const response = await fetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, message, conversation_id: conversationId }),
    signal,
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
  let doneConversationId = null;
  const answer = document.createElement("span");
  answer.className = "answer-text";
  bubble.append(answer);

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    buffer = buffer.replaceAll("\r\n", "\n");

    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";

    for (const block of blocks) {
      const parsed = parseSseBlock(block);
      if (!parsed) continue;

      if (parsed.eventName === "tool") {
        const name = parsed.data.name;
        if (typeof name === "string" && name.trim()) {
          let badge = bubble.querySelector(".tool-badge");
          if (!badge) {
            badge = document.createElement("span");
            badge.className = "tool-badge";
            bubble.prepend(badge);
          }
          badge.textContent = `调用了 ${name}`;
        }
        scrollToLatest();
      } else if (parsed.eventName === "token") {
        const token = parsed.data.content;
        if (typeof token === "string" && token) {
          assistantText += token;
          renderAssistantText(answer, assistantText);
          bubble.classList.remove("typing");
        }
        scrollToLatest();
      } else if (parsed.eventName === "done") {
        const id = parsed.data.conversation_id;
        if (Number.isSafeInteger(id) && id > 0) {
          doneConversationId = id;
          completed = true;
        }
      } else if (parsed.eventName === "error") {
        throw new Error(parsed.data.message || "模型服务暂时不可用");
      }
    }

    if (done) break;
  }

  if (!completed || !assistantText.trim()) {
    throw new Error("回复意外中断，请重新发送");
  }

  if (signal.aborted) return;
  localStorage.setItem(conversationIdKey, String(doneConversationId));
}

async function sendMessage() {
  const content = input.value.trim();
  if (!content || isStreaming) return;

  createMessage("user", content);

  input.value = "";
  resizeInput();
  suggestions.hidden = true;
  setBusy(true);
  const generation = ++requestGeneration;
  const controller = new AbortController();
  activeController = controller;

  const assistantBubble = createMessage("assistant");
  assistantBubble.classList.add("typing");

  try {
    await streamReply(content, assistantBubble, controller.signal);
  } catch (error) {
    if (!controller.signal.aborted) {
      assistantBubble.classList.add("error-bubble");
      const answer = assistantBubble.querySelector(".answer-text") || assistantBubble;
      answer.textContent = error instanceof Error ? error.message : "请求失败，请稍后重试";
    }
  } finally {
    assistantBubble.classList.remove("typing");
    if (generation === requestGeneration) {
      activeController = null;
      setBusy(false);
      input.focus();
      scrollToLatest();
    }
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  void sendMessage();
});

sendButton.addEventListener("click", (event) => {
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

suggestions.querySelectorAll("button[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    input.value = button.dataset.prompt || "";
    resizeInput();
    void sendMessage();
  });
});

function resetConversation() {
  requestGeneration += 1;
  activeController?.abort();
  activeController = null;
  setBusy(false);
  localStorage.removeItem(conversationIdKey);
  messageList.querySelectorAll(".message:not(.welcome-message)").forEach((message) => message.remove());
  suggestions.hidden = false;
  input.value = "";
  resizeInput();
  input.focus();
}

resetButtons.forEach((button) => button.addEventListener("click", resetConversation));

input.focus();
