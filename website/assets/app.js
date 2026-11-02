const history = [];
const elements = {
  chatTab: document.querySelector("#chat-tab"),
  imageTab: document.querySelector("#image-tab"),
  chatView: document.querySelector("#chat-view"),
  imageView: document.querySelector("#image-view"),
  pageTitle: document.querySelector("#page-title"),
  connectionIndicator: document.querySelector("#connection-indicator"),
  connectionLabel: document.querySelector("#connection-label"),
  welcome: document.querySelector("#welcome"),
  messages: document.querySelector("#messages"),
  chatForm: document.querySelector("#chat-form"),
  prompt: document.querySelector("#prompt"),
  chatStatus: document.querySelector("#chat-status"),
  send: document.querySelector("#send"),
  newChat: document.querySelector("#new-chat"),
  imageForm: document.querySelector("#image-form"),
  imagePrompt: document.querySelector("#image-prompt"),
  imageSteps: document.querySelector("#image-steps"),
  imageSeed: document.querySelector("#image-seed"),
  imageStatus: document.querySelector("#image-status"),
  imageResult: document.querySelector("#image-result"),
  generateImage: document.querySelector("#generate-image"),
};

function setStatus(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("is-error", isError);
}

function showView(view) {
  const isChat = view === "chat";
  elements.chatView.hidden = !isChat;
  elements.imageView.hidden = isChat;
  elements.chatTab.classList.toggle("is-active", isChat);
  elements.imageTab.classList.toggle("is-active", !isChat);
  if (isChat) {
    elements.chatTab.setAttribute("aria-current", "page");
    elements.imageTab.removeAttribute("aria-current");
  } else {
    elements.imageTab.setAttribute("aria-current", "page");
    elements.chatTab.removeAttribute("aria-current");
  }
  elements.pageTitle.textContent = isChat ? "Chat" : "Image studio";
  if (isChat) elements.prompt.focus();
  else elements.imagePrompt.focus();
}

function resizeComposer() {
  elements.prompt.style.height = "auto";
  elements.prompt.style.height = `${Math.min(elements.prompt.scrollHeight, 180)}px`;
}

function appendMessage(role, content) {
  const row = document.createElement("article");
  row.className = `message ${role}`;

  const avatar = document.createElement("span");
  avatar.className = "message-avatar";
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = role === "assistant" ? "a" : "Y";

  const bubble = document.createElement("div");
  bubble.className = "message-content";
  bubble.textContent = content;
  row.append(avatar, bubble);
  elements.messages.append(row);
  row.scrollIntoView({
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
    block: "end",
  });
  return row;
}

async function checkConnection() {
  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error("Health check failed");
    elements.connectionIndicator.classList.add("is-online");
    elements.connectionLabel.textContent = "App connected";
  } catch {
    elements.connectionIndicator.classList.add("is-offline");
    elements.connectionLabel.textContent = "App unavailable";
  }
}

elements.chatTab.addEventListener("click", () => showView("chat"));
elements.imageTab.addEventListener("click", () => showView("images"));

elements.newChat.addEventListener("click", () => {
  if (elements.send.disabled) return;
  history.length = 0;
  elements.messages.replaceChildren();
  elements.welcome.hidden = false;
  elements.newChat.hidden = true;
  elements.prompt.value = "";
  resizeComposer();
  setStatus(elements.chatStatus, "");
  elements.prompt.focus();
});

document.querySelectorAll(".suggestion").forEach((button) => {
  button.addEventListener("click", () => {
    elements.prompt.value = button.dataset.prompt ?? "";
    resizeComposer();
    elements.prompt.focus();
  });
});

elements.prompt.addEventListener("input", resizeComposer);
elements.prompt.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    elements.chatForm.requestSubmit();
  }
});

document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    showView("chat");
    elements.prompt.focus();
  }
});

elements.chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const content = elements.prompt.value.trim();
  if (!content || elements.send.disabled) return;

  if (history.length >= 32) history.splice(0, 2);
  elements.welcome.hidden = true;
  const userMessage = appendMessage("user", content);
  history.push({ role: "user", content });
  elements.newChat.hidden = false;
  elements.newChat.disabled = true;
  elements.prompt.value = "";
  resizeComposer();
  elements.send.disabled = true;
  setStatus(elements.chatStatus, "Thinking…");

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "The request could not be completed.");
    if (typeof result.reply !== "string" || !result.reply.trim()) {
      throw new Error("The AI provider returned an empty response.");
    }
    history.push({ role: "assistant", content: result.reply });
    appendMessage("assistant", result.reply);
    setStatus(elements.chatStatus, "");
  } catch (error) {
    history.pop();
    userMessage.remove();
    elements.welcome.hidden = history.length > 0;
    elements.newChat.hidden = history.length === 0;
    elements.prompt.value = content;
    resizeComposer();
    setStatus(elements.chatStatus, error.message || "Could not reach the AI provider. Try again.", true);
  } finally {
    elements.send.disabled = false;
    elements.newChat.disabled = false;
    elements.prompt.focus();
  }
});

elements.imageForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const prompt = elements.imagePrompt.value.trim();
  if (!prompt || elements.generateImage.disabled) return;

  elements.generateImage.disabled = true;
  elements.generateImage.textContent = "Generating…";
  setStatus(elements.imageStatus, "Loading the local model and generating your image. First use may take a few minutes.");
  elements.imageResult.replaceChildren();

  try {
    const response = await fetch("/api/images/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        steps: Number(elements.imageSteps.value),
        seed: elements.imageSeed.value === "" ? null : Number(elements.imageSeed.value),
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Image generation failed.");

    const figure = document.createElement("figure");
    const image = document.createElement("img");
    image.src = result.image_url;
    image.alt = prompt;
    const download = document.createElement("a");
    download.className = "download-link";
    download.href = result.image_url;
    download.download = "ardvark-image.png";
    download.textContent = "Download image";
    figure.append(image);
    elements.imageResult.append(figure, download);
    setStatus(elements.imageStatus, `Generated locally with ${result.model}.`);
  } catch (error) {
    setStatus(elements.imageStatus, error.message || "Image generation failed. Try again.", true);
  } finally {
    elements.generateImage.disabled = false;
    elements.generateImage.innerHTML = '<span aria-hidden="true">✳</span> Generate image';
  }
});

void checkConnection();
