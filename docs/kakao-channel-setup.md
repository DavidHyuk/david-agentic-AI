# KakaoTalk Channel feedback collection

This integration collects messages sent **to the Channel chatbot**, not messages
from David's existing private KakaoTalk conversations. The webhook only queues raw
teacher feedback locally; Hermes's scheduled English intake analyzes it with the
local model and sends the summary and SRS drill to the dedicated English Telegram bot.

## 1. Complete the Open Builder bot

In Open Builder, create a skill named `English Feedback Intake`. Leave its URL
empty until steps 2 and 3 are running. Return to the bot's **폴백 블록**, select
that skill from **스킬 검색/선택**, then use the `+` in **봇 응답** to select
**스킬데이터로 사용**. A fallback block is intentional: all otherwise-unmatched
teacher text reaches the collector.

Do not try to empty the text inside the mandatory default fallback response.
Open Builder prevents the only response from being empty. Add the skill-data
response first, then remove the old static `제가 할 수 있는 일이 아니에요`
text response. The server's `template` then becomes the bot output. Do not add
parameters; Kakao includes the original message in `userRequest.utterance` by
default.

## 2. Install and start the local collector

```bash
bash bootstrap/install_kakao_services.sh
```

The installer stages only the Kakao/English runtime files, generates
`KAKAO_WEBHOOK_PATH` in `~/.hermes/.env`, installs the matching ARM64 or AMD64
`cloudflared` binary, and starts two user services:

- `kakao-webhook.service`: local feedback collector on `127.0.0.1:8787`
- `kakao-tunnel.service`: temporary public HTTPS tunnel

The random path is the webhook's shared secret; never commit or send it in a
screenshot. Runtime logs redact both that path and raw Kakao user IDs.

## 3. Publish an HTTPS URL

Kakao's servers must reach the collector through HTTPS. Read the Quick Tunnel URL:

```bash
journalctl --user -u kakao-tunnel.service --no-pager | grep trycloudflare.com
```

The installer combines the current origin and secret path in a private mode-0600
file. Copy its entire contents directly into Open Builder's skill URL field:

```bash
cat ~/.hermes/data/english/kakao-skill-url.txt
```

Do not paste or share that combined URL anywhere else.

This Quick Tunnel is for initial testing. Its hostname changes if the tunnel
service restarts. For ongoing use, replace it with a named Cloudflare Tunnel and a
stable hostname.

## 4. Test, lock down, and deploy

1. Use Open Builder's test panel and send a unique mock teacher correction.
2. Confirm the terminal says it saved a `kakaotalk-feedback-*.txt` file under
   `~/english-lessons/YYYY-MM-DD/`.
3. Verify the bot answers: `피드백을 저장했어요...`.
4. Deploy the bot, then verify **설정 → 카카오톡 채널 연결** names
   `David English Feed` as the operating channel and shows the bot as **실행**.
   In KakaoTalk Channel Manager, disable the human-support path at
   **1:1 채팅 → 채팅 설정** and disable any active channel list/custom menu
   under **비즈니스 도구**. Under **프로필 → 채널홈 설정**, add or enable
   the chat card and confirm that it exposes **챗봇 채팅**. Save the channel
   home, then use the home icon in KakaoTalk and enter through that
   **챗봇 채팅** card.
5. Open Builder's bot-test identity is not the same as a real KakaoTalk app
   identity, so send a short message from the real app and expect the first
   request to receive the unapproved-sender message. Immediately approve that
   known real sender without printing its raw Kakao ID, restart the collector,
   and send the message again:

```bash
python3 ~/.hermes/scripts/kakao_webhook.py \
  --approve-latest-sender \
  --env-file ~/.hermes/.env
systemctl --user restart kakao-webhook.service
```

The command prints only a one-way sender fingerprint. Run it only immediately
after a message from a sender you intend to approve. Additional teachers can be
approved the same way; the allowlist is additive. The rejected registration
message is intentionally not queued, so it must be re-sent after approval.

6. Send a second sentence on the same day and run:

```bash
python3 ~/.hermes/scripts/english_intake.py
```

If Kakao replies with `위 운영시간 내에 채팅이 가능합니다` or `지금은 ...
채팅 가능한 시간이 아닙니다`, the user entered the Channel Manager's 1:1
human-chat path. Disabling 1:1 chat does not convert that existing room into a
bot room; `관리자가 채팅을 OFF한 상태입니다` still identifies the old
human-chat path. These Kakao-generated messages never reach this webhook, so
re-send the feedback after entering through the channel home's bot card.

Only the newly arrived file should appear. After successful analysis,
`english_intake.py --mark` records that exact file version, so repeated scans do
not process it twice.

6. This prevents unknown channel visitors from writing lesson files. Connect the
   chatbot to the KakaoTalk Channel and deploy it. Then re-register the Hermes cron
   jobs so the daily 20:00 coaching is active:

```bash
python3 bootstrap/register_cron.py
```

At 20:00, new feedback is analyzed into SRS cards. With no new feedback, Hermes
coaches from accumulated weak cards instead of suppressing the notification; on
Sunday it reviews the current week's feedback and cumulative weaknesses. The
21:00 dedicated English Telegram drill includes cards created by intake when the local model
successfully processes the feedback.

## 5. Rotate a leaked or stale URL

Rotation invalidates the old secret, restarts both services, and refreshes the
private URL file:

```bash
bash bootstrap/install_kakao_services.sh --rotate-path
cat ~/.hermes/data/english/kakao-skill-url.txt
```

Paste the refreshed URL into Open Builder again before testing. A Quick Tunnel
hostname can also change after a restart, so always use the current private file.
