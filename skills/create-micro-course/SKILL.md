---
name: create-micro-course
description: Convert supplied source text into a Learn on the Way Markdown micro course for operator review and import.
---
Create one Markdown file with YAML frontmatter containing id (lowercase slug matching filename), name, and description. Use consecutive headings starting at 1: `## Step 1 [text] Title`. Allowed types are text, qa and quiz. Keep spoken text steps short enough for roughly one to two minutes. Alternate explanation with relevant discussion and recall checks when useful; let source material determine the structure.

For a quiz, write the question followed by `### Expected answer` on its own line and a source-grounded expected answer. This section is instructor context, not narration. For qa, supply the topic and relevant source context. Do not fabricate facts absent from the source. Preserve necessary qualifications and make the course understandable without viewing diagrams.

Review the whole course for a coherent progression, accurate source coverage and spoken usability. Save as courses/<id>.md in the project and validate with `docker compose run --rm app python -m app.admin validate-courses`. Import is an operator action, not a learner-facing MCP tool. Upload only when the user has authorized server modification. Never edit a live course with existing progress without a migration plan; publish a new course ID for a new edition.
