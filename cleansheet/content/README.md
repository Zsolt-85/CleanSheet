# Content — LinkedIn publishing system

One folder per post. Everything needed to publish lives inside it: copy,
image, hashtags, and a notes file tracking what happened after posting.

## Naming

```
YYYY-MM-DD-<slug>/
```

Date-first ISO format so folders sort chronologically (`2026-09-16-...`
before `2026-09-23-...`). Dotted dates (`16.09.2026`) do NOT sort — don't
use them.

## Anatomy of a post package

```
2026-09-16-cleansheet-beta-launch/
├── post.md    # EN + RO copy, hashtags included, ready to paste
├── image.png  # attach to the post (self-contained copy, not a link)
└── notes.md   # status, posted URL, replies, files, follow-ups, metrics
```

## Workflow

1. **Draft** — create folder, write `post.md`, generate/copy `image.png`,
   set status `draft` in `notes.md`.
2. **Review** — read it once out loud. If it sounds like a template, rewrite.
3. **Schedule** — Tue–Thu mornings EU. Set status `scheduled`.
4. **Post** — paste text, attach image, hit Post. **Put the URL in the
   first comment, not the post body** — LinkedIn demotes posts with
   external links. Set status `posted` + paste the post URL in notes.
5. **First hour** — reply to every comment. This decides distribution.
6. **Log** — record replies, files received, discovery answers, and any
   second-file returns (the golden event) in `notes.md`.
7. **Commit + push** — the content history is part of the repo.

## Cadence

2–3 posts per week max during beta. Quality + replies beat volume.
Sequence logic: ask (beta call) → prove (before/after) → involve (poll),
then repeat with real user stories as they arrive.
