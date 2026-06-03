---
name: english-practice
description: Turn David's English tutor recordings and sentence corrections into transcripts, error analysis, and spaced-repetition drills delivered on Telegram.
version: 1.0.0
platforms: [linux, macos]
metadata:
  hermes:
    category: learning
    tags: [english, language-learning, transcription, spaced-repetition]
    config:
      - key: english.lessons_dir
        description: Local folder where tutor recordings + corrections land
        default: ~/english-lessons
        prompt: Path to the English lessons folder
      - key: english.deck_path
        description: Spaced-repetition deck file
        default: ~/.hermes/data/english/srs_deck.json
        prompt: Path to the SRS deck
---

# English Practice

David takes online English lessons on Mon/Tue/Wed. After each lesson the tutor sends
a recording (video) and written sentence corrections via KakaoTalk. David forwards
these files to Hermes via Telegram. This skill saves the files, ingests the material,
and builds a durable practice routine.

## When to Use
- David sends a lesson file (video or text) via Telegram → trigger **Procedure C**.
- The scheduled "check for new lessons" job fires (Mon/Tue/Wed 20:00) → trigger **Procedure A**.
- The scheduled "daily drill" job fires (21:00) → trigger **Procedure B**.
- David asks to review English, do a drill, or analyze a specific lesson.

## Procedure
### C. Receiving files via Telegram (triggered immediately when David sends a file)
1. **Save the file** to `~/english-lessons/` using the helper:
   `python ~/.hermes/scripts/english_intake.py --save-file <file_path> --lessons-dir <dir>`
   This saves the file and prints the destination path.
2. Confirm to David: "저장했어. 오늘 수업 파일 다 보냈어? 영상이랑 교정 텍스트 둘 다 있으면 바로 분석할게."
3. Once David confirms all files for the session are sent, proceed with **Procedure A**
   on the newly saved files.

### A. Intake & analysis (new lessons)
1. Find new sessions:
   `python ~/.hermes/scripts/english_intake.py --lessons-dir <dir>`
   (add `--mark` only after you have successfully processed them).
2. For each new session:
   - **Transcribe** each audio/video file with the transcription tool (or `video_analyze`
     for video). Save the transcript next to the source.
   - **Read the correction file(s)** (txt/md/docx/pdf).
3. **Mine correction pairs.** Extract each "❌ what David said → ✅ better form"
   pair plus a short reason (grammar, collocation, naturalness, pronunciation note).
   Also pull recurring error *patterns* (e.g. article use, past tense, prepositions).
4. **Add cards to the SRS deck** (de-duplicated automatically):
   `python ~/.hermes/scripts/english_srs.py add --wrong "..." --correct "..." --note "..."`
5. Mark the session processed (`english_intake.py --mark`) and post a short summary:
   what was covered, the top 2–3 recurring patterns, and how many new drill cards
   were added. Save persistent weakness patterns to memory.

### B. Daily drill
1. `python ~/.hermes/scripts/english_srs.py due` → renders the due cards as a quiz.
2. Deliver it as the drill. Encourage David to reply with his attempts.
3. When David answers, grade each, then record results:
   `python ~/.hermes/scripts/english_srs.py review --id <card_id> --result correct|wrong`
   Correct → the card resurfaces later; wrong → it comes back tomorrow.

## Output Format
- Intake summary: 4–6 bullets max + pattern callouts. Speak encouragingly.
- Drill: numbered "rewrite this" prompts; reveal answers after his attempt when
  interactive, or include them under an *Answers* section for the scheduled push.

## Pitfalls
- Don't re-process a session — always check intake state; only `--mark` on success.
- Keep correction cards atomic (one error per card) so SRS scheduling is meaningful.
- Be specific in `--note` (the *why*), since that's the real learning.

## Verification
- New cards exist in the deck (`english_srs.py stats`).
- The processed-session count increased by exactly the number handled.
