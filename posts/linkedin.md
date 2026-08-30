# OATS — Can an AI agent actually diagnose a production incident?

*A LinkedIn post. Repo: https://github.com/4sgupta828/oats*

---

**The 2 a.m. problem:**

Something is on fire. An engineer spends the first painful hour doing the same ritual by hand — pulling metrics, tailing logs, running `kubectl` and `aws`, and then the *hard* part: guessing which anomaly is the **cause** versus a downstream **symptom**, and mapping how far it spread. It's slow, stressful, and the reasoning almost never gets written down. "AIOps" has promised to fix this for a decade and mostly delivered dashboards that tell you *what* changed, not *why*.

**What I explored: OATS — an autonomous SRE agent that both *acts* and *proves the root cause.***

Two halves, because neither alone is enough:
- A **statistical RCA engine** that reads telemetry and separates the primary symptom from its cascade with real methods — Bayesian changepoint detection, multivariate anomaly detection, and **Granger causality** to infer cause→effect between metric series — with no hardcoded incident windows.
- An **autonomous ReAct agent** that then investigates the *live* environment with real tools (`kubectl`, `aws`, `psql`, `helm`), reasoning Thought → Action → Observation until it submits a structured report.

Everything is **event-sourced**: every turn is a row in Postgres, streamed live, so a human can watch, interrupt, inject feedback, and resume. `finish` *pauses* for review rather than ending. The stats hand the LLM a ready-made scaffold so it doesn't have to rediscover which anomaly came first.

**What AI solves well:**
- Orchestration and synthesis: choosing the next investigative step, reading heterogeneous evidence, and writing a coherent narrative a human can act on.
- Turning a wall of telemetry into "here's the likely cause and why."

**What AI does NOT solve — and shouldn't:**
- Causality itself. "This metric spiked when that one did" is correlation; separating cause from symptom needs actual causal/temporal methods (Granger, changepoint, dependency graphs), not a vibes-based guess from a language model.
- Deciding what's safe to *run*. Tool permissions, read-vs-write boundaries, blast-radius limits — that's code and policy, not prompt.

**What stays genuinely hard:**
- Grounding in messy, real telemetry: dropped metrics, clock skew, sampling, and cascades that look like the cause. Detection in the lab ≠ detection under a retry storm.
- Trust and autonomy: an agent that executes commands in prod is powerful and terrifying. Auditability, interruptibility, and reversibility aren't features — they're the license to operate.
- Convergence: keeping an agent from burning 15 turns chasing a dead end (turn-budget governance helps, but efficient investigation is an open problem).

**How to take it from here:**
- Pluggable provider abstraction so the same engine runs on CloudWatch, Datadog, X-Ray, GitHub — not one vendor.
- Separate the model's job (produce data) from the UI's job (choose the visualization) to kill chart-type hallucination.
- Treat RCA as a *scored* problem against labeled incidents (see the sibling project, Dataraft) — otherwise you can't tell a good agent from a confident one.

**Products this could become:**
- An "AI on-call" copilot that drafts the RCA and the remediation plan before a human joins.
- A post-incident engine that writes the timeline + blast radius automatically.
- A causal-RCA layer that sits under existing observability stacks.

**To go deeper, look up:** Granger causality, Bayesian Online Changepoint Detection, the AIOps / incident-management literature, Datadog Watchdog, and the ReAct agent paper.

The takeaway: **the leap isn't a chatbot that describes your infra — it's an agent that investigates it, backed by statistics that actually find causes, and governed tightly enough to let it act.**

#SRE #AIOps #DevOps #Observability #IncidentManagement #AIAgents #RCA
