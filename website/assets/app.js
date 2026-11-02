const CHAT_STORAGE_KEY = "ardvark.chat.v1";
const MAX_CHAT_MESSAGES = 32;

const elements = {
  chatTab: document.querySelector("#chat-tab"),
  imageTab: document.querySelector("#image-tab"),
  chatView: document.querySelector("#chat-view"),
  imageView: document.querySelector("#image-view"),
  pageTitle: document.querySelector("#page-title"),
  connection: document.querySelector("#connection"),
  connectionLabel: document.querySelector("#connection-label"),
  welcome: document.querySelector("#welcome"),
  messages: document.querySelector("#messages"),
  chatForm: document.querySelector("#chat-form"),
  prompt: document.querySelector("#prompt"),
  send: document.querySelector("#send"),
  chatNotice: document.querySelector("#chat-notice"),
  newChat: document.querySelector("#new-chat"),
  imageForm: document.querySelector("#image-form"),
  imagePrompt: document.querySelector("#image-prompt"),
  imageSteps: document.querySelector("#image-steps"),
  imageSeed: document.querySelector("#image-seed"),
  generateImage: document.querySelector("#generate-image"),
  imageNotice: document.querySelector("#image-notice"),
  imageResult: document.querySelector("#image-result"),
  modelStatus: document.querySelector("#model-status"),
  modelStatusLabel: document.querySelector("#model-status-label"),
};

let messages = loadMessages();
let busy = false;
let imageBusy = false;

function loadMessages() {
  try {
    const saved = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) || "[]");
    if (
      Array.isArray(saved) &&
      saved.length <= MAX_CHAT_MESSAGES &&
      saved.every(
        (message, index) =>
          message &&
          message.role === (index % 2 === 0 ? "user" : "assistant") &&
          typeof message.content === "string",
      )
    ) {
      return saved;
    }
  } catch {
    localStorage.removeItem(CHAT_STORAGE_KEY);
  }
  return [];
}

function saveMessages() {
  try {
    localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(messages));
  } catch {
    showNotice(elements.chatNotice, "This conversation could not be saved in this browser.");
  }
}

function showNotice(element, message) {
  element.textContent = message;
  element.hidden = false;
}

function clearNotice(element) {
  element.textContent = "";
  element.hidden = true;
}

function setConnection(state, label) {
  elements.connection.dataset.state = state;
  elements.connectionLabel.textContent = label;
}

async function responseError(response) {
  let detail = `Request failed (${response.status}).`;
  try {
    const payload = await response.json();
    if (typeof payload.detail === "string") detail = payload.detail;
    else if (typeof payload.error === "string") detail = payload.error;
  } catch {
    // Keep the useful HTTP status when the server does not return JSON.
  }
  return detail;
}

function renderMessages() {
  elements.messages.replaceChildren();
  elements.welcome.hidden = messages.length > 0;
  for (const message of messages) {
    elements.messages.append(createMessage(message.role, message.content));
  }
  elements.conversation.scrollTop = elements.conversation.scrollHeight;
}

function createMessage(role, content, options = {}) {
  const article = document.createElement("article");
  article.className = `message ${role}${options.error ? " error" : ""}`;
  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = role === "assistant" ? "a" : "Y";
  const body = document.createElement("div");
  body.className = "message-body";
  const label = document.createElement("div");
  label.className = "message-label";
  label.textContent = role === "assistant" ? "Ardvark" : "You";
  const text = document.createElement("div");
  text.className = `message-text${options.pending ? " pending" : ""}`;
  text.textContent = content;
  body.append(label, text);
  article.append(avatar, body);
  return article;
}

function setBusy(value) {
  busy = value;
  elements.send.disabled = value;
  elements.prompt.disabled = value;
  elements.send.setAttribute("aria-label", value ? "Ardvark is responding" : "Send message");
}

async function sendMessage(text) {
  const content = text.trim();
  if (!content || busy) return;
  clearNotice(elements.chatNotice);
  setBusy(true);
  messages.push({ role: "user", content });
  const pending = createMessage("assistant", "Thinking…", { pending: true });
  renderMessages();
  elements.messages.append(pending);

  const requestMessages = messages.slice(-MAX_CHAT_MESSAGES);
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: requestMessages }),
    });
    if (!response.ok) throw new Error(await responseError(response));
    const payload = await response.json();
    if (typeof payload.reply !== "string" || !payload.reply.trim()) {
      throw new Error("Ardvark returned an empty response. Please try again.");
    }
    messages.push({ role: "assistant", content: payload.reply });
    messages = messages.slice(-MAX_CHAT_MESSAGES);
    saveMessages();
    setConnection("online", "Ardvark is ready");
  } catch (error) {
    messages.pop();
    const reason = error instanceof TypeError
      ? "Could not reach Ardvark. Check that the application server is running."
      : error.message;
    showNotice(elements.chatNotice, reason || "Something went wrong. Please try again.");
    setConnection("offline", "Ardvark is unavailable");
  } finally {
    setBusy(false);
    renderMessages();
    elements.prompt.focus();
  }
}

function switchView(view) {
  const showingChat = view === "chat";
  elements.chatView.hidden = !showingChat;
  elements.imageView.hidden = showingChat;
  elements.chatTab.classList.toggle("is-active", showingChat);
  elements.imageTab.classList.toggle("is-active", !showingChat);
  elements.chatTab.toggleAttribute("aria-current", showingChat);
  elements.imageTab.toggleAttribute("aria-current", !showingChat);
  elements.pageTitle.textContent = showingChat ? "Chat" : "Image studio";
  if (!showingChat) void checkImageStatus();
  else elements.prompt.focus();
}

async function checkImageStatus() {
  elements.modelStatus.dataset.state = "checking";
  elements.modelStatusLabel.textContent = "Checking local image model…";
  try {
    const response = await fetch("/api/images/status");
    if (!response.ok) throw new Error(await responseError(response));
    const status = await response.json();
    const ready = status.status === "ready";
    elements.modelStatus.dataset.state = ready ? "ready" : "checking";
    elements.modelStatusLabel.textContent = ready
      ? `SD-Turbo ready · ${status.device}`
      : `SD-Turbo · ${status.status === "not_loaded" ? "loads on first generation" : status.status}`;
  } catch {
    elements.modelStatus.dataset.state = "error";
    elements.modelStatusLabel.textContent = "Local image service is unavailable";
  }
}

async function generateImage(event) {
  event.preventDefault();
  if (imageBusy) return;
  clearNotice(elements.imageNotice);
  elements.imageResult.replaceChildren();
  const prompt = elements.imagePrompt.value.trim();
  if (!prompt) {
    showNotice(elements.imageNotice, "Describe the image you want to create.");
    elements.imagePrompt.focus();
    return;
  }

  const rawSeed = elements.imageSeed.value.trim();
  const seed = rawSeed === "" ? null : Number(rawSeed);
  if (seed !== null && (!Number.isInteger(seed) || seed < 0 || seed > 4294967295)) {
    showNotice(elements.imageNotice, "Seed must be a whole number between 0 and 4294967295.");
    elements.imageSeed.focus();
    return;
  }

  imageBusy = true;
  elements.generateImage.disabled = true;
  elements.generateImage.querySelector("span").textContent = "Generating…";
  elements.modelStatus.dataset.state = "loading";
  elements.modelStatusLabel.textContent = "Loading SD-Turbo and creating your image…";
  try {
    const response = await fetch("/api/images/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        steps: Number(elements.imageSteps.value),
        seed,
      }),
    });
    if (!response.ok) throw new Error(await responseError(response));
    const result = await response.json();
    if (typeof result.image_url !== "string" || !result.image_url.startsWith("/api/images/")) {
      throw new Error("The image service returned an invalid image URL.");
    }

    const link = document.createElement("a");
    link.href = result.image_url;
    link.target = "_blank";
    link.rel = "noopener";
    link.setAttribute("aria-label", "Open generated image");
    const image = document.createElement("img");
    image.className = "generated-image";
    image.src = result.image_url;
    image.alt = result.prompt || prompt;
    image.loading = "lazy";
    link.append(image);
    elements.imageResult.append(link);
    elements.modelStatus.dataset.state = "ready";
    elements.modelStatusLabel.textContent = `SD-Turbo ready · ${result.model}`;
  } catch (error) {
    const reason = error instanceof TypeError
      ? "Could not reach the local image service. Check that the application server is running."
      : error.message;
    showNotice(elements.imageNotice, reason || "Image generation failed. Please try again.");
    elements.modelStatus.dataset.state = "error";
    elements.modelStatusLabel.textContent = "Image generation needs attention";
  } finally {
    imageBusy = false;
    elements.generateImage.disabled = false;
    elements.generateImage.querySelector("span").textContent = "Generate image";
  }
}

elements.chatTab.addEventListener("click", () => switchView("chat"));
elements.imageTab.addEventListener("click", () => switchView("image"));
elements.newChat.addEventListener("click", () => {
  messages = [];
  saveMessages();
  clearNotice(elements.chatNotice);
  renderMessages();
  switchView("chat");
});
elements.chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const content = elements.prompt.value;
  if (!content.trim() || busy) return;
  elements.prompt.value = "";
  elements.prompt.style.height = "auto";
  void sendMessage(content);
});
elements.prompt.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    elements.chatForm.requestSubmit();
  }
});
elements.prompt.addEventListener("input", () => {
  elements.prompt.style.height = "auto";
  elements.prompt.style.height = `${Math.min(elements.prompt.scrollHeight, 180)}px`;
});
document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    elements.prompt.value = button.dataset.prompt || "";
    switchView("chat");
    elements.prompt.focus();
    elements.prompt.style.height = "auto";
    elements.prompt.style.height = `${Math.min(elements.prompt.scrollHeight, 180)}px`;
  });
});
elements.imageForm.addEventListener("submit", generateImage);
elements.imagePrompt.addEventListener("input", () => clearNotice(elements.imageNotice));
document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    messages = [];
    saveMessages();
    clearNotice(elements.chatNotice);
    renderMessages();
    switchView("chat");
    elements.prompt.focus();
  }
});

renderMessages();
fetch("/api/health")
  .then((response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    setConnection("online", "Ardvark is ready");
  })
  .catch(() => setConnection("offline", "Ardvark is unavailable"));
