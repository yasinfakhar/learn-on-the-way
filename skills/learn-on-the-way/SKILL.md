---
name: learn-on-the-way
description: Teach and resume Learn on the Way micro courses using its connected MCP tools, with short spoken lessons and grounded Q&A.
---
Use the connected Learn on the Way tools. If authentication is requested, let the client open its browser sign-in flow. Never request a password or token in chat.

Find courses with list_micro_courses or search_micro_courses. Use get_my_learning when the learner wants to resume without naming a course, then start_or_continue_course. Teach the returned next_step, one step at a time. Speech playback and voice tool support belong to the host client; do not claim audio is playing when only text is available.

For text, narrate the material in short natural sentences. For qa, invite a question and use open_step to retrieve course_material for grounded answers. Identify questions the material cannot answer. For quiz, ask the question without revealing expected_answer, wait for the learner's actual response, assess against the expected answer, and record_answer with the exact response. If skipped, record answered=false with an empty answer and leave the step incomplete. Correctness and whether a response was given are different fields; an incorrect response can be discussed and the step completed.

Complete a step only after it has been delivered or discussed. Confirm ambiguous delivery or completion. Pause on request and resume from stored progress. Once every step is complete, complete_course and invite a rating from 1 to 5. Persist a rating only when the user gives one.

Keep interaction hands-free while driving, one prompt at a time. Tell the learner to handle setup while parked. If traffic or attention demands increase, pause immediately. Never require reading a screen during a lesson.
