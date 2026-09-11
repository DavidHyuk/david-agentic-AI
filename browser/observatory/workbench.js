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
const missionStatuses = {
  triage: ["접수", "HQ가 작업을 나누는 중"],
  todo: ["계획됨", "선행 작업 대기"],
  ready: ["실행 대기", "담당 에이전트 호출 대기"],
  running: ["작업 중", "에이전트가 실행 중"],
  review: ["검토", "결과 검토 필요"],
  blocked: ["막힘", "확인 또는 재시도 필요"],
  scheduled: ["예약", "지정 시점까지 대기"],
  done: ["완료", "결과 저장됨"],
};
function missionId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  return [...bytes]
    .map((byte, i) =>
      [4, 6, 8, 10].includes(i)
        ? `-${byte.toString(16).padStart(2, "0")}`
        : byte.toString(16).padStart(2, "0"),
    )
    .join("");
}
function missionCard(task) {
  const status = missionStatuses[task.status] || [task.status, ""];
  return `<button class="mission-card" data-mission="${esc(task.id)}"><span class="mission-agent">${esc(roomIcon(task.room))} ${esc(deskTitles[task.room] || task.assignee || "HQ")}</span><strong>${esc(task.title)}</strong><small>${esc(task.id)} · ${when(task.created_at)}</small><span class="mission-state state-${esc(task.status)}">${esc(status[0])}</span>${task.result ? `<p>${esc(task.result.slice(0, 130))}</p>` : ""}</button>`;
}
function hqDesk(d) {
  const o = d.orchestration;
  if (!o.available)
    return `<article class="desk-card mission-command"><span class="tag">COMMAND CENTER</span><h2>오케스트레이션을 준비할 수 없습니다</h2><p>${esc(o.error)}</p></article>`;
  const columns = [
    ["triage", "접수"],
    ["todo,ready,scheduled", "계획 · 대기"],
    ["running,review", "작업 · 검토"],
    ["blocked", "막힘"],
    ["done", "완료"],
  ];
  const draft = localRead("hermes-mission-draft", {});
  return `<article class="desk-card mission-command"><span class="tag">COMMAND CENTER · ${esc(o.board)}</span><h2>HQ에 목표 맡기기</h2><p>목표를 접수하면 HQ가 전문 에이전트별 작업과 의존관계로 나누고 결과를 다시 종합합니다. 제출 즉시 실제 에이전트 실행 대기열에 들어갑니다.</p><form id="mission-form"><label class="desk-field">달성할 목표<input name="goal" maxlength="200" required placeholder="예: 이번 주 Anthropic MLE 면접 준비 계획과 연습 자료를 만들어줘" value="${esc(draft.goal || "")}"></label><label class="desk-field">배경·제약·원하는 결과<textarea name="context" maxlength="4000" rows="5" placeholder="마감, 지원 회사, 산출물 형태, 이미 시도한 내용 등을 적어주세요.">${esc(draft.context || "")}</textarea></label><label class="desk-field compact-field">우선순위<select name="priority"><option value="80" ${draft.priority === "80" ? "selected" : ""}>높음</option><option value="50" ${!draft.priority || draft.priority === "50" ? "selected" : ""}>보통</option><option value="20" ${draft.priority === "20" ? "selected" : ""}>낮음</option></select></label><button class="primary">계획 · 실행 시작</button></form></article>
    <article class="desk-card"><div class="mission-heading"><div><span class="tag">LIVE MISSION BOARD</span><h2>에이전트 작업 흐름</h2></div><span class="dispatcher ${o.dispatcher_alive ? "on" : ""}">● ${o.dispatcher_alive ? "Dispatcher online" : "Dispatcher offline"}</span></div><div class="agent-roster">${o.assignees.map((a) => `<span>${esc(roomIcon(a.room))} ${esc(a.name)} <small>${Object.values(a.counts || {}).reduce((sum, n) => sum + n, 0)}</small></span>`).join("")}</div><div class="mission-board">${columns.map(([keys, title]) => {
      const statuses = keys.split(","),
        tasks = o.tasks.filter((task) => statuses.includes(task.status));
      return `<section class="mission-column"><header><b>${esc(title)}</b><span>${tasks.length}</span></header>${tasks.map(missionCard).join("") || '<div class="mission-empty">비어 있음</div>'}</section>`;
    }).join("")}</div></article><section id="mission-detail"></section>
    <article class="desk-card"><span class="tag">YOUR NEXT MOVE</span><h2>직접 확인할 학습</h2><div class="pending-list">${d.pending.map((a) => `<button data-open-desk="${a.track === "coding" ? "coding" : "design"}"><span>${a.track === "coding" ? "⌨" : "🏗"} ${esc(a.item_id)}</span><small>${esc(a.date)} · 결과 미입력 →</small></button>`).join("")}<button data-open-desk="english"><span>💬 영어 복습 ${d.due_count}개</span><small>교정 문장 연습 →</small></button><button data-open-desk="papers"><span>🔭 읽기 대기 ${d.reading_count}편</span><small>논문 읽기 목록 →</small></button></div></article>`;
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
  if (d.room === "hq" && d.orchestration?.available) wireHq(d);
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
function wireHq(d) {
  const form = $("mission-form");
  form.oninput = () => {
    const saved = Object.fromEntries(new FormData(form));
    saved.request_id = localRead("hermes-mission-draft", {}).request_id;
    localWrite("hermes-mission-draft", saved);
  };
  form.onsubmit = async (event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(form));
    const saved = localRead("hermes-mission-draft", {});
    values.request_id = saved.request_id || missionId();
    localWrite("hermes-mission-draft", values);
    const ok = await deskAction(
      {
        action: "mission_create",
        goal: values.goal,
        context: values.context,
        priority: Number(values.priority),
        request_id: values.request_id,
      },
      "목표를 접수했습니다. HQ가 작업을 나누기 시작합니다.",
    );
    if (ok) {
      localWrite("hermes-mission-draft", null);
      await loadWorkbench();
    }
  };
  document
    .querySelectorAll("[data-mission]")
    .forEach((button) =>
      button.addEventListener("click", () => showMission(button.dataset.mission)),
    );
}
async function showMission(taskId) {
  const target = $("mission-detail");
  if (!target) return;
  target.innerHTML = '<article class="desk-card">실행 기록을 불러오는 중…</article>';
  try {
    const detail = await api("mission", { task: taskId }),
      task = detail.task,
      status = missionStatuses[task.status] || [task.status, task.status],
      assignees = bench.data.orchestration.assignees;
    target.innerHTML = `<article class="desk-card mission-detail-card"><div class="mission-heading"><div><span class="mission-state state-${esc(task.status)}">${esc(status[0])}</span><h2>${esc(task.title)}</h2></div><button class="text-button" id="mission-close">닫기</button></div><p class="mission-meta">${esc(task.id)} · ${esc(task.assignee || "미배정")} · ${when(task.created_at)}</p><div class="mission-body">${linkedText(task.body || "설명 없음")}</div>${detail.latest_summary || task.result ? `<section class="mission-result"><b>현재 결과</b><div>${linkedText(detail.latest_summary || task.result)}</div></section>` : ""}<div class="mission-relations">${detail.parents.length ? `<div><b>선행 작업</b>${detail.parents.map((id) => `<button data-related-mission="${esc(id)}">${esc(id)}</button>`).join("")}</div>` : ""}${detail.children.length ? `<div><b>하위 작업</b>${detail.children.map((id) => `<button data-related-mission="${esc(id)}">${esc(id)}</button>`).join("")}</div>` : ""}</div><details class="desk-help" ${detail.runs.length ? "open" : ""}><summary>실행 시도 ${detail.runs.length}개</summary>${detail.runs.map((run) => `<div class="mission-run"><b>${esc(run.profile)} · ${esc(run.outcome || run.status)}</b><small>${when(run.started_at)}${run.ended_at ? " → " + when(run.ended_at) : ""}</small>${run.summary ? `<p>${linkedText(run.summary)}</p>` : ""}${run.error ? `<p class="mission-error">${esc(run.error)}</p>` : ""}</div>`).join("") || '<p class="muted">아직 실행되지 않았습니다.</p>'}</details><details class="desk-help"><summary>댓글·이벤트 ${detail.comments.length + detail.events.length}개</summary>${detail.comments.map((comment) => `<div class="mission-run"><b>${esc(comment.author)}</b><small>${when(comment.created_at)}</small><p>${linkedText(comment.body)}</p></div>`).join("")}${detail.events.slice().reverse().map((item) => `<div class="mission-event"><span>${esc(item.kind)}</span><small>${when(item.created_at)}</small></div>`).join("")}</details><form id="mission-comment-form" class="mission-inline"><input name="comment" maxlength="2000" required placeholder="방향 수정이나 추가 정보를 남기세요"><button class="outline">댓글 추가</button></form>${!["running", "done", "archived"].includes(task.status) ? `<div class="mission-admin"><label>담당 에이전트<select id="mission-assignee">${assignees.map((a) => `<option value="${esc(a.name)}" ${a.name === task.assignee ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select></label><button class="outline" id="mission-assign">재배정</button>${task.status === "blocked" || task.status === "scheduled" ? '<button class="primary" id="mission-unblock">다시 실행</button>' : '<button class="outline danger" id="mission-block">중지</button>'}</div>` : ""}</article>`;
    $("mission-close").onclick = () => target.replaceChildren();
    target.querySelectorAll("[data-related-mission]").forEach(
      (button) =>
        (button.onclick = () => showMission(button.dataset.relatedMission)),
    );
    $("mission-comment-form").onsubmit = (event) => {
      event.preventDefault();
      const comment = new FormData(event.currentTarget).get("comment");
      deskAction(
        { action: "mission_comment", task: task.id, comment },
        "작업에 댓글을 추가했습니다.",
      );
    };
    if ($("mission-assign"))
      $("mission-assign").onclick = () =>
        deskAction(
          {
            action: "mission_assign",
            task: task.id,
            assignee: $("mission-assignee").value,
          },
          "담당 에이전트를 바꿨습니다.",
        );
    if ($("mission-unblock"))
      $("mission-unblock").onclick = () =>
        deskAction(
          { action: "mission_unblock", task: task.id },
          "작업을 실행 대기열로 돌려보냈습니다.",
        );
    if ($("mission-block"))
      $("mission-block").onclick = () => {
        const reason = prompt("중지 이유를 입력하세요.");
        if (reason)
          deskAction(
            { action: "mission_block", task: task.id, reason },
            "작업을 중지했습니다.",
          );
      };
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    target.innerHTML = `<article class="desk-card"><p class="mission-error">${esc(error.message)}</p></article>`;
  }
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
window.hermesMissionRefresh = setInterval(() => {
  const active = document.activeElement;
  if (
    bench.room === "hq" &&
    state.view === "workbench" &&
    !bench.busy &&
    !["INPUT", "TEXTAREA", "SELECT"].includes(active?.tagName) &&
    !$("mission-detail")?.children.length
  )
    loadWorkbench();
}, 10000);
