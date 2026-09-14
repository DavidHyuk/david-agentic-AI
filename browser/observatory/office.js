// Author: David Choi. Purpose: a persistent shared office and character conversations.
"use strict";
window.sharedOffice = (() => {
  // Coordinates are feet positions on a 1000 x 620 floor. All routes pass
  // through the open aisle; furniture stays outside that aisle.
  const homes = {
    papers: [145, 265], interview: [365, 265], coding: [625, 265],
    design: [855, 265], english: [185, 490], hq: [495, 420], podcast: [735, 455],
  };
  const spots = [
    {point: [185, 430], label: "커피 한 잔의 여유", icon: "☕"},
    {point: [320, 455], label: "라운지에서 쉬는 중", icon: "…"},
    {point: [690, 400], label: "동료에게 인사하는 중", icon: "♡"},
    {point: [895, 360], label: "창가에서 생각하는 중", icon: "✦"},
  ];
  // Scripted small talk is decorative, never a model call or a work-status report.
  const ambientLines = {
    hq: ["필요하면 언제든 불러주세요.", "오늘의 흐름을 같이 정리해볼까요?", "천천히, 하나씩 해도 괜찮아요."],
    papers: ["흥미로운 논문을 같이 찾아볼까요?", "논문의 아이디어를 면접 답변으로 연결해봐요.", "초록부터 같이 읽어볼까요?"],
    interview: ["답을 소리 내어 말해볼까요?", "좋아요. 근거를 한 단계 더 붙여보죠.", "트레이드오프도 함께 설명해보세요."],
    coding: ["힌트 하나만 드릴까요?", "경계 조건부터 떠올려봐요.", "복잡도도 잊지 마세요!"],
    design: ["실패 시나리오부터 살펴볼까요?", "병목은 어디에서 생길까요?", "요구사항을 먼저 정리해보죠."],
    english: ["오늘 한 문장 말해볼까요?", "자연스럽게 다시 표현해봐요.", "틀려도 괜찮아요. 제가 도와드릴게요."],
    podcast: ["이 표현, 귀에 익혀봐요!", "짧게 따라 말해볼까요?", "오늘은 어떤 이야기를 들어볼까요?"],
  };
  const actors = new Map();
  const conversations = new Map();
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  let selected = null, paused = localRead("office-paused", false);
  let previous = 0, frame = 0, roomData = [], historyRequest = 0;
  let talkTimer = 0, speakingRoom = null;
  const conversation = (room) => {
    if (!conversations.has(room))
      conversations.set(room, {history: [], busy: false, available: false, loaded: false, error: ""});
    return conversations.get(room);
  };
  const sprite = (room, className = "") => {
    const source = room === "english"
      ? "assets/ellie-english-tutor.png"
      : "assets/hermes-agent-cast.png";
    return `<span class="cast-art ${className}" data-character="${room}" style="--cast-index:${officeCast[room].index}" aria-hidden="true"><img src="${source}" alt="" /></span>`;
  };

  function build() {
    $("rooms").innerHTML = `<div class="office-viewport" tabindex="0" aria-label="큰 사무실. 작은 화면에서는 좌우로 스크롤할 수 있습니다.">
      <div class="shared-floor">
        <div class="back-wall" aria-hidden="true"><div class="wide-window"></div><span>HERMES<br><small>IDEAS LIVE HERE</small></span><div class="wide-window"></div></div>
        <div class="floor-sign">THE STUDIO <span>↙ LOUNGE · COFFEE ↗</span></div>
        <div class="furniture desk-island desk-one"><i></i><i></i><span>RESEARCH / INTERVIEW</span></div>
        <div class="furniture desk-island desk-two"><i></i><i></i><span>CODE / DESIGN</span></div>
        <div class="furniture coffee-bar"><b>☕</b><span>COFFEE CLUB</span><i></i></div>
        <div class="furniture sofa"><span>TAKE A BREATH</span><i></i><i></i><i></i></div>
        <div class="furniture meeting-table"><i></i><span>✦</span><i></i></div>
        <div class="furniture sound-desk"><span>ON AIR</span><b>▥ ▥ ▥</b></div>
        <div class="furniture green-plant plant-one">✺</div><div class="furniture green-plant plant-two">✺</div>
        <div class="walking-floor" id="walking-floor"></div>
        <div class="shared-floor-caption">일상 연출 <span>캐릭터를 클릭해 이야기해 보세요</span></div>
      </div></div>
      <section id="office-conversation" class="office-conversation" aria-label="캐릭터 대화" hidden>
        <div class="conversation-portrait" id="conversation-portrait"></div>
        <div class="conversation-main">
          <div class="conversation-heading"><div><small id="conversation-role"></small><h2 id="conversation-name"></h2></div><button id="conversation-close" class="outline" aria-label="대화 패널 닫기">×</button></div>
          <p id="conversation-context"></p>
          <div class="conversation-history" id="conversation-history" role="log" aria-label="대화 기록"></div>
          <div id="conversation-suggestions"></div>
          <form id="office-chat-form"><label class="sr-only" for="office-message">캐릭터에게 할 말</label><textarea id="office-message" maxlength="4000" rows="2" required placeholder="편하게 이야기해 보세요…"></textarea><button class="primary" id="office-send">보내기</button></form>
          <div class="conversation-footer"><span id="office-chat-status" role="status"></span><button class="text-button" id="conversation-reload">기록 새로고침</button><button class="text-button" id="conversation-workbench">작업실 열기 ↗</button></div>
          <small class="conversation-note">사무실 대화는 웹에 저장됩니다 · Telegram 전송 없음</small>
        </div>
      </section>`;
    $("conversation-close").onclick = close;
    $("conversation-workbench").onclick = () => { if (selected) openWorkbench(selected); };
    $("conversation-reload").onclick = () => { if (selected) loadHistory(selected); };
    $("office-chat-form").onsubmit = send;
    $("office-message").oninput = () => { if (selected) localWrite("office-draft:" + selected, $("office-message").value); };
    $("office-conversation").onkeydown = (event) => { if (event.key === "Escape") close(); };
    $("office-motion").onclick = () => {
      paused = !paused;
      localWrite("office-paused", paused);
      visibility();
    };
  }

  function render(rooms) {
    roomData = rooms;
    if (!$("walking-floor")) build();
    for (const room of rooms) {
      if (!officeCast[room.id]) continue;
      let actor = actors.get(room.id);
      if (!actor) {
        const button = document.createElement("button");
        button.className = "walking-agent";
        button.dataset.room = room.id;
        button.innerHTML = `<span class="walk-bubble" aria-hidden="true"></span>${sprite(room.id)}<span class="walk-name">${officeCast[room.id].name} <i></i></span>`;
        button.onclick = () => select(room.id);
        $("walking-floor").append(button);
        actor = {node: button, x: homes[room.id][0], y: homes[room.id][1], route: [],
          wait: 15 + officeCast[room.id].index * 17 + Math.random() * 8,
          home: true, mode: "ambient"};
        actors.set(room.id, actor);
      }
      const mode = room.presence?.mode || "ambient";
      if (actor.mode !== mode) {
        actor.route = [];
        if (mode !== "ambient") route(actor, homes[room.id]);
      }
      actor.mode = mode;
      actor.node.dataset.presence = mode;
      actor.node.title = `${room.title} · ${room.presence?.label || "일상 연출"}`;
      actor.node.setAttribute("aria-label", `${officeCast[room.id].name}와 대화하기 · ${room.title}`);
      paint(actor);
    }
    // Stable actor nodes retain positions, keyboard focus and animation on polling.
    if (!$("office-roster").children.length) {
      $("office-roster").innerHTML = rooms.map(room =>
        `<button class="outline" data-cast="${esc(room.id)}">${esc(officeCast[room.id]?.name || room.title)}<small>${esc(room.subtitle)}</small></button>`).join("");
      $("office-roster").querySelectorAll("[data-cast]").forEach(button => {
        button.onclick = () => officeCast[button.dataset.cast] ? select(button.dataset.cast) : openWorkbench(button.dataset.cast);
      });
    }
    visibility();
  }
  function route(actor, target) {
    actor.route = [[actor.x, 345], [target[0], 345], target];
  }
  function paint(actor) {
    actor.node.style.left = actor.x / 10 + "%";
    actor.node.style.top = actor.y / 6.2 + "%";
    actor.node.style.zIndex = Math.round(actor.y);
  }
  function tick(now) {
    const delta = Math.min((now - previous) / 1000 || 0, 0.05);
    previous = now;
    for (const [room, actor] of actors) {
      const held = selected === room || Boolean(state.replay) || actor.node.matches(":hover, :focus-visible");
      if (!held && actor.route.length) {
        const [x, y] = actor.route[0], dx = x - actor.x, dy = y - actor.y;
        const distance = Math.hypot(dx, dy), step = delta * 45;
        if (distance <= step) {
          actor.x = x; actor.y = y; actor.route.shift();
        } else { actor.x += dx / distance * step; actor.y += dy / distance * step; }
      } else if (!held && actor.mode === "ambient") {
        actor.wait -= delta;
        if (actor.wait <= 0) {
          const spot = spots[(officeCast[room].index + Math.floor(Math.random() * spots.length)) % spots.length];
          const index = officeCast[room].index;
          const destination = [spot.point[0] + (index - 3) * 9, spot.point[1] - (index % 3) * 8];
          route(actor, actor.home ? destination : homes[room]);
          actor.home = !actor.home;
          actor.wait = 60 + Math.random() * 80;
        }
      }
      actor.node.classList.toggle("is-walking", !held && actor.route.length > 0);
      actor.node.classList.toggle("is-selected", selected === room);
      paint(actor);
    }
    frame = requestAnimationFrame(tick);
  }
  function visibility() {
    cancelAnimationFrame(frame);
    const stop = paused || reduced.matches || document.hidden || state.view !== "office";
    document.querySelector(".shared-floor")?.classList.toggle("motion-paused", stop);
    if ($("office-motion")) {
      $("office-motion").textContent = paused ? "움직임 재개" : "움직임 멈추기";
      $("office-motion").setAttribute("aria-pressed", String(paused));
    }
    previous = 0;
    if (!stop) frame = requestAnimationFrame(tick);
    if (document.hidden || state.view !== "office" || state.replay) stopTalk();
    else scheduleTalk();
  }
  function stopTalk() {
    clearTimeout(talkTimer);
    talkTimer = 0;
    if (speakingRoom) actors.get(speakingRoom)?.node.classList.remove("is-speaking");
    speakingRoom = null;
  }
  function speak(room, text, duration = 7200) {
    if (speakingRoom) actors.get(speakingRoom)?.node.classList.remove("is-speaking");
    const actor = actors.get(room);
    if (!actor) return;
    speakingRoom = room;
    actor.node.querySelector(".walk-bubble").textContent = text;
    actor.node.classList.add("is-speaking");
    clearTimeout(talkTimer);
    talkTimer = setTimeout(() => {
      actor.node.classList.remove("is-speaking");
      speakingRoom = null;
      talkTimer = 0;
      scheduleTalk();
    }, duration);
  }
  function scheduleTalk() {
    if (talkTimer || document.hidden || state.view !== "office" || state.replay || !actors.size) return;
    talkTimer = setTimeout(() => {
      talkTimer = 0;
      if (document.hidden || state.view !== "office" || state.replay) return;
      const rooms = [...actors.keys()].filter((room) => room !== selected);
      if (!rooms.length) return;
      const room = rooms[Math.floor(Math.random() * rooms.length)];
      const lines = ambientLines[room];
      speak(room, lines[Math.floor(Math.random() * lines.length)]);
    }, 11000 + Math.random() * 15000);
  }
  function close() {
    const last = selected;
    selected = null;
    historyRequest++;
    $("office-conversation").hidden = true;
    actors.get(last)?.node.classList.remove("is-selected");
    if (state.view === "workbench") $("bench-talk")?.focus({preventScroll: true});
    else actors.get(last)?.node.focus({preventScroll: true});
  }
  function select(room, insideWorkbench = false) {
    if (!officeCast[room]) return;
    selected = room;
    if (state.replay) stopReplay();
    if (!insideWorkbench) view("office");
    (insideWorkbench ? $("bench-character") : $("rooms")).append($("office-conversation"));
    const cast = officeCast[room], actor = actors.get(room);
    actor?.node.classList.add("is-selected");
    speak(room, "불러주셨나요?", 4200);
    if (!insideWorkbench) actor?.node.scrollIntoView({block: "nearest", inline: "center", behavior: "smooth"});
    $("conversation-portrait").innerHTML = sprite(room, "portrait-art");
    $("conversation-role").textContent = cast.role;
    $("conversation-name").textContent = cast.name;
    const data = roomData.find(item => item.id === room), job = data && nextRoomJob(data);
    $("conversation-context").textContent = `${data?.title || room} · ${job ? "다음 일정 " + when(job.next_run_at) : "함께 이야기할 준비가 됐어요"}`;
    $("office-conversation").hidden = false;
    $("office-message").value = localRead("office-draft:" + room, "");
    $("office-message").placeholder = cast.name + "에게 이야기해 보세요…";
    $("conversation-suggestions").innerHTML = ["어떤 일을 도와줄 수 있어?", "오늘 같이 뭘 해볼까?"].map(text =>
      `<button class="outline">${text}</button>`).join("");
    $("conversation-suggestions").querySelectorAll("button").forEach(button => {
      button.onclick = () => { $("office-message").value = button.textContent; $("office-message").dispatchEvent(new Event("input")); $("office-message").focus(); };
    });
    showConversation(room);
    loadHistory(room);
    $("office-message").focus({preventScroll: true});
    $("office-conversation").scrollIntoView({block: "nearest", behavior: reduced.matches ? "instant" : "smooth"});
  }
  function showConversation(room) {
    if (room !== selected) return;
    const chat = conversation(room);
    $("conversation-history").innerHTML = chat.history.length ?
      chat.history.map(item => `<div class="office-message ${item.role === "user" ? "from-user" : "from-agent"}"><b>${item.role === "user" ? "David" : officeCast[room].name}</b><p>${linkedText(item.content)}</p></div>`).join("") :
      '<p class="conversation-empty">이곳에서 나눈 이야기가 이어집니다. 먼저 인사해 보세요.</p>';
    $("office-chat-status").textContent = chat.busy ? "답변을 생각하고 있어요. 로컬 모델은 몇 분 걸릴 수 있습니다…" :
      chat.error || (!chat.loaded ? "대화를 불러오는 중…" : !chat.available ? "대화 연결을 준비하지 못했습니다." : "");
    $("office-send").disabled = chat.busy || !chat.loaded || !chat.available;
    $("conversation-portrait").classList.toggle("thinking", chat.busy);
    $("conversation-history").scrollTop = $("conversation-history").scrollHeight;
  }
  async function loadHistory(room) {
    const request = ++historyRequest, chat = conversation(room);
    try {
      const result = await api("office-chat", {room});
      if (request !== historyRequest || chat.busy) return;
      chat.history = result.history; chat.available = result.available; chat.loaded = true;
      chat.error = result.busy ? "이 캐릭터가 답변 중입니다. 잠시 후 기록을 새로고침해 주세요." : "";
      showConversation(room);
    } catch (err) {
      if (request !== historyRequest) return;
      chat.error = err.message; showConversation(room);
    }
  }
  async function send(event) {
    event.preventDefault();
    const room = selected, chat = conversation(room), message = $("office-message").value.trim();
    if (!message || chat.busy || !chat.available) return;
    historyRequest++;
    chat.busy = true; chat.error = "";
    chat.history.push({role: "user", content: message});
    showConversation(room);
    try {
      const response = await fetch("api/action", {
        method: "POST", headers: {"Content-Type": "application/json", "X-Hermes-Action": "1"},
        body: JSON.stringify({action: "office_chat", room, message}),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "답변을 확인하지 못했습니다.");
      chat.history.push({role: "assistant", content: result.response});
      if (String(localRead("office-draft:" + room, "")).trim() === message)
        localWrite("office-draft:" + room, null);
      if (selected === room && $("office-message").value.trim() === message) $("office-message").value = "";
    } catch (err) {
      chat.error = err.message + " 기록을 새로고침해 저장 여부를 확인해 주세요.";
    } finally { chat.busy = false; showConversation(room); }
  }
  function workbench(room) {
    const target = $("bench-character");
    if ($("office-conversation")) {
      $("rooms").append($("office-conversation"));
      $("office-conversation").hidden = true;
      selected = null;
      historyRequest++;
    }
    if (!officeCast[room]) { target.replaceChildren(); return; }
    const cast = officeCast[room];
    target.innerHTML = `<div class="bench-companion">${sprite(room)}<div><small>${esc(cast.role)}</small><h2>${esc(cast.name)}와 함께하는 작업실</h2><p>자료를 함께 살펴보고, 이곳에서 이야기를 이어가세요.</p><button class="primary" id="bench-talk">대화 이어가기</button></div></div>`;
    $("bench-talk").onclick = () => select(room, true);
  }
  document.addEventListener("visibilitychange", visibility);
  reduced.addEventListener("change", visibility);
  return {render, visibility, select, workbench};
})();
