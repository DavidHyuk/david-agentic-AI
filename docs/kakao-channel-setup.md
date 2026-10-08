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
`cloudflared` binary when temporary transport is needed, and starts the collector:

- `kakao-webhook.service`: local feedback collector on `127.0.0.1:8787`
- `kakao-tunnel.service`: optional temporary public HTTPS tunnel when no fixed
  origin is configured; disabled on the current DGX after Funnel verification

The random path is the webhook's shared secret; never commit or send it in a
screenshot. Runtime logs redact both that path and raw Kakao user IDs.

## 3. Publish an HTTPS URL

Kakao's servers must reach the collector through HTTPS. The current DGX uses a
verified fixed Tailscale Funnel on HTTPS port 10000. Copy the complete private
skill URL through Ellie or the file below, then save and deploy it in Open Builder.
For temporary Quick Tunnel setups, read the origin:

```bash
journalctl --user -u kakao-tunnel.service --no-pager | grep trycloudflare.com
```

After every Quick Tunnel startup, including DGX reboot and automatic recovery,
`kakao_tunnel_url.py` reads only the current systemd invocation's journal and
checks the actual public skill endpoint with an empty JSON body. That probe
does not register a sender or queue feedback. A reachable endpoint atomically
refreshes the private mode-0600 URL file; failure preserves the previous file
and is reported in the service journal. This refresh does **not** update Kakao's
deployed skill URL: change it in Open Builder and deploy again when the origin
changes. An `active` process alone does not prove the registered URL is reachable.

The installer combines the current origin and secret path in a private mode-0600
file. In the private Observatory, Ellie → **계정·연결 설정** provides **챗봇 관리자센터
열기** and **스킬 URL 복사**. Copy directly into Open Builder's skill URL field;
the normal status view does not include the secret endpoint. Collector/tunnel
status does not prove that Kakao's channel has been deployed. The terminal
alternative is:

```bash
cat ~/.hermes/data/english/kakao-skill-url.txt
```

Do not paste or share that combined URL anywhere else.

This Quick Tunnel is for initial testing. Its hostname changes if the tunnel
service restarts. For ongoing use, configure a stable public HTTPS origin.

### Stable public address

An existing named Cloudflare Tunnel or Tailscale Funnel can provide the fixed
origin. Start that transport before configuring it here. On this DGX, Tailscale
ports 443 and 8443 belong to other applications; do not replace those routes or
publish their private dashboards. A separate Funnel on port 10000 exposes only
the existing loopback feedback collector:

```bash
sudo tailscale funnel --bg --https=10000 http://127.0.0.1:8787
bash bootstrap/install_kakao_services.sh \
  --public-origin https://spark-df6d.tail63b0d1.ts.net:10000
```

Funnel may require the tailnet owner to enable it at the authorization link
printed by Tailscale. `--bg` persists the route across DGX reboot; see the
[Tailscale Funnel CLI documentation](https://tailscale.com/docs/reference/tailscale-cli/funnel).
The route is public, but sender enrollment and the secret endpoint stay enforced.
Public DNS can take up to ten minutes to appear after first enabling Funnel.
The verifier resolves `*.ts.net` through public DNS-over-HTTPS and connects to
that public ingress IP with the hostname's TLS certificate. Local MagicDNS
access alone is not accepted as proof that Kakao can reach the endpoint.
Fresh DNS queries also avoid retaining an HTTP-cached NXDOMAIN response after
the new record appears. Both public Funnel ingress IPs on the current DGX were
verified with valid Kakao responses in approximately 160 ms; the Quick Tunnel
is now disabled. After the Kakao URL update and deployment, two real messages
at 23:06:36 and 23:06:53 PDT on October 7 returned HTTP 200 and were saved as
separate lesson files, confirming the deployed Kakao-to-collector route.
Test the fixed URL in Open Builder and from the real Kakao app before declaring
delivery restored, including whether Kakao accepts that explicit HTTPS port.
If the port is rejected, use a named Cloudflare Tunnel on standard HTTPS 443.

`--public-origin` verifies the endpoint before replacing the private skill URL
and records the origin in `~/.hermes/data/english/kakao-public-origin.txt`.
It then disables the old Quick Tunnel. Later installer runs and secret rotations
reuse this fixed origin. Copy the resulting private URL into Open Builder and
deploy once; ordinary reboots no longer require changing its hostname.
The installer does not create the external fixed transport or configure Kakao
on your behalf. Ellie shows fixed-address configuration separately from Quick
Tunnel process status; neither proves Kakao deployment or live delivery.

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

Rotation invalidates the old secret, restarts the collector, and refreshes the
private URL file using the configured fixed origin or current Quick Tunnel:

```bash
bash bootstrap/install_kakao_services.sh --rotate-path
cat ~/.hermes/data/english/kakao-skill-url.txt
```

Paste the refreshed URL into Open Builder again before testing. A Quick Tunnel
hostname can also change after a restart, so always use the current private file.
