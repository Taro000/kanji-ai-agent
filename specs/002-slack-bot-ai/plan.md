
# Implementation Plan: Enhanced Slack Bot Event Organizer AI Agent

**Branch**: `002-slack-bot-ai` | **Date**: 2025-09-21 | **Spec**: [spec_ja.md](./spec_ja.md)
**Input**: Feature specification from `/specs/002-slack-bot-ai/spec_ja.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path
   → If not found: ERROR "No feature spec at {path}"
2. Fill Technical Context (scan for NEEDS CLARIFICATION)
   → Detect Project Type from context (web=frontend+backend, mobile=app+api)
   → Set Structure Decision based on project type
3. Fill the Constitution Check section based on the content of the constitution document.
4. Evaluate Constitution Check section below
   → If violations exist: Document in Complexity Tracking
   → If no justification possible: ERROR "Simplify approach first"
   → Update Progress Tracking: Initial Constitution Check
5. Execute Phase 0 → research.md
   → If NEEDS CLARIFICATION remain: ERROR "Resolve unknowns"
6. Execute Phase 1 → contracts, data-model.md, quickstart.md, agent-specific template file (e.g., `CLAUDE.md` for Claude Code, `.github/copilot-instructions.md` for GitHub Copilot, or `GEMINI.md` for Gemini CLI).
7. Re-evaluate Constitution Check section
   → If new violations: Refactor design, return to Phase 1
   → Update Progress Tracking: Post-Design Constitution Check
8. Plan Phase 2 → Describe task generation approach (DO NOT create tasks.md)
9. STOP - Ready for /tasks command
```

**IMPORTANT**: The /plan command STOPS at step 7. Phases 2-4 are executed by other commands:
- Phase 2: /tasks command creates tasks.md
- Phase 3-4: Implementation execution (manual or via tools)

## Summary
A Slack Bot AI Agent that autonomously organizes group events (drinking parties, lunches, study sessions) by handling participant confirmation via DM, scheduling coordination, venue booking, Google Calendar integration, and meeting room reservations. Built using Agent Development Kit (ADK) with multi-agent architecture deployed on GCP Cloud Run.

## Technical Context
**Language/Version**: Python 3.11+
**Primary Dependencies**: Agent Development Kit (ADK), Slack Bolt SDK, Google Calendar API, Google Places API, ぐるなびAPI
**Storage**: GCP Firestore for event state management and participant data
**Testing**: pytest with type hints using typing module
**Target Platform**: GCP Cloud Run (containerized deployment)
**Project Type**: single (backend service)
**Performance Goals**: Handle 100+ concurrent event coordination sessions, <500ms API response times
**Constraints**: Multi-agent coordination, OAuth2.0 integration, real-time Slack interactions
**Scale/Scope**: Support 1000+ Slack workspaces, manage 10k+ events monthly
**Package Manager**: Poetry
**Code Quality**: Ruff for linting and formatting
**Architecture**: Multi-agent system with sub-agents for specialized tasks

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Library-First Principle**: ✅ Each component (Slack handler, Calendar integration, Venue search) will be standalone libraries
**CLI Interface**: ✅ All libraries expose CLI commands for testing and debugging
**Test-First**: ✅ TDD approach with contract tests for external APIs, unit tests for business logic
**Integration Testing**: ✅ Focus on Slack API, Google Calendar API, and venue search API integrations
**Type Safety**: ✅ Python typing module for all function signatures and data models
**Observability**: ✅ Structured logging for multi-agent coordination and external API calls
**Simplicity**: ✅ Start with core event coordination, defer advanced features

## Project Structure

### Documentation (this feature)
```
specs/[###-feature]/
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (/plan command)
├── data-model.md        # Phase 1 output (/plan command)
├── quickstart.md        # Phase 1 output (/plan command)
├── contracts/           # Phase 1 output (/plan command)
└── tasks.md             # Phase 2 output (/tasks command - NOT created by /plan)
```

### Source Code (repository root)
```
# Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure]
```

**Structure Decision**: [DEFAULT to Option 1 unless Technical Context indicates web/mobile app]

## Phase 0: Outline & Research
1. **Extract unknowns from Technical Context** above:
   - For each NEEDS CLARIFICATION → research task
   - For each dependency → best practices task
   - For each integration → patterns task

2. **Generate and dispatch research agents**:
   ```
   For each unknown in Technical Context:
     Task: "Research {unknown} for {feature context}"
   For each technology choice:
     Task: "Find best practices for {tech} in {domain}"
   ```

3. **Consolidate findings** in `research.md` using format:
   - Decision: [what was chosen]
   - Rationale: [why chosen]
   - Alternatives considered: [what else evaluated]

**Output**: research.md with all NEEDS CLARIFICATION resolved

## Phase 1: Design & Contracts
*Prerequisites: research.md complete*

1. **Extract entities from feature spec** → `data-model.md`:
   - Entity name, fields, relationships
   - Validation rules from requirements
   - State transitions if applicable

2. **Generate API contracts** from functional requirements:
   - For each user action → endpoint
   - Use standard REST/GraphQL patterns
   - Output OpenAPI/GraphQL schema to `/contracts/`

3. **Generate contract tests** from contracts:
   - One test file per endpoint
   - Assert request/response schemas
   - Tests must fail (no implementation yet)

4. **Extract test scenarios** from user stories:
   - Each story → integration test scenario
   - Quickstart test = story validation steps

5. **Update agent file incrementally** (O(1) operation):
   - Run `.specify/scripts/bash/update-agent-context.sh claude` for your AI assistant
   - If exists: Add only NEW tech from current plan
   - Preserve manual additions between markers
   - Update recent changes (keep last 3)
   - Keep under 150 lines for token efficiency
   - Output to repository root

**Output**: data-model.md, /contracts/*, failing tests, quickstart.md, agent-specific file

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
- Load `.specify/templates/tasks-template.md` as base
- Generate tasks from Phase 1 design docs (contracts, data model, quickstart)
- Multi-agent coordination tasks with ADK framework setup
- External API integration tasks with contract tests
- TDD implementation tasks following library-first principle

**Specific Task Categories**:
1. **Infrastructure Setup** [P]:
   - ADK agent framework initialization
   - Firestore database schema setup
   - Poetry project configuration with dependencies
   - Docker containerization for Cloud Run

2. **Contract Test Tasks** [P]:
   - Slack Events API contract tests (slack_events.yaml)
   - Event Coordination API contract tests (event_coordination.yaml)
   - External APIs contract tests (external_apis.yaml)
   - Mock servers for external API testing

3. **Data Model Implementation** [P]:
   - Event entity with state machine validation
   - Participant entity with confirmation workflows
   - Venue entity with booking status tracking
   - Calendar integration entities
   - Firestore repository implementations

4. **Agent Implementation** (Sequential due to coordination dependencies):
   - Coordination Agent (orchestrator with ADK event bus)
   - Participant Agent (DM workflow management)
   - Scheduling Agent (time slot optimization algorithms)
   - Venue Agent (multi-API search with fallback)
   - Calendar Agent (OAuth2.0 + Google Workspace integration)

5. **Integration Tasks**:
   - Slack Bolt SDK event handling
   - Google Calendar API with OAuth delegation
   - Google Places API with rate limiting
   - ぐるなびAPI with error handling
   - Multi-agent coordination via ADK event system

6. **User Story Implementation**:
   - Dining event end-to-end workflow
   - Study/meeting event with room booking
   - Intermediate confirmation workflows
   - Error handling and manual fallback scenarios

7. **CLI Tools** [P]:
   - Event coordination CLI for testing
   - Participant simulation CLI
   - Venue search testing CLI
   - Calendar integration testing CLI

**Ordering Strategy**:
- TDD order: Contract tests → Models → Agents → Integration tests
- Dependency order: Infrastructure → Data layer → Business logic → External integrations
- Mark [P] for parallel execution (independent files/agents)
- Sequential tasks for inter-agent coordination logic

**Estimated Output**: 35-40 numbered, ordered tasks in tasks.md
- Infrastructure: 5 tasks
- Contract tests: 8 tasks [P]
- Data models: 6 tasks [P]
- Agent implementation: 12 tasks (partially sequential)
- External integrations: 6 tasks
- CLI tools: 4 tasks [P]
- Documentation/deployment: 3 tasks

**Task Dependencies**:
- All contract tests can run in parallel
- Data models depend on database setup
- Agents depend on data models and ADK setup
- External integrations depend on agent framework
- Integration tests depend on all components

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)  
**Phase 4**: Implementation (execute tasks.md following constitutional principles)  
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
*Fill ONLY if Constitution Check has violations that must be justified*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |


## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command)
- [x] Phase 1: Design complete (/plan command)
- [x] Phase 2: Task planning complete (/plan command - describe approach only)
- [ ] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [ ] Complexity deviations documented

---
*Based on Constitution v2.1.1 - See `/memory/constitution.md`*
