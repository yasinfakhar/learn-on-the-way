---
name: setup
description: Connect a Learn on the Way account and help a new learner choose their first micro course.
---
Let the client open browser signup/sign-in and store OAuth credentials. Never ask for passwords or tokens in chat. Invoke list_micro_courses to trigger authentication if needed.

If the learner has not selected a course, show a short selection and ask which one they want. If they have already selected a course or asked to start it, skip preference and readiness questions: call start_or_continue_course and immediately narrate its returned text step following delivery. Do not quiz or coach before the authored quiz step.

Voice depends on the host client's support. Complete account setup while parked.
