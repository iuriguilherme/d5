/compound-engineering:ce-brainstorm

<objective>
Brainstorm the full architecture and design of a social media content organizer application delivered as a Telegram bot.

The goal is to produce a comprehensive, well-reasoned design — covering tech stack choices, data architecture, UX flows, scheduling heuristics, and AI-powered suggestion logic — that a developer can use as the foundation for implementation planning.
</objective>

<application_description>
This application helps a user manage and execute their social media content strategy through a conversational Telegram bot interface. It acts as a personal content coach: collecting ideas, predicting what to post next, reminding the user when to post, and learning from past posting behavior.

Key capabilities:
- Store and organize general subject ideas for social media posts
- Suggest which subject to post next, based on configurable heuristics
- Accept feedback on what was actually posted, to close the loop
- Import posting history from social media platforms to improve predictions
- Send scheduled reminders with a ready-to-post suggestion
- Learn from user strategy notes and personal research to weight suggestions
</application_description>

<user_stories>
1. As a user, I can submit a new subject idea via the Telegram bot so it is saved in my content pool
2. As a user, I can ask the bot to suggest a subject to post today, and it will pick one based on my history and heuristics
3. As a user, I can confirm what I actually posted so the system records it as done
4. As a user, I can import my past posting history from social media platforms so predictions improve over time
5. As a user, I can set reminder frequency (e.g., once/day, twice/week) and the bot will remind me when it's time to post
6. As a user, I can share my own social media strategy notes and research so the algorithm gives them extra weight
7. As a user, I must approve AI-generated subject suggestions before they are added to my pool
</user_stories>

<cron_system>
- Fixed or dynamic reminder schedules (user-configurable: e.g., twice per week, once per day)
- When a reminder fires, the system auto-selects a subject using the active heuristics and sends it to the user
- Default posting frequencies should follow best practices per platform (Instagram, TikTok, Threads, etc.)
</cron_system>

<persistence_requirements>
- Plain text storage: all user inputs (ideas, feedback, strategy notes, imported history)
- Vector database: embeddings of content for semantic search and pattern analysis
- Two distinct data stores are required — brainstorm which databases fit each role best
</persistence_requirements>

<analytics_and_heuristics>
- Simplest heuristic: random choice from the subject pool
- Avoid suggesting the same subject too soon after it was last posted
- Weight suggestions by user-provided strategy research
- If posting history is available: use prediction models to surface new subject ideas
- New predicted subjects require user approval before entering the active pool
- Heuristics should be pluggable / configurable over time
</analytics_and_heuristics>

<tech_stack_research>
The primary maintainer knows Python and Aiogram (async Telegram bot framework). However, the brainstorm should include a thorough research phase before finalizing the stack recommendation:

- Research and compare Telegram bot frameworks across languages (Python, Go, Node.js, etc.)
- Evaluate Aiogram vs alternatives on: async support, ecosystem maturity, LLM/AI integration ease, community, maintenance status
- Research best-fit vector databases for this use case (ChromaDB, Qdrant, Weaviate, pgvector, etc.)
- Research best-fit plain text / relational databases (SQLite, PostgreSQL, etc.)
- Propose the final recommended stack with clear reasoning
- If an alternative to Python/Aiogram is significantly better, explain the trade-offs honestly
</tech_stack_research>

<brainstorm_scope>
Explore and document decisions across these dimensions:

1. **Bot UX and conversation flows** — How does the user interact? What commands, menus, inline buttons are needed?
2. **Data model** — What entities exist (subjects, posts, reminders, strategies, users)?
3. **Scheduler design** — How are cron jobs managed? Fixed vs dynamic schedules?
4. **Suggestion engine** — How does the heuristics pipeline work? How are weights combined?
5. **History import** — What APIs or file formats can be used to import social media history?
6. **Prediction system** — What ML or statistical approach fits this scale?
7. **Tech stack** — Final recommendation with research backing
8. **Deployment** — How and where does this run? What are the infrastructure needs?
9. **Extensibility** — How can new heuristics or platforms be added later?

Thoroughly analyze trade-offs for each dimension. Consider multiple approaches before settling on a recommendation.
</brainstorm_scope>

<output>
Produce a structured brainstorm document saved to: `./docs/brainstorm/social-media-organizer.md`

Structure the output as:
- Executive summary (3-5 bullet points of key decisions)
- Section per brainstorm dimension listed above
- Each section: options considered → recommended approach → rationale
- Final recommended tech stack with justification
- Open questions and risks to resolve before implementation
</output>

<verification>
Before completing, verify:
- All 9 brainstorm dimensions are addressed
- Tech stack recommendation is backed by research, not assumed
- Trade-offs for at least 2 alternatives per major decision are documented
- The output file is saved to ./docs/brainstorm/social-media-organizer.md
</verification>
