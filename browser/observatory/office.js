// Author: David Choi. Purpose: a persistent shared office and character conversations.
"use strict";
window.sharedOffice = (() => {
  // Coordinates are feet positions on a 1000 x 620 floor. All routes pass
  // through the open aisle; furniture stays outside that aisle.
  const homes = {
    papers: [145, 300], interview: [365, 300], coding: [625, 300],
    design: [855, 300], english: [275, 490], hq: [495, 420], podcast: [815, 480],
  };
  // Each role follows a small, deterministic work routine instead of choosing
  // arbitrary floor coordinates. Points are feet positions on the shared floor.
  const routines = {
    papers: [
      {point: homes.papers, label: "논문 정리"},
      {point: [145, 350], label: "자료 근거 확인"},
      {point: [430, 400], label: "연구 메모 공유"},
    ],
    interview: [
      {point: homes.interview, label: "면접 질문 정리"},
      {point: [410, 350], label: "답변 구조화"},
      {point: [570, 400], label: "모의 답변 검토"},
    ],
    coding: [
      {point: homes.coding, label: "문제 분석"},
      {point: [690, 350], label: "코드 리뷰"},
      {point: [520, 400], label: "풀이 검토"},
    ],
    design: [
      {point: homes.design, label: "다이어그램 작성"},
      {point: [850, 350], label: "병목 점검"},
      {point: [680, 400], label: "설계 리뷰"},
    ],
    english: [
      {point: homes.english, label: "예문 정리"},
      {point: [335, 440], label: "발음 연습"},
      {point: [625, 475], label: "표현 맞추기"},
    ],
    hq: [
      {point: homes.hq, label: "전체 흐름 정리"},
      {point: [260, 350], label: "연구 팀 확인"},
      {point: [745, 350], label: "엔지니어링 팀 확인"},
      {point: [180, 410], label: "잠깐 재정비"},
    ],
    podcast: [
      {point: homes.podcast, label: "레슨 편집"},
      {point: [770, 440], label: "셰도잉 점검"},
      {point: [875, 455], label: "녹음 확인"},
    ],
  };
  // Hermes is the only ambient walker. His visits make leadership presence
  // legible without turning every idle specialist into background motion.
  const leaderVisits = [
    {room: "papers", point: [245, 345], label: "Iris와 연구 이야기"},
    {room: "interview", point: [455, 345], label: "Theo와 잠깐 이야기"},
    {room: "coding", point: [555, 345], label: "Jun과 진행 확인"},
    {room: "design", point: [765, 345], label: "Mina와 설계 이야기"},
    {room: "english", point: [335, 440], label: "Ellie와 잠깐 이야기"},
    {room: "podcast", point: [765, 440], label: "Rina와 잠깐 이야기"},
    {room: "hq", point: homes.hq, label: "전체 흐름 정리"},
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
  const dialogueScenes = [
    ["papers", "interview", "Theo, 논문 근거를 답변에 넣어볼까요?", "좋아요, 사례까지 이어서 말해볼게요."],
    ["coding", "design", "Mina, 이 구조의 병목은 어디일까요?", "트래픽부터 같이 계산해보죠."],
    ["english", "podcast", "Rina, 오늘 표현 하나 골라줄래요?", "Ellie, 셰도잉하기 좋은 걸로 찾아볼게요!"],
    ["hq", "papers", "Iris, 요즘 어떤 주제가 눈에 띄나요?", "추론과 에이전트 흐름을 보고 있어요."],
    ["interview", "design", "Mina, 이 답변의 약점도 봐줄래요?", "실패 시나리오를 하나 더 붙여봐요."],
  ];
  const leaderSmallTalk = {
    papers: ["Iris, 커피는 챙겼어요?", "네, 논문보다 따뜻해요."],
    interview: ["Theo, 오늘 질문이 너무 어렵진 않죠?", "좋은 질문은 조금 어려워야죠."],
    coding: ["Jun, 키보드 소리만 들려도 든든하네요.", "버그도 그 소리를 들으면 도망가면 좋겠어요."],
    design: ["Mina, 화이트보드 자리가 아직 남았나요?", "좋은 생각 하나만 가져오시면요."],
    english: ["Ellie, 오늘도 한 문장 배워볼까요?", "물론이죠. 부담 없이 시작해요."],
    podcast: ["Rina, 음악은 너무 크게 틀지 말아줘요.", "좋은 부분만 살짝 들려드릴게요!"],
  };
  const jobLabels = {
    "papers-digest": "연구 다이제스트", "interview-prep": "MLE 면접 드릴",
    "coding-coach": "코딩 훈련", "system-design-coach": "시스템 디자인 훈련",
    "weekly-review": "주간 리뷰", "english-intake": "영어 피드백",
    "english-drill": "영어 복습", "english-weekly-review": "영어 주간 리뷰",
    "english-podcast-daily": "팟캐스트 영어", "career-rewards-daily": "오늘의 보상",
  };
  const rewardRooms = {coding: "coding", design: "design", english: "english", paper: "papers", weekly: "hq", combo: "hq"};
  const actors = new Map();
  const conversations = new Map();
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  let selected = null, paused = localRead("office-paused", false);
  let officeZoom = Math.min(1.4, Math.max(0.6, Number(localRead("office-zoom", 1)) || 1));
  let previous = 0, frame = 0, roomData = [], historyRequest = 0;
  let talkTimer = 0, replyTimer = 0, followupTimer = 0, closingTimer = 0;
  let talkTurn = 0, noticeTurn = 0;
  let dialogueTurn = 0, ambientTurn = 0;
  const speakingRooms = new Set();
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
        <div class="reward-hud" id="reward-hud" hidden><span class="reward-wallet">$<b id="reward-balance">0</b></span><div><small id="reward-streak">TODAY'S MISSION</small><strong id="reward-offer">첫 보상을 준비 중</strong><i><em id="reward-progress"></em></i></div></div>
        <div class="reward-shower" id="reward-shower" aria-hidden="true"></div>
        <div class="floor-sign">THE STUDIO <span>↙ LOUNGE · COFFEE ↗</span></div>
        <div class="wall-board research-board" aria-hidden="true"><b>RESEARCH PULSE</b><i></i><i></i><i></i></div>
        <div class="wall-board systems-board" aria-hidden="true"><b>SYSTEM MAP</b><i></i><i></i><i></i></div>
        <div class="studio-plaque research-plaque"><small>IRIS · THEO</small><b>RESEARCH / INTERVIEW</b><span>PAPERS · ANSWERS · EVIDENCE</span></div>
        <div class="studio-plaque engineering-plaque"><small>JUN · MINA</small><b>CODE / SYSTEM DESIGN</b><span>BUILD · REVIEW · ARCHITECTURE</span></div>
        <div class="ceiling-light light-one" aria-hidden="true"></div><div class="ceiling-light light-two" aria-hidden="true"></div>
        <div class="floor-runner" aria-hidden="true"><span>HERMES COMMONS</span></div>
        <div class="zone-rug collaboration-zone" aria-hidden="true"><span>COLLABORATION COMMONS</span></div>
        <div class="furniture desk-island desk-one"><i></i><i></i><em>FIELD NOTES · QUESTION LAB</em><div class="desk-lamp lamp-left" aria-hidden="true"></div><div class="desk-lamp lamp-right" aria-hidden="true"></div><div class="zone-actions" id="research-actions"></div></div>
        <div class="furniture desk-island desk-two"><i></i><i></i><em>BUILD · REVIEW · SYSTEM MAP</em><div class="desk-lamp lamp-left" aria-hidden="true"></div><div class="desk-lamp lamp-right" aria-hidden="true"></div><div class="zone-actions" id="engineering-actions"></div></div>
        <div class="furniture archive-shelf" aria-hidden="true"><b>FIELD NOTES</b><i></i><i></i><i></i><span>ARCHIVE</span></div>
        <div class="furniture review-board" aria-hidden="true"><b>REVIEW</b><i></i><i></i><span></span></div>
        <div class="furniture coffee-bar"><b>☕</b><span><strong>COFFEE CLUB</strong><small>ESPRESSO BAR</small></span><i></i><div class="zone-actions" id="english-actions"></div></div>
        <div class="furniture sofa"><span><strong>ELLIE · ENGLISH LOUNGE</strong><small>TAKE A BREATH · SPEAK EASY</small></span><i></i><i></i><i></i><b>✦</b></div>
        <div class="furniture meeting-table"><i></i><span>✦</span><i></i><div class="zone-actions" id="hq-actions"></div></div>
        <div class="furniture sound-desk"><span><strong>RINA · ON AIR</strong><small>LISTENING STUDIO</small></span><b>▥ ▥ ▥</b><i></i><div class="zone-actions" id="podcast-actions"></div></div>
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
    $("office-message").onkeydown = (event) => {
      if (event.key === "Enter" && event.shiftKey && !event.isComposing) {
        event.preventDefault();
        $("office-chat-form").requestSubmit();
      }
    };
    $("office-conversation").onkeydown = (event) => { if (event.key === "Escape") close(); };
    $("office-motion").onclick = () => {
      paused = !paused;
      localWrite("office-paused", paused);
      visibility();
    };
    $("office-zoom-out").onclick = () => setOfficeZoom(officeZoom - 0.1);
    $("office-zoom-in").onclick = () => setOfficeZoom(officeZoom + 0.1);
    const viewport = document.querySelector(".office-viewport");
    let pinchDistance = 0, pinchZoom = officeZoom;
    viewport.addEventListener("touchstart", (event) => {
      if (event.touches.length !== 2) return;
      pinchDistance = Math.hypot(event.touches[0].clientX - event.touches[1].clientX,
        event.touches[0].clientY - event.touches[1].clientY);
      pinchZoom = officeZoom;
    }, {passive: true});
    viewport.addEventListener("touchmove", (event) => {
      if (event.touches.length !== 2 || !pinchDistance) return;
      event.preventDefault();
      const distance = Math.hypot(event.touches[0].clientX - event.touches[1].clientX,
        event.touches[0].clientY - event.touches[1].clientY);
      const center = (event.touches[0].clientX + event.touches[1].clientX) / 2 - viewport.getBoundingClientRect().left;
      setOfficeZoom(pinchZoom * distance / pinchDistance, center, false);
    }, {passive: false});
    const finishPinch = () => {
      if (pinchDistance) localWrite("office-zoom", officeZoom);
      pinchDistance = 0;
    };
    viewport.addEventListener("touchend", finishPinch, {passive: true});
    viewport.addEventListener("touchcancel", finishPinch, {passive: true});
    setOfficeZoom(officeZoom, null, false);
  }

  function setOfficeZoom(value, focusX = null, persist = true) {
    const viewport = document.querySelector(".office-viewport"), floor = document.querySelector(".shared-floor");
    if (!viewport || !floor) return;
    const previousZoom = officeZoom;
    officeZoom = Math.round(Math.min(1.4, Math.max(0.6, value)) * 20) / 20;
    const center = focusX ?? viewport.clientWidth / 2;
    const contentPoint = (viewport.scrollLeft + center) / previousZoom;
    floor.style.zoom = String(officeZoom);
    viewport.scrollLeft = Math.max(0, contentPoint * officeZoom - center);
    $("office-zoom-label").textContent = Math.round(officeZoom * 100) + "%";
    $("office-zoom-out").disabled = officeZoom <= 0.6;
    $("office-zoom-in").disabled = officeZoom >= 1.4;
    if (persist) localWrite("office-zoom", officeZoom);
  }

  function render(rooms, rewards = null) {
    roomData = rooms;
    if (!$("walking-floor")) build();
    for (const room of rooms) {
      if (!officeCast[room.id]) continue;
      let actor = actors.get(room.id);
      if (!actor) {
        const button = document.createElement("button");
        button.className = "walking-agent";
        button.dataset.room = room.id;
        button.innerHTML = `<span class="walk-bubble" aria-hidden="true"></span>${sprite(room.id)}<span class="walk-name"><b>${officeCast[room.id].name}</b><small class="walk-purpose"></small><i></i></span>`;
        button.onclick = () => select(room.id);
        button.addEventListener("pointerenter", () => showHoverNotice(room.id));
        button.addEventListener("pointerleave", () => button.classList.remove("is-hovering"));
        $("walking-floor").append(button);
        actor = {node: button, x: homes[room.id][0], y: homes[room.id][1], route: [],
          wait: room.id === "hq" ? 55 : Infinity, routineIndex: 0, visitRoom: null,
          pendingPurpose: "", purpose: routines[room.id][0].label, mode: "ambient"};
        actors.set(room.id, actor);
        setPurpose(actor, actor.purpose);
      }
      const mode = room.presence?.mode || "ambient";
      if (actor.mode !== mode) {
        actor.route = [];
        actor.visitRoom = null;
        setPurpose(actor, mode !== "ambient"
          ? room.presence?.label || "실제 작업 확인"
          : routines[room.id][0].label);
      }
      actor.mode = mode;
      actor.node.dataset.presence = mode;
      actor.node.title = `${room.title} · ${room.presence?.label || "일상 연출"} · ${actor.purpose}`;
      actor.node.setAttribute("aria-label", `${officeCast[room.id].name}와 대화하기 · ${room.title}`);
      paint(actor);
    }
    // Stable actor nodes retain positions, keyboard focus and animation on polling.
    renderUserActions(rooms);
    renderRewards(rewards);
    $("office-roster").innerHTML = rooms.map(room => {
      const action = room.action || {title: "다음 행동", detail: "작업실 열기"};
      return `<button class="outline" data-cast="${esc(room.id)}"><b>${esc(officeCast[room.id]?.name || room.title)}</b><small>${esc(room.subtitle)}</small><span class="roster-action"><strong>${esc(action.title)}</strong><em>${esc(action.detail)}</em></span></button>`;
    }).join("");
    $("office-roster").querySelectorAll("[data-cast]").forEach(button => {
      button.onclick = () => officeCast[button.dataset.cast] ? select(button.dataset.cast) : openWorkbench(button.dataset.cast);
    });
    visibility();
  }
  function renderRewards(rewards) {
    const hud = $("reward-hud");
    if (!hud || !rewards || rewards.available === false) {
      if (hud) hud.hidden = true;
      return;
    }
    hud.hidden = false;
    const balance = Number(rewards.balance || 0);
    $("reward-balance").textContent = balance.toLocaleString();
    $("reward-streak").textContent = `CAREER CASH · 🔥 ${Number(rewards.streak || 0)} DAY`;
    $("reward-offer").textContent = rewards.next_offer
      ? `${rewards.next_offer.label} · $${rewards.next_offer.remaining} 남음`
      : "ALL VIRTUAL OFFERS UNLOCKED";
    const threshold = Number(rewards.next_offer?.threshold || balance || 1);
    $("reward-progress").style.width = `${Math.min(100, balance / threshold * 100)}%`;
    const previousBalance = Number(localRead("career-cash-seen", 0) || 0);
    if (balance > previousBalance) celebrateReward(rewards, balance - previousBalance);
    localWrite("career-cash-seen", balance);
  }
  function celebrateReward(rewards, earned) {
    const latest = (rewards.recent || []).find(item => item.kind === "activity") || rewards.recent?.[0];
    const room = rewardRooms[latest?.category] || "hq";
    const actor = actors.get(room), leader = actors.get("hq");
    const shower = $("reward-shower"), floor = document.querySelector(".shared-floor");
    if (shower) shower.innerHTML = Array.from({length: 14}, (_, index) => `<i style="--coin:${index}">$</i>`).join("");
    floor?.classList.add("reward-party");
    actor?.node.classList.add("rewarding");
    stopTalk();
    showBubble(room, `미션 완료! Career Cash +$${earned} 🎉`, "reward");
    if (room !== "hq") replyTimer = setTimeout(() => showBubble("hq", `잘했어요 David! 잔액 $${Number(rewards.balance).toLocaleString()} · 다음 오퍼를 향해 가죠.`, "reward"), 1800);
    finishTalk(8500);
    setTimeout(() => {
      floor?.classList.remove("reward-party");
      actor?.node.classList.remove("rewarding");
      if (shower) shower.replaceChildren();
    }, 8200);
  }
  function renderUserActions(rooms) {
    const byId = new Map(rooms.map(room => [room.id, room]));
    const slots = {
      "research-actions": ["papers", "interview"],
      "engineering-actions": ["coding", "design"],
      "english-actions": ["english"],
      "hq-actions": ["hq"],
      "podcast-actions": ["podcast"],
    };
    for (const [slotId, roomIds] of Object.entries(slots)) {
      const slot = $(slotId);
      if (!slot) continue;
      slot.innerHTML = roomIds.map((roomId) => {
        const room = byId.get(roomId), action = room?.action || {title: "다음 행동", detail: "작업실 열기"};
        return `<button data-action-room="${esc(roomId)}" title="${esc(room?.title || roomId)} 작업실 열기"><b>${esc(room?.icon || "✦")} ${esc(action.title)}</b><small>${esc(action.detail)}</small></button>`;
      }).join("");
      slot.querySelectorAll("[data-action-room]").forEach(button => {
        button.onclick = () => openWorkbench(button.dataset.actionRoom);
      });
    }
  }
  function setPurpose(actor, purpose) {
    actor.purpose = purpose;
    actor.node.querySelector(".walk-purpose").textContent = purpose;
  }
  function route(actor, target, purpose, visitRoom = null) {
    actor.route = [[actor.x, 345], [target[0], 345], target];
    actor.pendingPurpose = purpose;
    actor.visitRoom = visitRoom;
    setPurpose(actor, purpose + " · 이동 중");
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
          if (!actor.route.length && actor.pendingPurpose) {
            setPurpose(actor, actor.pendingPurpose);
            actor.pendingPurpose = "";
            const visitRoom = actor.visitRoom;
            actor.visitRoom = null;
            if (room === "hq" && visitRoom) startLeaderSmallTalk(visitRoom);
          }
        } else { actor.x += dx / distance * step; actor.y += dy / distance * step; }
      } else if (!held && room === "hq" && actor.mode === "ambient") {
        actor.wait -= delta;
        if (actor.wait <= 0) {
          const visit = leaderVisits[actor.routineIndex++ % leaderVisits.length];
          route(actor, visit.point, visit.label, visit.room === "hq" ? null : visit.room);
          actor.wait = 115 + (actor.routineIndex % 3) * 18;
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
      $("office-motion").textContent = paused ? "팀장 이동 재개" : "팀장 이동 멈추기";
      $("office-motion").setAttribute("aria-pressed", String(paused));
    }
    previous = 0;
    if (!stop) frame = requestAnimationFrame(tick);
    if (document.hidden || state.view !== "office" || state.replay) stopTalk();
    else scheduleTalk();
  }
  function stopTalk() {
    clearTimeout(talkTimer);
    clearTimeout(replyTimer);
    clearTimeout(followupTimer);
    clearTimeout(closingTimer);
    talkTimer = 0;
    replyTimer = 0;
    followupTimer = 0;
    closingTimer = 0;
    for (const room of speakingRooms) actors.get(room)?.node.classList.remove("is-speaking");
    speakingRooms.clear();
  }
  function showBubble(room, text, kind) {
    const actor = actors.get(room);
    if (!actor) return false;
    const bubble = actor.node.querySelector(".walk-bubble");
    bubble.textContent = text;
    bubble.dataset.kind = kind;
    actor.node.classList.add("is-speaking");
    speakingRooms.add(room);
    return true;
  }
  function finishTalk(duration) {
    talkTimer = setTimeout(() => {
      stopTalk();
      scheduleTalk();
    }, duration);
  }
  function speak(room, text, duration = 7200, kind = "ambient") {
    stopTalk();
    if (showBubble(room, text, kind)) finishTalk(duration);
  }
  function notificationLine(room) {
    const data = roomData.find((item) => item.id === room);
    if (data?.notice?.text) return `최근 알림 · ${data.notice.text}`;
    const job = data && nextRoomJob(data);
    if (job) return `다음 알림 · ${jobLabels[job.name] || job.name} ${when(job.next_run_at)}`;
    return "최근 알림 · 아직 새 소식은 없어요.";
  }
  function hoverNoticeLine(room) {
    const data = roomData.find((item) => item.id === room);
    const recent = data?.notice?.text || data?.latest?.title || "최근 기록이 아직 없어요.";
    const action = data?.action || {title: "다음 행동", detail: "작업실에서 확인하기"};
    return `최근 · ${recent}\nDavid 다음 · ${action.title} · ${action.detail}`;
  }
  function showHoverNotice(room) {
    if (state.replay) return;
    const actor = actors.get(room);
    if (!actor || actor.node.classList.contains("is-speaking")) return;
    const bubble = actor.node.querySelector(".walk-bubble");
    bubble.textContent = hoverNoticeLine(room);
    bubble.dataset.kind = "notice";
    actor.node.classList.add("is-hovering");
  }
  function speakNotification() {
    const rooms = [...actors.keys()];
    for (let i = 0; i < rooms.length; i++) {
      const room = rooms[noticeTurn++ % rooms.length];
      if (room !== selected) {
        speak(room, notificationLine(room), 7800, "notice");
        return;
      }
    }
  }
  function speakDialogue() {
    for (let i = 0; i < dialogueScenes.length; i++) {
      const scene = dialogueScenes[dialogueTurn++ % dialogueScenes.length];
      if (scene[0] === selected || scene[1] === selected) continue;
      const first = actors.get(scene[0]), second = actors.get(scene[1]);
      if (!first || !second || Math.hypot(first.x - second.x, first.y - second.y) > 270) continue;
      stopTalk();
      showBubble(scene[0], scene[2], "dialogue");
      replyTimer = setTimeout(() => showBubble(scene[1], scene[3], "dialogue"), 1700);
      followupTimer = setTimeout(() => showBubble(scene[0], "좋아요, 핵심만 하나 더 맞춰볼까요?", "dialogue"), 3400);
      closingTimer = setTimeout(() => showBubble(scene[1], "네, 그 정도면 다음에 이어가기 좋겠어요.", "dialogue"), 5100);
      finishTalk(9000);
      return;
    }
    speakNotification();
  }
  function startLeaderSmallTalk(partner) {
    const lines = leaderSmallTalk[partner];
    if (!lines || selected || state.replay || document.hidden || state.view !== "office") return;
    stopTalk();
    showBubble("hq", lines[0], "dialogue");
    replyTimer = setTimeout(() => showBubble(partner, lines[1], "dialogue"), 1600);
    followupTimer = setTimeout(() => showBubble("hq", "좋아요. 너무 급하게 하진 말아요.", "dialogue"), 3200);
    closingTimer = setTimeout(() => showBubble(partner, "네, 다음에 진행도 같이 알려드릴게요.", "dialogue"), 4800);
    finishTalk(8800);
  }
  function speakAmbient() {
    const rooms = [...actors.keys()].filter((room) => room !== selected);
    if (!rooms.length) return;
    const room = rooms[ambientTurn++ % rooms.length];
    const lines = ambientLines[room];
    speak(room, lines[ambientTurn % lines.length]);
  }
  function scheduleTalk() {
    if (talkTimer || document.hidden || state.view !== "office" || state.replay || !actors.size) return;
    talkTimer = setTimeout(() => {
      talkTimer = 0;
      if (document.hidden || state.view !== "office" || state.replay) return;
      const event = ["dialogue", "notice", "dialogue", "ambient"][talkTurn++ % 4];
      if (event === "notice") speakNotification();
      else if (event === "dialogue") speakDialogue();
      else speakAmbient();
    }, 7000 + Math.random() * 7000);
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
    speak(room, "불러주셨나요?", 4200, "greeting");
    if (!insideWorkbench) actor?.node.scrollIntoView({block: "nearest", inline: "center", behavior: "smooth"});
    $("conversation-portrait").innerHTML = sprite(room, "portrait-art");
    $("office-conversation").dataset.character = room;
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
    // The send action has started; do not leave a duplicate in the composer
    // while the local model works through a potentially long response.
    localWrite("office-draft:" + room, null);
    $("office-message").value = "";
    showConversation(room);
    try {
      const response = await fetch("api/action", {
        method: "POST", headers: {"Content-Type": "application/json", "X-Hermes-Action": "1"},
        body: JSON.stringify({action: "office_chat", room, message}),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "답변을 확인하지 못했습니다.");
      chat.history.push({role: "assistant", content: result.response});
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
  return {render, visibility, select, workbench, setZoom: setOfficeZoom};
})();
