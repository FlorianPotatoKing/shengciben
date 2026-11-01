// 复习页逻辑：从后端抽卡 -> 显示题目 -> 揭晓答案 -> 自评。
// 支持两种模式：word（单词）和 sentence（句子），由 URL ?type= 决定。
(function () {
  const stage = document.getElementById("stage");
  const counter = document.getElementById("counter");
  if (!stage) return;

  const params = new URLSearchParams(window.location.search);
  const rawType = params.get("type") || "word";
  const kind = ["word", "phrase", "sentence"].includes(rawType) ? rawType : "word";

  let reviewed = 0;
  let currentId = null;

  function updateCounter() {
    counter.textContent = `本次已复习 ${reviewed} 条`;
  }

  async function fetchJSON(url, options) {
    const res = await fetch(url, options);
    if (res.status === 401) {
      window.location.href = "/login";
      throw new Error("未登录");
    }
    return res.json();
  }

  async function nextCard() {
    const data = await fetchJSON(`/api/review/next?type=${kind}`);
    if (data.done) {
      renderDone();
      return;
    }
    currentId = data.id;
    renderQuestion(data);
  }

  function renderQuestion(card) {
    if (card.type === "sentence") {
      stage.innerHTML = `
        <div class="review-card">
          <span class="review-tag">${escapeHtml(card.category || "未分类")}</span>
          <p class="review-explanation">${escapeHtml(card.explanation || "")}</p>
          <p class="review-hint">想一想对应的英文句子…</p>
          <div class="review-actions">
            <button class="btn btn-primary" id="reveal-btn">显示答案</button>
          </div>
        </div>`;
    } else {
      const exampleHtml = card.example_blank
        ? `<p class="review-example"><span class="review-blank">${escapeHtml(card.example_blank)}</span></p>`
        : "";
      stage.innerHTML = `
        <div class="review-card">
          <h1 class="review-word">${escapeHtml(card.word)}</h1>
          ${exampleHtml}
          <div class="review-actions">
            <button class="btn btn-primary" id="reveal-btn">显示答案</button>
          </div>
        </div>`;
    }
    document.getElementById("reveal-btn").addEventListener("click", () => reveal(card));
  }

  function reveal(card) {
    if (card.type === "sentence") {
      stage.innerHTML = `
        <div class="review-card">
          <span class="review-tag">${escapeHtml(card.category || "未分类")}</span>
          <p class="review-sentence">${escapeHtml(card.sentence)}</p>
          ${
            card.explanation
              ? `<div class="review-answer"><p class="review-meaning">${escapeHtml(card.explanation)}</p></div>`
              : ""
          }
          <div class="review-actions">
            <button class="btn btn-forgot" id="forgot-btn">不记得</button>
            <button class="btn btn-remember" id="remember-btn">记得</button>
          </div>
        </div>`;
    } else {
      stage.innerHTML = `
        <div class="review-card">
          <h1 class="review-word">${escapeHtml(card.word)}</h1>
          ${
            card.example
              ? `<p class="review-example">${escapeHtml(card.example)}</p>`
              : ""
          }
          <div class="review-answer">
            <p class="review-meaning">${escapeHtml(card.meaning)}</p>
          </div>
          <div class="review-actions">
            <button class="btn btn-forgot" id="forgot-btn">不记得</button>
            <button class="btn btn-remember" id="remember-btn">记得</button>
          </div>
        </div>`;
    }
    document.getElementById("forgot-btn").addEventListener("click", () => answer(false));
    document.getElementById("remember-btn").addEventListener("click", () => answer(true));
  }

  async function answer(remembered) {
    await fetchJSON("/api/review/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: currentId, type: kind, remembered }),
    });
    reviewed += 1;
    updateCounter();
    nextCard();
  }

  function renderDone() {
    const label = { word: "单词", phrase: "短语", sentence: "句子" }[kind];
    stage.innerHTML = `
      <div class="review-done">
        <h2>🎉 没有可复习的${label}了</h2>
        <p>先到「${label}」板块录入一些内容吧。</p>
        <a href="/" class="btn btn-primary">返回</a>
      </div>`;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML;
  }

  updateCounter();
  nextCard();
})();
