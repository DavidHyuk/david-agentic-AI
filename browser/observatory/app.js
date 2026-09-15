// Author: David Choi. Purpose: real-data campus, searchable archives and transcripts.
"use strict";
const $ = (id) => document.getElementById(id);
const state = {
  overview: null,
  view: "office",
  sessionsOffset: 0,
  libraryOffset: 0,
  detail: null,
  request: 0,
  libraryRequest: 0,
  replay: null,
};
const names = {
  office: "사무실",
  sessions: "대화 & 작업 기록",
  schedule: "알림 스케줄",
  library: "기록 보관소",
  workbench: "작업실",
};
const officeCast = {
  hq: {
    index: 0,
    name: "Hermes",
    role: "Team lead",
    activities: [
      ["오늘의 흐름을 정리하는 중", "observe"],
      ["커피를 내리는 중", "stroll"],
      ["팀의 기록을 둘러보는 중", "read"],
    ],
  },
  papers: {
    index: 1,
    name: "Iris",
    role: "Research analyst",
    activities: [
      ["논문을 읽는 중", "read"],
      ["매우 작은 글씨와 싸우는 중", "focus"],
      ["온실의 식물을 돌보는 중", "stroll"],
    ],
  },
  interview: {
    index: 2,
    name: "Theo",
    role: "Interview coach",
    activities: [
      ["면접 카드를 정리하는 중", "read"],
      ["좋은 질문을 고민하는 중", "observe"],
      ["거울 앞에서 발음 연습 중", "chat"],
    ],
  },
  coding: {
    index: 3,
    name: "Jun",
    role: "Coding engineer",
    activities: [
      ["키보드를 닦는 중", "focus"],
      ["새 단축키를 실험하는 중", "read"],
      ["간식을 찾으러 가는 중", "stroll"],
    ],
  },
  design: {
    index: 4,
    name: "Mina",
    role: "Systems architect",
    activities: [
      ["블루프린트를 검토하는 중", "read"],
      ["화이트보드를 재배치하는 중", "stroll"],
      ["장애 시나리오를 상상하는 중", "observe"],
    ],
  },
  english: {
    index: 5,
    name: "Ellie",
    role: "English tutor",
    activities: [
      ["오늘의 표현을 정리하는 중", "read"],
      ["새 예문을 쓰는 중", "focus"],
      ["창가에서 소리 내어 읽는 중", "chat"],
    ],
  },
  podcast: {
    index: 6,
    name: "Rina",
    role: "Podcast host",
    activities: [
      ["오늘의 에피소드를 듣는 중", "listen"],
      ["오디오 레벨을 맞추는 중", "focus"],
      ["리듬을 타며 쉬는 중", "stroll"],
    ],
  },
};
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
function linkedText(value) {
  return String(value ?? "")
    .split(/(https?:\/\/[^\s<>"']+)/g)
    .map((part, index) => {
      if (index % 2 === 0) return esc(part);
      const url = part.replace(/[),.;\]]+$/, "");
      return `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(url)}</a>${esc(part.slice(url.length))}`;
    })
    .join("");
}
function when(value) {
  if (!value) return "기록 없음";
  const d = new Date(typeof value === "number" ? value * 1000 : value);
  return Number.isNaN(d.getTime())
    ? String(value)
    : new Intl.DateTimeFormat("ko-KR", {
        timeZone: "America/Los_Angeles",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(d);
}
function relative(value) {
  const seconds = Date.now() / 1000 - Number(value);
  if (seconds < 60) return "방금 전";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}분 전`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}시간 전`;
  return `${Math.floor(seconds / 86400)}일 전`;
}
async function api(path, params = {}) {
  const response = await fetch(`api/${path}?${new URLSearchParams(params)}`, {
    cache: "no-store",
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "연결 오류");
  return result;
}
function error(err) {
  $("error").hidden = false;
  $("error").textContent = err.message;
}
function roomName(id) {
  return state.overview?.rooms.find((r) => r.id === id)?.title || id;
}
function roomIcon(id) {
  return state.overview?.rooms.find((r) => r.id === id)?.icon || "✦";
}
function view(name, historyMode = "push", route = {}) {
  state.view = names[name] ? name : "office";
  Object.keys(names).forEach((k) => ($(k + "-view").hidden = k !== state.view));
  document
    .querySelectorAll("nav button")
    .forEach((b) =>
      b.classList.toggle("active", b.dataset.view === state.view),
  );
  $("breadcrumb").textContent = names[state.view];
  const query = state.view === "workbench" && route.room
    ? `?room=${encodeURIComponent(route.room)}`
    : "";
  const historyState = { view: state.view, room: route.room || null };
  if (historyMode === "push") history.pushState(historyState, "", "#" + state.view + query);
  else if (historyMode === "replace") history.replaceState(historyState, "", "#" + state.view + query);
  if (state.view === "sessions") loadSessions();
  if (state.view === "library") loadLibrary();
  window.sharedOffice?.visibility();
}
function pager(id, data, callback) {
  const container = $(id);
  container.replaceChildren();
  if (!data.total) return;
  const prev = document.createElement("button"),
    next = document.createElement("button"),
    label = document.createElement("span");
  prev.textContent = "← 이전";
  next.textContent = "다음 →";
  prev.disabled = data.offset === 0;
  next.disabled = data.offset + data.limit >= data.total;
  label.textContent = `${data.offset + 1}–${Math.min(data.offset + data.limit, data.total)} / ${data.total.toLocaleString()}`;
  prev.onclick = () => callback(Math.max(0, data.offset - data.limit));
  next.onclick = () => callback(data.offset + data.limit);
  container.append(prev, label, next);
}
function options(id, items, all) {
  const el = $(id),
    old = el.value;
  el.replaceChildren();
  if (all) {
    const option = new Option(all, "");
    el.add(option);
  }
  items.forEach(([value, label]) => el.add(new Option(label, value)));
  if ([...el.options].some((o) => o.value === old)) el.value = old;
}
function nextRoomJob(room) {
  return room.jobs
    .filter((job) => job.enabled && job.next_run_at)
    .sort((a, b) => a.next_run_at.localeCompare(b.next_run_at))[0];
}
function drawOverview() {
  const d = state.overview;
  const alive = d.profiles.filter((p) => p.alive).length;
  const cards = [
    [
      "연결된 프로필",
      `${alive} / ${d.profiles.length}`,
      `gateway 보고 작업 ${d.profiles.reduce((sum, p) => sum + (p.active_agents || 0), 0)}개`,
      "◉",
    ],
    ["오늘의 세션", d.today_sessions, "LA 현지 날짜 기준", "↗"],
    [
      "보관된 대화",
      d.total_sessions.toLocaleString(),
      `${d.total_messages.toLocaleString()}개 메시지 집계`,
      "☷",
    ],
    [
      "예약된 알림",
      d.jobs.filter((j) => j.enabled).length,
      "프로필별 cron 스케줄",
      "◷",
    ],
  ];
  $("stats").innerHTML = cards
    .map(
      ([label, n, note, icon]) =>
        `<div class="stat"><label>${esc(label)}</label><span class="stat-icon">${icon}</span><strong>${esc(n)}</strong><small>${esc(note)}</small></div>`,
    )
    .join("");
  $("team").innerHTML = d.profiles
    .map(
      (p) =>
        `<div class="team-item" title="${esc(`gateway 보고 시각: ${when(p.updated_at)}`)}"><span class="dot ${p.alive ? "on" : ""}"></span>${esc(p.profile === "david" ? "David / Hermes" : p.profile)}<small>${p.alive ? (p.active_agents ? `작업 ${p.active_agents}개` : "대기") : "확인 필요"}</small></div>`,
    )
    .join("");
  window.sharedOffice.render(d.rooms, d.rewards);
  $("recent").innerHTML =
    d.recent
      .slice(0, 7)
      .map(
        (s, i) =>
          `<button class="activity-item" data-recent="${i}"><span class="activity-symbol">${esc(roomIcon(s.room))}</span><span class="activity-text"><strong>${esc(roomName(s.room))}</strong><p>${esc(s.title)}</p><time>${when(s.started_at)} · ${s.ended_at ? "세션 종료" : "종료 미기록"}</time></span></button>`,
      )
      .join("") || '<div class="empty">아직 저장된 활동이 없습니다.</div>';
  document
    .querySelectorAll("[data-recent]")
    .forEach(
      (b) =>
        (b.onclick = () => openSession(d.recent[Number(b.dataset.recent)])),
    );
  $("schedule-list").innerHTML = d.jobs
    .map(
      (j) =>
        `<article class="schedule-card"><span class="tag">${esc(roomName(j.room))} · ${esc(j.profile)}</span><h3>${esc(j.name)}</h3><dl><dt>스케줄</dt><dd>${esc(j.schedule_display)}</dd><dt>다음 실행</dt><dd>${j.enabled ? when(j.next_run_at) : "비활성화"}</dd><dt>최근 실행</dt><dd>${when(j.last_run_at)}</dd><dt>실행 결과</dt><dd>${esc(j.last_status || "아직 실행 기록 없음")}</dd><dt>전송 대상</dt><dd>${esc(j.deliver)}</dd><dt>전송 오류</dt><dd class="${j.last_delivery_error ? "error-text" : ""}">${esc(j.last_delivery_error || "기록된 오류 없음 (수신 확인과 다름)")}</dd></dl>${j.last_error ? `<p class="error-text">${esc(j.last_error)}</p>` : ""}</article>`,
    )
    .join("");
}
async function refresh() {
  try {
    const d = await api("overview");
    const first = !state.overview;
    state.overview = d;
    if (first) {
      const profiles = d.profiles.map((p) => [
        p.profile,
        p.profile === "david" ? "David" : p.profile,
      ]);
      options("profile-filter", profiles, "모든 프로필");
      options("library-profile", profiles);
      options(
        "room-filter",
        d.rooms.map((r) => [r.id, r.title]),
        "모든 작업실",
      );
    }
    drawOverview();
    $("connection").textContent = "● 기록 연결됨";
    $("last-sync").textContent = `마지막 동기화 ${when(d.now)} · 10초 갱신`;
    $("error").hidden = !d.errors.length;
    if (d.errors.length) {
      $("error").textContent =
        "일부 기록을 읽지 못했습니다: " +
        d.errors.map((e) => e.profile + " (" + e.error + ")").join(", ");
    }
  } catch (e) {
    $("connection").textContent = "○ 연결 끊김";
    error(e);
  }
}
function clearFilters() {
  ["query", "profile-filter", "room-filter", "date-from", "date-to"].forEach(
    (id) => ($(id).value = ""),
  );
  state.sessionsOffset = 0;
}
async function loadSessions() {
  const request = ++state.request;
  try {
    const d = await api("sessions", {
      q: $("query").value,
      profile: $("profile-filter").value,
      room: $("room-filter").value,
      start: $("date-from").value,
      end: $("date-to").value,
      offset: state.sessionsOffset,
    });
    if (request !== state.request) return;
    $("result-count").textContent =
      `${d.total.toLocaleString()}개 세션${d.errors.length ? " · 일부 프로필 읽기 오류" : ""}`;
    $("sessions-list").innerHTML =
      d.items
        .map(
          (s, i) =>
            `<button class="record" data-session="${i}"><div class="record-meta"><span class="tag">${esc(roomName(s.room))}</span><span>${esc(s.profile)} · ${esc(s.source)}</span><span>${when(s.started_at)}</span><span>${esc(s.status)}</span></div><h3>${esc(s.title)}</h3><p class="preview">${esc(s.preview)}</p><div class="record-meta" style="margin-top:12px;margin-bottom:0"><span>${s.message_count} messages</span><span>${s.tool_call_count} tool calls</span><span>${s.ended_at ? Math.max(0, Math.round(s.ended_at - s.started_at)) + "s" : "소요 시간 미확정"}</span></div></button>`,
        )
        .join("") ||
      '<div class="empty">조건에 맞는 기록이 없습니다.<br>날짜나 작업실 필터를 변경해 보세요.</div>';
    document
      .querySelectorAll("[data-session]")
      .forEach(
        (b) =>
          (b.onclick = () => openSession(d.items[Number(b.dataset.session)])),
      );
    pager("sessions-pages", d, (offset) => {
      state.sessionsOffset = offset;
      loadSessions();
    });
  } catch (e) {
    error(e);
  }
}
function showDetail(title, meta) {
  $("detail-title").textContent = title;
  $("detail-meta").textContent = meta;
  $("detail-body").replaceChildren();
  $("detail-pages").replaceChildren();
  if (!$("detail").open) $("detail").showModal();
}
function readable(value) {
  if (typeof value !== "string") return JSON.stringify(value, null, 2);
  try {
    const parsed = JSON.parse(value);
    return JSON.stringify(parsed, null, 2);
  } catch {
    return value;
  }
}
async function openSession(session) {
  state.detail = { session, offset: 0, q: "" };
  showDetail(
    session.title,
    `${session.profile} / ${roomName(session.room)} / ${when(session.started_at)}`,
  );
  await loadMessages();
}
async function loadMessages() {
  const current = state.detail;
  if (!current) return;
  try {
    const d = await api("messages", {
      profile: current.session.profile,
      session: current.session.id,
      offset: current.offset,
      q: current.q,
      limit: 60,
    });
    if (current !== state.detail) return;
    $("detail-body").innerHTML =
      `<form id="message-search" class="detail-tools"><input id="message-query" type="search" placeholder="이 세션 안에서 검색" value="${esc(current.q)}" aria-label="세션 내 검색"><button class="primary">찾기</button></form><p class="muted">${esc(current.session.model || "모델 미기록")} · ${current.session.input_tokens || 0} input / ${current.session.output_tokens || 0} output tokens · 시스템 프롬프트와 내부 추론 제외</p>` +
      d.items
        .map(
          (m) =>
            `<article class="message ${esc(m.role)}"><header><b>${esc(m.tool_name || m.role)}</b><time>${when(m.timestamp)}</time></header><pre>${linkedText(readable(m.display_content || m.content || ""))}</pre>${m.display_content ? `<details><summary>삽입된 스킬을 포함한 전체 요청</summary><pre>${esc(m.content)}</pre></details>` : ""}${m.tool_calls ? `<details><summary>도구 호출 보기</summary><pre>${esc(readable(m.tool_calls))}</pre></details>` : ""}</article>`,
        )
        .join("") +
      (d.items.length
        ? ""
        : '<div class="empty">표시할 메시지가 없습니다.</div>');
    $("message-search").onsubmit = (e) => {
      e.preventDefault();
      state.detail = { ...current, q: $("message-query").value, offset: 0 };
      loadMessages();
    };
    pager("detail-pages", d, (offset) => {
      state.detail = { ...current, offset };
      loadMessages();
      $("detail").scrollTop = 0;
    });
  } catch (e) {
    $("detail-body").textContent = e.message;
  }
}
const libraryNotes = {
  workspace: "작업실별 노트의 이전 버전과 논문 읽기 목록 변경을 조회합니다.",
  learning:
    "공유 학습 데이터 · 배정된 과제와 실제 완료 피드백을 구분합니다. SRS는 보관된 카드 전체를 조회합니다.",
  papers:
    "공유 논문 카탈로그 · 제목과 초록 검색. 논문 원문은 제공된 링크로 열 수 있습니다.",
  memory:
    "선택한 프로필의 현재 MEMORY / USER 문서입니다. 과거 버전 이력은 포함하지 않습니다.",
  outputs:
    "선택한 프로필에 남아 있는 cron 출력 파일입니다. 오래된 알림은 대화 & 작업 기록에서도 검색하세요.",
  lessons:
    "공유 영어 레슨 inbox의 Markdown / 텍스트 원문입니다. 음성 파일은 포함하지 않습니다.",
  logs: "선택한 프로필의 현재 및 회전된 비압축 gateway 로그. 최신 줄부터 표시하며 검색할 수 있습니다.",
};
document.querySelector(".brand").onclick = (e) => {
  e.preventDefault();
  view("office");
};
async function loadLibrary() {
  const request = ++state.libraryRequest;
  const kind = $("library-kind").value;
  $("library-note").textContent = libraryNotes[kind];
  $("library-profile").disabled = [
    "learning",
    "papers",
    "lessons",
    "workspace",
  ].includes(kind);
  try {
    const d = await api("library", {
      kind,
      profile: $("library-profile").value || "david",
      q: $("library-query").value,
      offset: state.libraryOffset,
    });
    if (request !== state.libraryRequest) return;
    $("library-count").textContent = `${d.total.toLocaleString()}개 기록`;
    $("library-list").innerHTML =
      d.items
        .map(
          (r, i) =>
            `<button class="record" data-library="${i}"><div class="record-meta"><span>${esc(r.date || (r.time ? when(r.time) : ""))}</span></div><h3>${esc(r.title)}</h3><p class="preview">${esc(r.content)}</p></button>`,
        )
        .join("") ||
      '<div class="empty">저장된 기록이 없거나 검색 결과가 없습니다.</div>';
    document.querySelectorAll("[data-library]").forEach(
      (b) =>
        (b.onclick = () => {
          const r = d.items[Number(b.dataset.library)];
          state.detail = null;
          showDetail(r.title, kind);
          const pre = document.createElement("pre");
          pre.className = "full-record";
          pre.textContent = r.content;
          $("detail-body").append(pre);
          if (r.url && /^https?:\/\//i.test(r.url)) {
            const a = document.createElement("a");
            a.href = r.url;
            a.textContent = "원문 열기 ↗";
            a.target = "_blank";
            a.rel = "noopener noreferrer";
            a.className = "inline-link";
            $("detail-body").append(a);
          }
          if (r.data) {
            const detail = document.createElement("details"),
              summary = document.createElement("summary"),
              raw = document.createElement("pre");
            summary.textContent = "카드 전체 기록";
            raw.className = "full-record";
            raw.textContent = JSON.stringify(r.data, null, 2);
            detail.append(summary, raw);
            $("detail-body").append(detail);
          }
        }),
    );
    pager("library-pages", d, (offset) => {
      state.libraryOffset = offset;
      loadLibrary();
    });
  } catch (e) {
    error(e);
  }
}
document
  .querySelectorAll("nav button")
  .forEach((b) => (b.onclick = () => view(b.dataset.view)));
$("all-history").onclick = () => view("sessions");
$("refresh").onclick = refresh;
$("search-form").onsubmit = (e) => {
  e.preventDefault();
  state.sessionsOffset = 0;
  loadSessions();
};
$("clear-search").onclick = () => {
  clearFilters();
  loadSessions();
};
$("library-form").onsubmit = (e) => {
  e.preventDefault();
  state.libraryOffset = 0;
  loadLibrary();
};
$("library-kind").onchange = () => {
  state.libraryOffset = 0;
  loadLibrary();
};
$("library-profile").onchange = () => {
  state.libraryOffset = 0;
  loadLibrary();
};
$("close-detail").onclick = () => {
  $("detail").close();
  state.detail = null;
};
$("detail").addEventListener("close", () => {
  state.detail = null;
});
function stopReplay() {
  if (state.replay) clearTimeout(state.replay.timer);
  state.replay = null;
  window.sharedOffice?.visibility();
  document
    .querySelectorAll(".replaying")
    .forEach((e) => e.classList.remove("replaying"));
  $("replay-stop").hidden = true;
  $("replay-start").disabled = false;
}
async function replay() {
  stopReplay();
  const date = $("replay-date").value;
  if (!date) return;
  const current = { items: [], index: 0, timer: null };
  state.replay = current;
  window.sharedOffice?.visibility();
  $("replay-start").disabled = true;
  $("replay-stop").hidden = false;
  $("replay-label").textContent = "기록을 불러오는 중…";
  try {
    let offset = 0;
    while (true) {
      const d = await api("sessions", {
        start: date,
        end: date,
        limit: 100,
        offset,
      });
      if (state.replay !== current) return;
      current.items.push(...d.items);
      offset += 100;
      if (offset >= d.total) break;
    }
    current.items.reverse();
    if (!current.items.length) {
      stopReplay();
      $("replay-label").textContent = "이 날짜에는 저장된 세션이 없습니다.";
      return;
    }
    function tick() {
      if (state.replay !== current) return;
      document
        .querySelectorAll(".replaying")
        .forEach((e) => e.classList.remove("replaying"));
      const session = current.items[current.index];
      document
        .querySelectorAll("[data-room]")
        .forEach((e) =>
          e.classList.toggle("replaying", e.dataset.room === session.room),
        );
      $("replay-label").textContent =
        `REPLAY ${current.index + 1}/${current.items.length} · ${when(session.started_at)} · ${roomName(session.room)}`;
      current.index++;
      if (current.index < current.items.length)
        current.timer = setTimeout(tick, 2200);
      else
        current.timer = setTimeout(() => {
          stopReplay();
          $("replay-label").textContent =
            `재생 완료 · ${current.items.length}개 세션 (실시간 상태 아님)`;
        }, 2200);
    }
    tick();
  } catch (e) {
    stopReplay();
    error(e);
  }
}
$("replay-date").value = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/Los_Angeles",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
}).format(new Date());
$("replay-start").onclick = replay;
$("replay-stop").onclick = () => {
  stopReplay();
  $("replay-label").textContent = "재생 중지";
};
function clock() {
  $("clock").textContent =
    new Intl.DateTimeFormat("en-US", {
      timeZone: "America/Los_Angeles",
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date()) + " · LA";
}
clock();
setInterval(clock, 30000);
document.addEventListener("DOMContentLoaded", () => {
  refresh().then(() => {
    const route = new URLSearchParams(location.hash.slice(1).split("?")[1] || "");
    const name = location.hash.slice(1).split("?")[0] || "office";
    if (name === "workbench")
      openWorkbench(route.get("room") || localRead("hermes-last-room", "hq"), "replace");
    else view(name, "replace");
  });
});
window.addEventListener("popstate", () => {
  const route = new URLSearchParams(location.hash.slice(1).split("?")[1] || "");
  const name = location.hash.slice(1).split("?")[0] || "office";
  if (name === "workbench")
    openWorkbench(route.get("room") || localRead("hermes-last-room", "hq"), "none");
  else view(name, "none");
});
setInterval(() => {
  if (!document.hidden && !state.replay) refresh();
}, 10000);
