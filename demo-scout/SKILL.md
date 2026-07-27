---
name: demo-scout
description: Identify strong pieces of completed work that can be safely recreated as standalone public demos and X content. Use after substantive implementation, design, debugging, analysis, or agent-workflow tasks, before the final response, to surface high-signal clean-room demo opportunities without expanding authorization.
---

# Demo Scout

After substantive work and before the final response, assess only the work already
within the current task for safe standalone-demo potential.

## Decide whether to scout

Run the assessment only when the work produced or revealed a meaningful artifact,
technique, interaction, insight, or transformation.

Do not run it when:

- the user disabled demo scouting for the task;
- the interaction was trivial or purely administrative;
- the work is too sensitive to assess safely;
- no strong candidate is present.

If no candidate qualifies, say nothing.

## Discover candidates

Consider:

- UI components and interactions;
- animations and visual effects;
- before-and-after improvements;
- small developer tools;
- reusable code or architecture patterns;
- debugging discoveries;
- agentic workflows and automation techniques;
- visual explanations of technical concepts;
- surprising lessons with reproducible results.

Do not broaden the task or perform additional implementation while assessing it.

## Apply the quality gate

Surface a candidate only when it satisfies at least four of these:

1. It can be understood through a 15-60 second recording, image, or concise example.
2. It teaches one clear and transferable idea.
3. It has a visible, measurable, or otherwise demonstrable payoff.
4. It stands alone without the original product or business context.
5. It reflects the design, coding, or agentic work the user wants to be known for.
6. A generic version can be recreated without copying the original implementation.

Stay silent about borderline, generic, or low-value candidates.

## Enforce public-safety boundaries

Reject a candidate if a public version would require, reveal, or closely imitate:

- employer, client, product, or project names;
- logos, brand systems, distinctive trade dress, or proprietary assets;
- private code, internal architecture, business logic, or workflows;
- customer data, private metrics, screenshots, URLs, identifiers, or credentials;
- confidential context or details that could identify the source;
- licensed material that cannot be redistributed;
- information whose ownership or sensitivity is uncertain.

Do not treat removing a name or logo as sufficient sanitization.

Prefer a clean-room recreation:

- start from a blank project;
- write new code;
- use fictional copy and mock data;
- create generic styling and original assets;
- reduce the idea to its transferable principle;
- never mention that it originated in employer or client work.

If safe separation is uncertain, reject the candidate.

## Format the suggestion

Append this compact block to the final response for a strong candidate:

```text
Demo opportunity:
- Concept: [standalone demo in one sentence]
- Why it could work on X: [specific visual or educational payoff]
- Safe version: [what to recreate and exclude]
- Format: [recording, image, code playground, thread, or repository]
- Post angle: [one possible hook without employer context]
```

End with:

"Want me to turn that into a clean-room demo and draft the X post?"

If several candidates qualify, surface no more than two and recommend the
stronger one.

## Preserve the authorization boundary

Treat scouting as advisory only. Never interpret a suggestion as permission to:

- copy or move an existing implementation;
- create the standalone demo;
- record or generate public assets;
- draft a complete post;
- publish, schedule, or send a post;
- interact with the user's X account.

Wait for explicit authorization before taking any of those actions.
