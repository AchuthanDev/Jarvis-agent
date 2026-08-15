"use strict";

const state = {
  conversations: [],
  activeConversationId: null,
  streaming: false,
  view: "chat",
};

const $ = (id) => document.getElementById(id);
const messagesEl = $("messages");
const formEl = $("chat-form");
const inputEl = $("message-input");
const sendButton = $("send-button");
const listEl = $("conversation-list");
const statusDot = $("status-dot");
const statusText = $("status-text");
const devicesView = $("devices-view");
const devicesList = $("devices-list");
const chatViewButton = $("chat-view-button");
const devicesViewButton = $("devices-view-button");
const refreshDevicesButton = $("refresh-devices");

function setStatus(kind, text) {
  statusDot.className = "status-dot " + kind;
  statusText.textContent = text;
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch (_) { /* ignore */ }
    throw new Error(detail);
  }
  return res.json();
}

function addMessage(role, content) {
  const el = document.createElement("div");
  el.className = "message " + role;
  el.textContent = content;
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return el;
}

function renderConversations() {
  listEl.innerHTML = "";
  for (const convo of state.conversations) {
    const el = document.createElement("div");
    el.className = "conversation" + (convo.id === state.activeConversationId ? " active" : "");
    el.textContent = convo.title || "(new conversation)";
    el.addEventListener("click", () => openConversation(convo.id));
    listEl.appendChild(el);
  }
}

function setView(view) {
  state.view = view;
  messagesEl.classList.toggle("hidden", view !== "chat");
  formEl.classList.toggle("hidden", view !== "chat");
  devicesView.classList.toggle("hidden", view !== "devices");
  chatViewButton.classList.toggle("active", view === "chat");
  devicesViewButton.classList.toggle("active", view === "devices");
  if (view === "devices") refreshDevices();
}

function formatDate(value) {
  if (!value) return "Never";
  return new Date(value).toLocaleString();
}

function renderDevices(devices) {
  devicesList.innerHTML = "";
  if (devices.length === 0) {
    devicesList.innerHTML = '<div class="empty">No registered devices.</div>';
    return;
  }
  for (const device of devices) {
    const el = document.createElement("article");
    el.className = "device-row";
    const status = device.online ? "Online" : "Offline";
    el.innerHTML = `
      <div class="device-main">
        <div>
          <h3></h3>
          <p></p>
        </div>
        <span class="device-status ${device.online ? "online" : "offline"}">${status}</span>
      </div>
      <dl>
        <div><dt>Last seen</dt><dd>${formatDate(device.last_seen)}</dd></div>
        <div><dt>Agent</dt><dd class="agent-version"></dd></div>
        <div><dt>Capabilities</dt><dd class="capabilities"></dd></div>
      </dl>
    `;
    el.querySelector("h3").textContent = device.name;
    el.querySelector("p").textContent =
      `${device.device_type}${device.operating_system ? " · " + device.operating_system : ""}`;
    el.querySelector(".agent-version").textContent = device.agent_version || "Unknown";
    const caps = el.querySelector(".capabilities");
    caps.textContent = device.capabilities.length ? device.capabilities.join(", ") : "None";
    devicesList.appendChild(el);
  }
}

async function refreshDevices() {
  try {
    renderDevices(await api("/api/devices"));
  } catch (err) {
    devicesList.innerHTML = '<div class="empty">Could not load devices.</div>';
    console.error("Failed to load devices:", err);
  }
}

async function refreshConversations() {
  try {
    state.conversations = await api("/api/conversations");
    renderConversations();
  } catch (err) {
    console.error("Failed to load conversations:", err);
  }
}

async function openConversation(id) {
  if (state.streaming) return;
  state.activeConversationId = id;
  renderConversations();
  messagesEl.innerHTML = "";
  try {
    const messages = await api(`/api/conversations/${id}/messages`);
    for (const m of messages) addMessage(m.role === "assistant" ? "assistant" : "user", m.content);
  } catch (err) {
    addMessage("error", "Couldn't load this conversation.");
    console.error(err);
  }
}

async function newConversation() {
  if (state.streaming) return;
  state.activeConversationId = null;
  messagesEl.innerHTML = "";
  renderConversations();
}

class SSESourceParser {
  constructor() {
    this.buffer = "";
  }

  parse(chunk) {
    this.buffer += chunk;
    const events = [];
    let index;
    while ((index = this.buffer.indexOf("\n\n")) !== -1) {
      const block = this.buffer.slice(0, index);
      this.buffer = this.buffer.slice(index + 2);
      const event = this.parseBlock(block);
      if (event) events.push(event);
    }
    return events;
  }

  parseBlock(block) {
    let eventName = "message";
    let data = [];
    for (const line of block.split("\n")) {
      if (!line || line.startsWith(":")) continue;
      const sep = line.indexOf(":");
      const field = sep === -1 ? line : line.slice(0, sep);
      const value = sep === -1 ? "" : line.slice(sep + 1).replace(/^ /, "");
      if (field === "event") eventName = value;
      else if (field === "data") data.push(value);
    }
    if (data.length === 0) return null;
    return { type: eventName, data: JSON.parse(data.join("\n")) };
  }
}

async function streamReply(conversationId, userText) {
  const body = JSON.stringify({ conversation_id: conversationId, message: userText });
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
  if (!res.ok) {
    let detail = "Stream failed.";
    try { detail = (await res.json()).detail || detail; } catch (_) { /* ignore */ }
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SSESourceParser();
  const bubble = addMessage("assistant", "");
  let full = "";
  let streamConversationId = conversationId;
  let failed = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    for (const event of parser.parse(decoder.decode(value, { stream: true }))) {
      if (event.type === "start") {
        streamConversationId = event.data.conversation_id;
      } else if (event.type === "delta") {
        full += event.data.delta;
        bubble.textContent = full;
        bubble.classList.add("cursor");
        messagesEl.scrollTop = messagesEl.scrollHeight;
      } else if (event.type === "done") {
        full = event.data.content || full;
      } else if (event.type === "error") {
        failed = new Error(event.data.message || "Stream error.");
      }
    }
  }
  bubble.classList.remove("cursor");
  if (failed) throw failed;
  if (streamConversationId) {
    state.activeConversationId = streamConversationId;
    await refreshConversations();
  }
}

async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text || state.streaming) return;

  inputEl.value = "";
  inputEl.style.height = "auto";
  sendButton.disabled = true;

  addMessage("user", text);
  state.streaming = true;

  try {
    const conversationId = state.activeConversationId;
    await streamReply(conversationId, text);
  } catch (err) {
    addMessage("error", "JARVIS couldn't respond right now: " + err.message);
    setStatus("offline", "LLM unavailable");
  } finally {
    state.streaming = false;
    sendButton.disabled = false;
    inputEl.focus();
  }
}

formEl.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage();
});

inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = inputEl.scrollHeight + "px";
  sendButton.disabled = !inputEl.value.trim() || state.streaming;
});

$("new-conversation").addEventListener("click", newConversation);
chatViewButton.addEventListener("click", () => setView("chat"));
devicesViewButton.addEventListener("click", () => setView("devices"));
refreshDevicesButton.addEventListener("click", refreshDevices);

async function init() {
  setStatus("connecting", "Connecting…");
  try {
    const health = await api("/api/health/ready");
    setStatus(health.status === "ready" ? "online" : "offline", health.status);
  } catch (_) {
    setStatus("offline", "API offline");
  }
  await refreshConversations();
  if (state.conversations.length > 0) {
    openConversation(state.conversations[0].id);
  } else {
    messagesEl.innerHTML =
      '<div class="empty">No conversations yet.<br />Message JARVIS to get started.</div>';
  }
  inputEl.focus();
}

init();
