# Tasks: Enhanced Slack Bot Event Organizer AI Agent

**Input**: Design documents from `/specs/002-slack-bot-ai/`
**Prerequisites**: plan_ja.md, research.md, data-model.md, contracts/, quickstart.md

## Execution Flow (main)
```
1. Load plan_ja.md from feature directory
   → Extract: Python 3.11+, ADK, Poetry, GCP Cloud Run
   → Structure: single project (src/, tests/)
2. Load design documents:
   → data-model.md: 6 entities → model tasks
   → contracts/: 3 files → contract test tasks
   → quickstart.md: 4 scenarios → integration tests
3. Generate tasks by category:
   → Setup: Poetry, ADK, GCP, linting
   → Tests: contract tests, integration tests
   → Core: models, agents, services
   → Integration: Slack, Google APIs, Firestore
   → Polish: unit tests, performance, docs
4. Apply agent implementation order from plan:
   → Coordination → Participant → Scheduling → Venue → Calendar
5. Number tasks sequentially (T001-T050)
6. Mark [P] for independent files
```

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Include exact file paths in descriptions

## Path Conventions
Single project structure (from plan_ja.md):
- **Source**: `src/models/`, `src/agents/`, `src/integrations/`, `src/cli/`
- **Tests**: `tests/contract/`, `tests/integration/`, `tests/unit/`

## Phase 3.1: Infrastructure Setup ✅ COMPLETED

- [x] **T001** ✅ Create project structure with Poetry and Python 3.11+ in pyproject.toml
- [x] **T002** ✅ Initialize ADK agent framework dependencies in pyproject.toml
- [x] **T003** ✅ [P] Configure Ruff linting and formatting in pyproject.toml
- [x] **T004** ✅ [P] Create GCP Cloud Run Dockerfile with Poetry and Python 3.11
- [x] **T005** ✅ [P] Initialize Firestore database schema setup script in scripts/init_firestore.py
- [x] **T006** ✅ [P] Create environment configuration template in .env.example

## Phase 3.2: Contract Tests (TDD) ✅ COMPLETED
**CRITICAL: These tests MUST be written and MUST FAIL before ANY implementation**

### Slack Events API Contract Tests
- [x] **T007** ✅ [P] Contract test Slack Event API verification in tests/contract/test_slack_events_verification.py
- [x] **T008** ✅ [P] Contract test Bot mention events in tests/contract/test_slack_bot_mentions.py
- [x] **T009** ✅ [P] Contract test Direct message events in tests/contract/test_slack_direct_messages.py
- [x] **T010** ✅ [P] Contract test Thread reply events in tests/contract/test_slack_thread_replies.py

### Event Coordination API Contract Tests
- [x] **T011** ✅ [P] Contract test POST /events creation in tests/contract/test_event_creation.py
- [x] **T012** ✅ [P] Contract test GET /events listing in tests/contract/test_event_listing.py
- [x] **T013** ✅ [P] Contract test PATCH /events/{id} updates in tests/contract/test_event_updates.py
- [x] **T014** ✅ [P] Contract test POST /events/{id}/participants in tests/contract/test_participant_management.py
- [x] **T015** ✅ [P] Contract test POST /events/{id}/scheduling in tests/contract/test_scheduling_coordination.py

### External APIs Contract Tests
- [x] **T016** ✅ [P] Contract test Google Calendar event creation in tests/contract/test_google_calendar.py
- [x] **T017** ✅ [P] Contract test Google Places venue search in tests/contract/test_google_places.py
- [x] **T018** ✅ [P] Contract test ぐるなび venue search in tests/contract/test_gurume_navi.py

### Integration Tests from Quickstart Scenarios
- [x] **T019** ✅ [P] Integration test basic dining event workflow in tests/integration/test_dining_event_workflow.py
- [x] **T020** ✅ [P] Integration test meeting room booking workflow in tests/integration/test_study_event_workflow.py
- [x] **T021** ✅ [P] Integration test intermediate confirmations in tests/integration/test_intermediate_confirmations.py
- [x] **T022** ✅ [P] Integration test error handling and fallbacks in tests/integration/test_error_handling.py

## Phase 3.3: Data Models ✅ COMPLETED

- [x] **T023** ✅ [P] Event entity model with state machine in src/models/event.py
- [x] **T024** ✅ [P] Participant entity model with validation in src/models/participant.py
- [x] **T025** ✅ [P] Venue entity model with booking status in src/models/venue.py
- [x] **T026** ✅ [P] CalendarEntry entity model in src/models/calendar_entry.py
- [x] **T027** ✅ [P] CoordinationSession entity model in src/models/coordination_session.py
- [x] **T028** ✅ [P] IntermediateConfirmation entity model in src/models/intermediate_confirmation.py
- [x] **T029** ✅ [P] Firestore repository base class in src/models/repository.py

## Phase 3.4: Agent Implementation ✅ COMPLETED

### Coordination Agent (Foundation)
- [x] **T030** ✅ Coordination Agent with ADK event bus orchestration in src/agents/coordination_agent.py
- [x] **T031** ✅ Agent communication interfaces and protocols in src/agents/base_agent.py

### Participant Agent (Independent)
- [x] **T032** ✅ Participant Agent with DM workflow management in src/agents/participant_agent.py

### Scheduling Agent (Depends on Participant data)
- [x] **T033** ✅ Scheduling Agent with time slot optimization in src/agents/scheduling_agent.py

### Venue Agent (Depends on confirmed schedule)
- [x] **T034** ✅ Venue Agent with multi-API search and fallback in src/agents/venue_agent.py

### Calendar Agent (Final integration)
- [x] **T035** ✅ Calendar Agent with Google Workspace integration in src/agents/calendar_agent.py

## Phase 3.5: External API Integrations ✅ COMPLETED

- [x] **T036** ✅ [P] Slack Bolt SDK event handler in src/integrations/slack_handler.py
- [x] **T037** ✅ [P] Google Calendar API OAuth integration in src/integrations/google_calendar.py
- [x] **T038** ✅ [P] Google Places API integration with rate limiting in src/integrations/google_places.py
- [x] **T039** ✅ [P] ぐるなび API integration with error handling in src/integrations/gurume_navi.py
- [x] **T040** ✅ [P] Firestore connection and transaction handling in src/integrations/firestore_client.py

## Phase 3.6: CLI Tools for Testing ✅ COMPLETED

- [x] **T041** ✅ [P] Event coordination CLI for testing in src/cli/event_cli.py
- [x] **T042** ✅ [P] Participant simulation CLI in src/cli/participant_simulator.py
- [x] **T043** ✅ [P] Venue search testing CLI in src/cli/venue_search_cli.py
- [x] **T044** ✅ [P] Calendar integration testing CLI in src/cli/calendar_cli.py

## Phase 3.7: CI/CD Pipeline

- [ ] **T045** [P] GitHub Actions CI workflow for tests and linting in .github/workflows/ci.yml
- [ ] **T046** [P] Auto-deploy workflow for main branch in .github/workflows/auto-deploy.yml
- [ ] **T047** [P] Manual deploy workflow in .github/workflows/manual-deploy.yml
- [ ] **T048** [P] Release drafter workflow in .github/workflows/release-drafter.yml

## Phase 3.8: Polish and Documentation

- [ ] **T049** [P] Unit tests for agent coordination logic in tests/unit/test_agent_coordination.py
- [ ] **T050** Performance validation and optimization for 500ms target response time
- [ ] **T051** [P] Update documentation and deployment guide in docs/deployment.md
- [x] **T052** [P] Cleanup and remove development scaffolding code ✅

## Dependencies

### Critical Path Dependencies
```
Setup (T001-T006) → Contract Tests (T007-T022) → Models (T023-T029) → Agents (T030-T035)
```

### Agent Implementation Dependencies (Sequential)
```
T030 (Coordination) → T031 (Interfaces) → T032 (Participant) → T033 (Scheduling) → T034 (Venue) → T035 (Calendar)
```

### Integration Dependencies
```
T023-T029 (Models) → T036-T040 (Integrations)
T030-T035 (Agents) → T041-T044 (CLI Tools)
```

## Parallel Execution Examples

### Contract Tests (Run Together)
```
Task: "Contract test Slack Event API verification in tests/contract/test_slack_events_verification.py"
Task: "Contract test Bot mention events in tests/contract/test_slack_bot_mentions.py"
Task: "Contract test Direct message events in tests/contract/test_slack_direct_messages.py"
Task: "Contract test Google Calendar event creation in tests/contract/test_google_calendar.py"
```

### Data Models (Run Together After Tests)
```
Task: "Event entity model with state machine in src/models/event.py"
Task: "Participant entity model with validation in src/models/participant.py"
Task: "Venue entity model with booking status in src/models/venue.py"
Task: "CalendarEntry entity model in src/models/calendar_entry.py"
```

### External Integrations (Run Together)
```
Task: "Slack Bolt SDK event handler in src/integrations/slack_handler.py"
Task: "Google Calendar API OAuth integration in src/integrations/google_calendar.py"
Task: "Google Places API integration with rate limiting in src/integrations/google_places.py"
Task: "ぐるなび API integration with error handling in src/integrations/gurume_navi.py"
```

## Task Generation Summary

**Total Tasks**: 52 | **Completed**: 44 (84.6%) | **Remaining**: 8 (15.4%)

### Completed Phases ✅
- **Setup**: 6/6 tasks ✅ COMPLETED
- **Contract Tests**: 16/16 tasks ✅ COMPLETED [P]
- **Data Models**: 7/7 tasks ✅ COMPLETED [P]
- **Agent Implementation**: 6/6 tasks ✅ COMPLETED (sequential)
- **External Integrations**: 5/5 tasks ✅ COMPLETED [P]
- **CLI Tools**: 4/4 tasks ✅ COMPLETED [P]

### Remaining Phases 🔄
- **CI/CD Pipeline**: 0/4 tasks [P] ⚠️ **NEXT PHASE**
- **Polish**: 0/4 tasks [P]

## Validation Checklist ✅

- [x] All contracts (3 files) have corresponding tests (T007-T018)
- [x] All entities (6 entities) have model tasks (T023-T028)
- [x] All tests (T007-T022) come before implementation (T023+)
- [x] Parallel tasks [P] are truly independent (different files)
- [x] Each task specifies exact file path
- [x] No [P] task modifies same file as another [P] task
- [x] Agent implementation follows dependency order from plan_ja.md
- [x] TDD approach enforced with failing tests before implementation

## Notes

- **[P] tasks** = different files, no dependencies, can run in parallel
- **Sequential tasks** follow agent dependency order: Coordination → Participant → Scheduling → Venue → Calendar
- **Verify tests fail** before implementing (T023 onwards)
- **Commit after each task** to maintain clean development history
- **ADK framework** provides event bus for agent coordination
- **Poetry** manages dependencies and virtual environment
- **GCP Cloud Run** deployment with Firestore backend