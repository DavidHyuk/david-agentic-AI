// Author: David Choi. Purpose: resumable study desks and explicit progress actions.
"use strict";
let bench = { room: "hq", data: null, request: 0, busy: false };
const deskTitles = {
  papers: "Frontier Radar",
  interview: "Interview Lab",
  coding: "LeetCode Gym",
  design: "Design Studio",
  english: "English Lab",
  hq: "Hermes HQ",
};
const deskSubtitles = {
  papers: "관심 논문을 모으고, 읽은 내용을 나만의 지식으로.",
  interview: "가장 최근 드릴에서 시작해 내 답변을 다듬어 보세요.",
  coding: "풀던 문제를 이어서. 실제 풀이 결과로 다음 과제를 준비합니다.",
  design: "요구사항부터 실패 시나리오까지, 설명할 수 있는 설계로.",
  english: "실제 교정 문장을 복습하고 다음 복습 날짜를 정합니다.",
  hq: "내가 확인할 일과 다음 행동을 한곳에서.",
};
const draftKey = (room) => `hermes-draft:${room}`;
function localRead(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
}
function localWrite(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {}
}
function safeLink(url, label) {
  return /^https?:\/\//i.test(url || "")
    ? `<a class="outline desk-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`
    : "";
}
async function openWorkbench(room) {
  localWrite("hermes-last-room", room);
  bench.room = room;
  bench.data = null;
  view("workbench");
  $("bench-title").textContent = deskTitles[room] || roomName(room);
  $("bench-subtitle").textContent =
    deskSubtitles[room] || "프로필 활동과 기록을 살펴보세요.";
  $("bench-status").textContent = "";
  $("bench-content").innerHTML =
    '<div class="empty">작업실을 준비하는 중…</div>';
  await loadWorkbench();
}
async function loadWorkbench() {
  const room = bench.room,
    request = ++bench.request;
  try {
    const data = await api("workbench", { room });
    if (request !== bench.request) return;
    bench.data = data;
    renderWorkbench(data);
  } catch (e) {
    if (request === bench.request) $("bench-status").textContent = e.message;
  }
}
async function deskAction(body, success = "저장했습니다.") {
  if (bench.busy) return false;
  const room = bench.room;
  bench.busy = true;
  $("bench-status").textContent = "저장 중…";
  const buttons = Array.from(
    document.querySelectorAll("#bench-content button"),
    (button) => ({ button, disabled: button.disabled }),
  );
  buttons.forEach(({ button }) => (button.disabled = true));
  try {
    const response = await fetch("api/action", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Hermes-Action": "1" },
      body: JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "저장하지 못했습니다.");
    if (body.action === "note") localWrite(draftKey(room), null);
    if (room === bench.room) {
      await loadWorkbench();
      $("bench-status").textContent = success;
    }
    return true;
  } catch (e) {
    if (room === bench.room) $("bench-status").textContent = e.message;
    return false;
  } finally {
    bench.busy = false;
    buttons.forEach(({ button, disabled }) => (button.disabled = disabled));
  }
}
function field(label, name, kind = "number", extra = "") {
  return `<label class="desk-field">${esc(label)}<input name="${name}" type="${kind}" required ${extra}></label>`;
}
function selectField(label, name, options) {
  return `<label class="desk-field">${esc(label)}<select name="${name}" required><option value="">선택하세요</option>${options.map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join("")}</select></label>`;
}
const yesNo = [
  ["true", "예"],
  ["false", "아니오"],
];
function coachDesk(d) {
  const a = d.pending[0];
  if (!a)
    return `<article class="desk-card"><span class="tag">TODAY</span><h2>이어갈 미완료 과제가 없습니다</h2><p>학습 기록에 맞춰 오늘의 과제를 배정합니다. 과제 배정은 학습 완료로 기록되지 않습니다.</p><button id="desk-plan" class="primary" ${!d.catalog_available ? "disabled" : ""}>${d.today_assignment?.completed ? "오늘 완료한 과제 확인" : "오늘 과제 준비하기"}</button>${!d.catalog_available ? "<p>커리큘럼 카탈로그가 아직 설치되지 않았습니다.</p>" : ""}</article>`;
  const item = a.item,
    coding = d.track === "coding";
  return `<article class="desk-card mission"><span class="tag">이어하기 · ${esc(a.date)} 배정 · ${a.session_type === "review" ? "복습" : "새 과제"}</span><h2>${esc(item.name || a.item_id)}</h2><p>${esc(coding ? item.goal : item.exercise)}</p><div class="desk-tags"><span>${esc(item.pattern || "System design")}</span><span>목표 ${coding ? 35 : item.target_minutes}분</span><span>결과 미입력</span>${coding ? `<span>기록된 힌트 ${a.hint_level} / 3</span>` : ""}</div>
    <div class="desk-actions">${coding ? safeLink(item.leetcode_url, "LeetCode 문제") + safeLink(item.neetcode_url, "NeetCode 문제") : safeLink(item.url, "Hello Interview")}</div>
    ${coding ? '<p class="muted">먼저 20분 동안 스스로 시도하고, 경계 조건과 시간·공간 복잡도를 설명해 보세요.</p>' : `<ul class="desk-focus">${(item.focus || []).map((f) => `<li>${esc(f)}</li>`).join("")}</ul><p>${esc(item.hermes_connection || "")}</p>${item.access_note ? `<p class="muted">${esc(item.access_note)}</p>` : ""}`}
    <div class="study-timer"><span id="study-time">00:00</span><div><button class="outline" id="timer-toggle">타이머 시작</button><button class="text-button" id="timer-reset">초기화</button></div><small>이 브라우저에서 이어집니다 · 타이머 종료는 완료 처리되지 않습니다</small></div>
    <details class="desk-help"><summary>Hermes에게 이어서 질문할 내용</summary><textarea id="coach-prompt" readonly>현재 ${esc(item.name || a.item_id)} 과제를 공부 중이야. 과제 ID는 ${esc(a.id)}야. ${coding ? "내 접근 방법을 먼저 물어보고, 요청하면 현재 힌트 단계 다음의 힌트 하나만 줘. 정답부터 보여주지 마." : "내 설계의 요구사항을 먼저 물어보고, 답변을 바탕으로 트레이드오프와 실패 시나리오를 질문해줘."}</textarea><button class="outline" id="copy-coach-prompt">질문 복사</button><small>복사한 내용을 해당 Telegram 방에서 보내면 됩니다.</small></details>
  </article>
  <article class="desk-card"><h2>실제 학습 결과 남기기</h2><p class="muted">본인이 보고한 결과만 저장합니다. 저장하면 다음 복습과 주간 리뷰에 반영됩니다.</p><form id="coach-feedback"><div class="feedback-grid">
    ${field("공부한 시간 (분)", "duration", "number", 'min="1" max="1440"')}${selectField(
      "자신감",
      "confidence",
      [1, 2, 3, 4, 5].map((n) => [n, n + " / 5"]),
    )}
    ${
      coding
        ? `${selectField("독립적으로 풀었나요?", "independent", yesNo)}${selectField("정답·해설을 봤나요?", "solution_viewed", yesNo)}${selectField(
            "가장 높은 힌트 단계",
            "hint_level",
            [0, 1, 2, 3].map((n) => [n, String(n)]),
          )}`
        : ["requirements", "architecture", "trade_off", "failure_mode"]
            .map((k, i) =>
              selectField(
                ["요구사항", "아키텍처", "트레이드오프", "실패 시나리오"][i] +
                  " 자기 평가",
                k + "_score",
                [1, 2, 3, 4, 5].map((n) => [n, n + " / 5"]),
              ),
            )
            .join("")
    }
    </div><label class="desk-field">${coding ? "배운 점 또는 실수" : "다음에 개선할 점"}<textarea name="${coding ? "lesson" : "next_improvement"}" required maxlength="16000" rows="4" placeholder="구체적인 경험을 남겨주세요."></textarea></label><button class="primary">결과 저장 · 완료 기록</button></form></article>`;
}
function englishDesk(d) {
  return `<div class="desk-metrics"><div><b>${d.due_count}</b><span>오늘 복습할 카드</span></div><div><b>${d.total_cards}</b><span>전체 교정 카드</span></div></div><article class="desk-card"><h2>오늘의 영어 복습</h2><p class="muted">먼저 문장을 고쳐 말해보세요. 정답은 각 문장 바로 아래에 있습니다. 자기 채점 결과를 저장하면 다음 복습일이 바뀝니다.</p>${d.due.length ? d.due.map((c, i) => `<section class="srs-card"><span class="tag">${i + 1} · Box ${c.box} · ${esc(c.due)}</span><h3>${esc(c.wrong)}</h3><p class="srs-answer"><b>정답</b> ${esc(c.correct)}</p><p class="muted">${esc(c.note || "")}</p><div class="desk-actions"><button class="outline" data-srs="${i}" data-result="wrong">다시 연습할래요</button><button class="primary" data-srs="${i}" data-result="correct">맞혔어요</button></div></section>`).join("") : '<div class="empty">오늘 복습할 카드를 모두 마쳤습니다.</div>'}${d.due_count > 30 ? "<p>한 번에 30개씩 표시합니다. 복습하면 다음 카드가 나타납니다.</p>" : ""}</article>`;
}
function papersDesk(d) {
  return `<article class="desk-card"><h2>내 읽기 목록</h2>${d.reading_list.length ? d.reading_list.map((p, i) => `<div class="reading-row"><div><strong>${esc(p.title)}</strong><span>${p.read ? "읽음" : "읽기 대기"}</span></div><div>${safeLink(p.url, "원문")}<button class="outline" data-paper-read="${i}">${p.read ? "다시 읽기" : "읽음으로 표시"}</button></div></div>`).join("") : "<p>아래 논문에서 읽고 싶은 항목을 추가하세요.</p>"}</article><article class="desk-card"><h2>최신 논문에서 고르기</h2><p class="muted">현재 카탈로그의 최신 12편입니다. 전체 논문은 기록 보관소에서 검색할 수 있습니다.</p>${d.papers.map((p, i) => `<div class="reading-row"><div><strong>${esc(p.title)}</strong><p class="paper-excerpt">${esc(p.content)}</p></div><div>${safeLink(p.url, "원문")}<button class="outline" data-bookmark="${i}">${d.reading_list.some((x) => x.id === p.id) ? "목록에 있음" : "읽기 목록에 추가"}</button></div></div>`).join("")}</article>`;
}
function hqDesk(d) {
  return `<article class="desk-card"><span class="tag">YOUR NEXT MOVE</span><h2>내가 확인할 일</h2><div class="pending-list">${d.pending.map((a) => `<button data-open-desk="${a.track === "coding" ? "coding" : "design"}"><span>${a.track === "coding" ? "⌨" : "🏗"} ${esc(a.item_id)}</span><small>${esc(a.date)} · 결과 미입력 →</small></button>`).join("")}<button data-open-desk="english"><span>💬 영어 복습 ${d.due_count}개</span><small>교정 문장 연습 →</small></button><button data-open-desk="papers"><span>🔭 읽기 대기 ${d.reading_count}편</span><small>논문 읽기 목록 →</small></button></div></article><article class="desk-card"><h2>이번 주의 집중 영역</h2><p>오른쪽 노트에 이번 주 우선순위와 막힌 부분을 남겨보세요. 과제 결과는 각 학습 작업실에서 저장하면 기존 주간 리뷰에서도 활용됩니다.</p><div class="desk-actions"><button class="outline" data-open-desk="interview">MLE 답변 연습</button><button class="outline" data-open-desk="design">설계 이어하기</button></div></article>`;
}
function renderWorkbench(d) {
  let body;
  if (["coding", "design"].includes(d.room)) body = coachDesk(d);
  else if (d.room === "english") body = englishDesk(d);
  else if (d.room === "papers") body = papersDesk(d);
  else if (d.room === "hq") body = hqDesk(d);
  else if (d.room === "interview")
    body = `<article class="desk-card"><span class="tag">최근 저장된 드릴${d.drill_session ? " · " + when(d.drill_session.started_at) : ""}</span><h2>내 답변으로 연습하기</h2><p class="muted">이전에 생성된 드릴을 바탕으로 답변과 개선할 점을 노트에 기록하세요. 자동 평가 점수는 생성하지 않습니다.</p><div class="drill-body">${linkedText(d.drill || "아직 드릴 기록이 없습니다. 다음 알림이 도착하면 이곳에 표시됩니다.")}</div></article>`;
  else
    body =
      '<article class="desk-card"><h2>프로필 활동</h2><p>이 독립 프로필의 대화·작업 기록을 확인할 수 있습니다.</p></article>';
  const editable = Boolean(deskTitles[d.room]);
  const draft = localRead(draftKey(d.room), null);
  $("bench-content").innerHTML =
    `<div class="workbench-grid"><div class="desk-main">${body}</div><aside class="desk-side">${editable ? `<article class="desk-card"><h2>${d.room === "interview" ? "내 답변 · 회고" : "작업실 노트"}</h2><form id="desk-note-form"><textarea id="desk-note" rows="10" maxlength="16000" required placeholder="오늘의 생각, 다음에 이어갈 내용을 남겨주세요.">${esc(draft ?? d.note)}</textarea><p class="muted">초안은 이 브라우저에 보관됩니다. 저장한 노트는 다른 기기에서도 이어볼 수 있습니다.</p><button class="primary">노트 저장</button></form></article>` : ""}<article class="desk-card"><h2>최근 기록</h2>${d.recent.map((s, i) => `<button class="desk-history" data-desk-session="${i}"><b>${esc(s.title)}</b><small>${when(s.started_at)}</small></button>`).join("") || '<p class="muted">저장된 세션이 없습니다.</p>'}</article>${
      d.completed
        ? `<article class="desk-card"><h2>실제 완료 기록 ${d.completed.length}개</h2>${
            d.completed
              .slice(0, 5)
              .map(
                (r) =>
                  `<details class="desk-help"><summary>${esc(r.problem || r.topic)} · ${esc(r.date)}</summary><p>${esc(r.lesson || r.next_improvement)}</p><p>${r.duration}분 · 자신감 ${r.confidence}/5 · 다음 복습 ${esc(r.next_review_date)}</p></details>`,
              )
              .join("") ||
            '<p class="muted">풀이 결과를 제출하면 여기에 표시됩니다.</p>'
          }</article>`
        : ""
    }<article class="desk-card"><h2>작업실 활동</h2>${d.events.map((e) => `<div class="desk-event"><b>${esc({ note: "노트 저장", bookmark: "읽기 목록 추가", paper_read: "읽기 상태 변경" }[e.action] || e.action)}</b><small>${when(e.time)}</small>${e.note ? `<details><summary>이 버전 보기</summary><p class="saved-note">${esc(e.note)}</p></details>` : ""}</div>`).join("") || '<p class="muted">노트와 읽기 목록 변경이 여기에 남습니다.</p>'}</article></aside></div>`;
  if (editable) {
    $("desk-note").oninput = () =>
      localWrite(draftKey(d.room), $("desk-note").value);
    $("desk-note-form").onsubmit = (e) => {
      e.preventDefault();
      deskAction(
        {
          action: "note",
          room: d.room,
          revision: d.revision,
          note: $("desk-note").value,
        },
        "노트를 저장했습니다.",
      );
    };
  }
  document
    .querySelectorAll("[data-desk-session]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          openSession(d.recent[Number(b.dataset.deskSession)])),
    );
  document
    .querySelectorAll("[data-open-desk]")
    .forEach((b) => (b.onclick = () => openWorkbench(b.dataset.openDesk)));
  document.querySelectorAll("[data-srs]").forEach(
    (b) =>
      (b.onclick = () => {
        const card = d.due[Number(b.dataset.srs)];
        deskAction(
          {
            action: "srs_review",
            card: card.id,
            result: b.dataset.result,
            expected_reviews: card.reviews || 0,
          },
          "복습 결과와 다음 복습일을 저장했습니다.",
        );
      }),
  );
  document
    .querySelectorAll("[data-bookmark]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          deskAction(
            {
              action: "bookmark",
              room: "papers",
              paper: d.papers[Number(b.dataset.bookmark)].id,
              revision: d.revision,
            },
            "읽기 목록에 추가했습니다.",
          )),
    );
  document.querySelectorAll("[data-paper-read]").forEach(
    (b) =>
      (b.onclick = () => {
        const p = d.reading_list[Number(b.dataset.paperRead)];
        deskAction(
          {
            action: "paper_read",
            room: "papers",
            paper: p.id,
            read: !p.read,
            revision: d.revision,
          },
          "읽기 상태를 저장했습니다.",
        );
      }),
  );
  if ($("desk-plan"))
    $("desk-plan").onclick = () =>
      deskAction(
        { action: "plan", track: d.track },
        "오늘의 과제를 확인했습니다.",
      );
  if ($("coach-feedback")) wireCoach(d);
}
function wireCoach(d) {
  const assignment = d.pending[0],
    form = $("coach-feedback");
  const key = "hermes-feedback:" + assignment.id;
  const draft = localRead(key, {});
  for (const el of form.elements)
    if (el.name && draft[el.name] !== undefined) el.value = draft[el.name];
  form.oninput = () => localWrite(key, Object.fromEntries(new FormData(form)));
  form.onsubmit = async (e) => {
    e.preventDefault();
    const values = Object.fromEntries(new FormData(form)),
      feedback = {};
    for (const [k, v] of Object.entries(values)) {
      feedback[k] = ["lesson", "next_improvement"].includes(k)
        ? v
        : ["independent", "solution_viewed"].includes(k)
          ? v === "true"
          : Number(v);
    }
    const ok = await deskAction(
      {
        action: "feedback",
        track: d.track,
        assignment: assignment.id,
        feedback,
      },
      "실제 완료 기록과 다음 복습 날짜를 저장했습니다.",
    );
    if (ok) localWrite(key, null);
  };
  $("copy-coach-prompt").onclick = async () => {
    const el = $("coach-prompt");
    el.focus();
    el.select();
    try {
      if (navigator.clipboard && isSecureContext)
        await navigator.clipboard.writeText(el.value);
      else if (!document.execCommand("copy")) throw new Error();
      $("bench-status").textContent =
        "질문을 복사했습니다. Telegram에서 보내세요.";
    } catch {
      $("bench-status").textContent = "선택된 질문을 직접 복사하세요.";
    }
  };
  wireTimer(assignment.id);
}
function wireTimer(id) {
  const key = "hermes-timer:" + id;
  const read = () => localRead(key, { elapsed: 0, started: null });
  $("timer-toggle").onclick = () => {
    const t = read();
    if (t.started) {
      t.elapsed += Date.now() - t.started;
      t.started = null;
    } else t.started = Date.now();
    localWrite(key, t);
    paintTimer();
  };
  $("timer-reset").onclick = () => {
    localWrite(key, { elapsed: 0, started: null });
    paintTimer();
  };
  function paintTimer() {
    if (!$("study-time") || bench.data?.pending?.[0]?.id !== id) return;
    const t = read(),
      seconds = Math.floor(
        (t.elapsed + (t.started ? Date.now() - t.started : 0)) / 1000,
      );
    $("study-time").textContent =
      `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
    $("timer-toggle").textContent = t.started ? "일시정지" : "타이머 이어가기";
  }
  paintTimer();
  clearInterval(window.hermesStudyClock);
  window.hermesStudyClock = setInterval(paintTimer, 1000);
}
$("bench-home").onclick = () => view("office");
$("bench-reload").onclick = loadWorkbench;
$("bench-history").onclick = () => {
  clearFilters();
  $("room-filter").value = bench.room;
  state.sessionsOffset = 0;
  view("sessions");
};
