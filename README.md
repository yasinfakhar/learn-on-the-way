# Learn on the Way

A FastAPI + PostgreSQL micro-course service with an authenticated Streamable HTTP MCP endpoint for compatible ChatGPT and Claude clients. Each course is one Markdown file. The host AI handles narration, grounded discussion and quizzes; this server handles content, accounts and private learning state. No model API key is required by the service.

## Deployment on the owner's server

- Directory: `/opt/learn-on-the-way`
- Listener: **127.0.0.1:8790** (intentionally private to the server)
- Public hostname: **https://learn.sayahub.ir**
- MCP endpoint: **https://learn.sayahub.ir/mcp**
- Database: dedicated `learn_on_the_way` database and role on the existing PostgreSQL container. No second database server.
- Secrets: server-only `.env`, mode 0600; never committed.

Point Nginx at `http://127.0.0.1:8790`. See [deploy/nginx.conf](deploy/nginx.conf). Proxy the entire hostname, including `/.well-known/` and `/oauth/`, with HTTPS. Cloudflare should use Full (strict) TLS and bypass caching. Health check: `curl http://127.0.0.1:8790/health`.

```sh
cd /opt/learn-on-the-way
docker compose up -d --build
docker compose logs --tail=100 app
```

## Easy account setup

1. Add the remote MCP URL in a compatible client and select OAuth.
2. The client discovers authorization metadata and registers itself (DCR).
3. A browser opens. Choose **Create account and connect** or sign in.
4. The client receives credentials using authorization code + S256 PKCE, stores them and refreshes them automatically.
5. Ask to start a course. No copying API keys, and no passwords in chat.

The package includes `plugin.json`, `mcp.json` and onboarding/teaching/authoring skills. Actual client installation and directory publication are separate from deploying this backend. ChatGPT's current plugin packaging and authentication docs: https://developers.openai.com/plugins/build/plugins and https://developers.openai.com/plugins/build/auth. For Claude, add the remote URL in a client supporting remote HTTP MCP with OAuth. Client plan, UI and voice-mode tool support vary. End-to-end host-client connection must be tested after DNS and TLS are ready. Deployment alone does not make the app appear in a public directory.

**Voice limitation:** MCP transports text and tool results. This project does not itself supply a driving voice interface, speech recognition or audio playback. Confirm the chosen host can invoke this MCP server during voice conversations; otherwise a dedicated voice client is needed.

## Tools

| Tool | Purpose |
|---|---|
| list_micro_courses | IDs, names, descriptions, step counts |
| search_micro_courses | Search course content and metadata |
| start_or_continue_course | Start/resume at first incomplete step |
| open_step | Get a step plus grounding material |
| record_answer | Store answered yes/no, exact answer, optional correctness |
| complete_step | Persist delivered/discussed step completion |
| complete_course | Pass only after every step is complete |
| rate_course | Integer 1–5, only after passing |
| get_my_learning | User's started/passed courses, answers and ratings |

The same operations are available as `POST /api/tools/{name}` with a JSON argument object and OAuth bearer token. The server derives user identity from the token; no user ID argument is accepted. Repeated start/completion calls preserve progress. A recorded quiz response is required to complete its step. Incorrect answers do not automatically block completion: the tutor can explain and discuss them. “Passed” means all steps completed, not a scored exam.

## Author a course

See [courses/learning-that-sticks.md](courses/learning-that-sticks.md) and [the authoring skill](skills/create-micro-course/SKILL.md).

```markdown
---
id: example-course
name: Example Course
description: What the learner will understand.
---
## Step 1 [text] A short lesson
Narration grounded in the supplied source.

## Step 2 [qa] Discuss the idea
Relevant context and discussion guidance.

## Step 3 [quiz] Check understanding
A question to ask the learner.
### Expected answer
Instructor-only answer guidance.
```

Use consecutive step numbers and types `text`, `qa`, or `quiz`. Put the file at `courses/<id>.md`, upload it to the same server directory, validate, then restart:

```sh
docker compose run --rm app python -m app.admin validate-courses
docker compose restart app
```

Courses are mounted read-only in the container. Operator access is required to publish content; learners cannot modify it. Source text can be converted with the included authoring skill. The service does not automatically call an LLM to generate courses. Existing progress is tied to the Markdown content hash. Publish a new ID for an updated edition rather than silently changing an in-progress course.

## Development and verification

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q tests
```

The integration suite uses an isolated SQLite test database and verifies OAuth signup, code single use, refresh rotation, user isolation, completion/rating rules, argument validation and real MCP transport initialization/discovery/calls. Production uses PostgreSQL and transaction locks to serialize concurrent updates to each user's course.

## Operations and current scope

- Passwords use Argon2; opaque access/refresh/code credentials are hashed in storage. Access tokens expire in one hour; refresh tokens rotate and expire after 30 days. Browser consent uses a signed, HTTP-only session and CSRF token.
- The service supports public OAuth clients with PKCE (`token_endpoint_auth_method=none`), not confidential clients or external identity providers. Email verification, password recovery and social login are not implemented. Account creation requires an email and password; no email delivery provider is needed.
- OAuth POST routes have a basic in-process throttle. Run a single worker as configured. Nginx-proxied users share the proxy's quota (20 POSTs per route per minute). Add trusted edge limits before substantial public traffic.
- Initial tables are created on startup. Future schema changes need versioned migrations; do not rely on `create_all` to alter deployed tables.
- Back up the dedicated PostgreSQL database and course folder with your existing backup process. No backup job is installed by this project.
- Delete an account and its learning data/credentials: `docker compose exec app python -m app.admin delete-account person@example.com`.
- Expired auth records are rejected but currently retained; schedule database housekeeping as traffic grows. Password reset and email verification are future work.

Configure while parked. Lessons should pause whenever attention is needed for traffic.

## Narration-first host behavior

Starting or resuming returns the actual `next_step` and step-specific `delivery` instructions. A text step must be narrated before any Q&A or quiz; no invented coaching or personal reflection questions. Read operations never complete a lesson. Future steps cannot be opened, completed or answered until preceding steps are complete. `open_step` includes earlier narrative context only for Q&A/quiz, rather than exposing future quizzes during narration. Persian MCP output uses unescaped Unicode.

These controls guide a host AI; the server cannot observe or prove that the host actually spoke the whole narration. Mobile voice behavior must still be checked in a fresh Live conversation. Existing client connections may cache server instructions and tool descriptions; refresh tool metadata or reconnect if needed. Course content and existing learner progress are preserved by this change.
