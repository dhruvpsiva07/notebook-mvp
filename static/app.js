"use strict";

const $ = (id) => document.getElementById(id);
const selected = new Set();
let sources = [];

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (res.status === 204) {
    return null;
  }
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

function postJson(path, body) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// Minimal Markdown: headings, lists, bold, italics, code, citations.
function inline(text, citeMap) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\[S(\d+)\]/g, (match, n) => (citeMap.has(Number(n))
      ? `<button type="button" class="cite" data-n="${n}">${n}</button>`
      : match));
}

function renderMarkdown(text, citeMap) {
  const out = [];
  let list = null;
  const closeList = () => {
    if (list) {
      out.push(`</${list}>`);
      list = null;
    }
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    const bullet = line.match(/^[-*]\s+(.*)$/);
    const numbered = line.match(/^\d+[.)]\s+(.*)$/);
    if (heading) {
      closeList();
      const level = heading[1].length + 1;
      out.push(`<h${level}>${inline(heading[2], citeMap)}</h${level}>`);
    } else if (bullet || numbered) {
      const type = bullet ? "ul" : "ol";
      if (list !== type) {
        closeList();
        out.push(`<${type}>`);
        list = type;
      }
      out.push(`<li>${inline((bullet || numbered)[1], citeMap)}</li>`);
    } else if (line) {
      closeList();
      out.push(`<p>${inline(line, citeMap)}</p>`);
    } else {
      closeList();
    }
  }
  closeList();
  return out.join("");
}

function answerElement(data) {
  const citeMap = new Map(data.citations.map((c) => [c.n, c]));
  const el = document.createElement("div");
  el.className = "answer";
  el.innerHTML = renderMarkdown(data.answer, citeMap);
  el.addEventListener("click", (event) => {
    const chip = event.target.closest(".cite");
    if (chip) {
      showCitation(citeMap.get(Number(chip.dataset.n)));
    }
  });
  return el;
}

function showCitation(citation) {
  $("citation-title").textContent = `[${citation.n}] ${citation.source}`;
  $("citation-text").textContent = citation.text;
  $("citation-panel").hidden = false;
}

function renderSources() {
  const list = $("source-list");
  list.innerHTML = "";
  for (const source of sources) {
    const li = document.createElement("li");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.style.width = "auto";
    box.checked = selected.has(source.id);
    box.addEventListener("change", () => {
      if (box.checked) {
        selected.add(source.id);
      } else {
        selected.delete(source.id);
      }
    });
    const name = document.createElement("span");
    name.className = "name";
    name.title = source.name;
    name.textContent = source.name;
    const meta = document.createElement("span");
    meta.className = "meta";
    meta.textContent = `${source.chunks} chunks`;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "×";
    remove.title = "Remove source";
    remove.addEventListener("click", async () => {
      await api(`/api/sources/${source.id}`, { method: "DELETE" });
      selected.delete(source.id);
      await loadSources();
    });
    li.append(box, name, meta, remove);
    list.append(li);
  }
}

async function loadSources() {
  sources = await api("/api/sources");
  renderSources();
}

function addedSources(newSources) {
  for (const source of newSources) {
    selected.add(source.id);
  }
  return loadSources();
}

function addMessage(className, content) {
  const empty = document.querySelector("#messages .empty");
  if (empty) {
    empty.remove();
  }
  const el = document.createElement("div");
  el.className = `msg ${className}`;
  if (typeof content === "string") {
    el.textContent = content;
  } else {
    el.append(content);
  }
  $("messages").append(el);
  el.scrollIntoView({ behavior: "smooth", block: "end" });
  return el;
}

$("file-input").addEventListener("change", async (event) => {
  const form = new FormData();
  for (const file of event.target.files) {
    form.append("files", file);
  }
  try {
    await addedSources(await api("/api/sources", { method: "POST", body: form }));
  } catch (err) {
    alert(err.message);
  }
  event.target.value = "";
});

$("paste-add").addEventListener("click", async () => {
  try {
    const added = await postJson("/api/sources", {
      name: $("paste-name").value,
      text: $("paste-text").value,
    });
    $("paste-name").value = "";
    $("paste-text").value = "";
    await addedSources(added);
  } catch (err) {
    alert(err.message);
  }
});

$("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = $("question").value.trim();
  if (!question) {
    return;
  }
  $("question").value = "";
  addMessage("user", question);
  const pending = addMessage("pending", "Reading your sources...");
  try {
    const data = await postJson("/api/chat", {
      question,
      source_ids: [...selected],
    });
    pending.className = "msg";
    pending.textContent = "";
    pending.append(answerElement(data));
  } catch (err) {
    pending.className = "msg error";
    pending.textContent = err.message;
  }
});

document.querySelectorAll(".studio-buttons button").forEach((button) => {
  button.addEventListener("click", async () => {
    const card = document.createElement("div");
    card.className = "studio-card";
    card.innerHTML = `<h3>${escapeHtml(button.textContent)}</h3>`
      + "<p class=\"hint\">Generating...</p>";
    $("studio-output").prepend(card);
    button.disabled = true;
    try {
      const data = await postJson("/api/studio", {
        kind: button.dataset.kind,
        source_ids: [...selected],
      });
      card.querySelector(".hint").replaceWith(answerElement(data));
    } catch (err) {
      card.querySelector(".hint").textContent = err.message;
    } finally {
      button.disabled = false;
    }
  });
});

$("citation-close").addEventListener("click", () => {
  $("citation-panel").hidden = true;
});

loadSources();
