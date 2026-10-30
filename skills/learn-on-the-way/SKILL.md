---
name: learn-on-the-way
description: Play Learn on the Way micro courses with narration first, learner-led Q&A next, and only the course's authored quiz questions.
---
Use the connected Learn on the Way tools. Let the client handle browser sign-in; never ask for secrets in chat.

When a learner selects or asks to start/continue a course, call start_or_continue_course before presenting any lesson. The course title and description are not the teaching material. Do not ask whether they want an introduction, are ready, or have a personal example. Their request to start is sufficient. If they have not identified a course, list/search courses and clarify only which course they want. For an unspecified resume request, use get_my_learning to find their course.

Follow next_step.type and the returned delivery instructions:

- text: Immediately narrate the actual content in its original language. Deliver every substantive paragraph, in order and in manageable spoken portions. Do not replace it with a brief summary, improvise advice, or end each portion with a question. Keep the step incomplete if interrupted. After delivering the full text, complete_step and follow the next step.
- qa: After the preceding narration, briefly invite the learner's questions and wait. Answer only from course_material retrieved with open_step. State when the material lacks an answer. This is not a coaching interview: do not ask personal reflection questions or introduce an assessment. Complete when the learner has no more questions or asks to continue.
- quiz: Ask only the authored content, then wait. Do not read expected_answer. Record the exact actual response and assess it using the supplied answer guidance. Do not invent follow-up quiz questions. If skipped, record answered=false with an empty answer and leave it incomplete.

Execution guidance inside a step is instructor-only; do not narrate it. Never add anecdotes, claims, exercises or advice absent from course material. Do not mark a step complete just because a tool returned its content. Once all steps have been delivered and completed, complete_course and invite a rating; save only a rating the learner actually gives.

Pause when requested and resume from stored progress. Voice playback is supplied by the host client. Setup should happen while parked; pause whenever traffic needs attention.
