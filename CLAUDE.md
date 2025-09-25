# Claude Code Context

## Project Overview
Enhanced Slack Bot Event Organizer AI Agent - An autonomous event coordination system built with Agent Development Kit (ADK) that handles group event planning including participant confirmation, scheduling, venue booking, and calendar integration.

## Current Implementation Status
- **Phase**: Planning Complete (Phase 1)
- **Branch**: 002-slack-bot-ai
- **Architecture**: Multi-agent system with specialized sub-agents
- **Deployment**: GCP Cloud Run with Firestore backend

## Technology Stack
- **Language**: Python 3.11+ with typing
- **Framework**: Agent Development Kit (ADK)
- **APIs**: Slack Bolt SDK, Google Calendar API, Google Places API, ぐるなびAPI
- **Storage**: GCP Firestore
- **Deployment**: GCP Cloud Run
- **Tools**: Poetry, Ruff, pytest

## Core Architecture
```
Coordination Agent (orchestrator)
├── Participant Agent (DM interactions, confirmations)
├── Scheduling Agent (calendar coordination, time optimization)
├── Venue Agent (restaurant/venue search and booking)
└── Calendar Agent (Google Calendar integration, meeting rooms)
```

## Key Features
1. **Slack Integration**: Bot mentions, DM workflows, thread confirmations
2. **Multi-Event Types**: Dining (restaurants), Study/Meeting (meeting rooms)
3. **Participant Management**: Automatic confirmation via DM, availability tracking
4. **Smart Scheduling**: Event-type appropriate time slot generation
5. **Venue Coordination**: Multi-API venue search with manual fallback
6. **Calendar Integration**: OAuth2.0, automatic event creation, meeting room booking
7. **Intermediate Confirmations**: Optional organizer approval for schedule/venue
8. **Error Resilience**: Circuit breaker pattern, manual fallback workflows

## Recent Implementation Plans
- **Data Model**: Comprehensive entity design with state management
- **API Contracts**: Slack events, event coordination, external API integration
- **Test Strategy**: TDD approach with contract, unit, and integration tests
- **Deployment**: Containerized ADK agents on Cloud Run

## Development Guidelines
- **Testing**: Write tests before implementation (TDD)
- **Code Quality**: Use Ruff for formatting, typing for all functions
- **Architecture**: Library-first approach, CLI interfaces for testing
- **Error Handling**: Graceful degradation with user notification
- **Security**: Encrypt OAuth tokens, PII protection, audit trails

## Recent Changes
- Completed planning phase with research, data model, and contracts
- Defined multi-agent coordination architecture
- Established external API integration patterns
- Created comprehensive test scenarios and quickstart validation

## TODO (Next Phase)
- Generate detailed implementation tasks (/tasks command)
- Implement core agent coordination framework
- Build Slack event handling and DM workflow
- Integrate Google Calendar and venue search APIs
- Create comprehensive test suite
- Set up deployment pipeline

## Project Structure
```
specs/002-slack-bot-ai/
├── plan.md              # Implementation plan
├── research.md          # Technical research and decisions
├── data-model.md        # Entity definitions and relationships
├── quickstart.md        # Integration test scenarios
└── contracts/           # API contracts (OpenAPI specs)

src/                     # Future implementation
├── agents/              # ADK agent implementations
├── integrations/        # External API wrappers
├── models/              # Data model classes
└── cli/                 # CLI tools for testing
```

Keep context under 150 lines for token efficiency.