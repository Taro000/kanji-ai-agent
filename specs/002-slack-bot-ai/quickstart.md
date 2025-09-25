# Quickstart: Enhanced Slack Bot Event Organizer AI Agent

## Overview
This quickstart validates the core event coordination workflow through integration tests that mirror real user scenarios from the feature specification.

## Prerequisites
- Python 3.11+ with Poetry installed
- GCP project with Firestore enabled
- Slack workspace with bot permissions
- Google Workspace domain (for calendar and meeting room integration)
- Test environment variables configured

## Environment Setup

### 1. Install Dependencies
```bash
poetry install
poetry shell
```

### 2. Configure Environment Variables
```bash
cp .env.example .env
# Edit .env with your credentials
```

Required environment variables:
```
# Slack Configuration
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret
SLACK_APP_TOKEN=xapp-your-app-token

# Google API Configuration
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json
GOOGLE_CALENDAR_DOMAIN=your-workspace-domain.com

# GCP Configuration
GCP_PROJECT_ID=your-project-id
FIRESTORE_DATABASE=(default)

# External APIs
GOOGLE_PLACES_API_KEY=your-places-api-key
GURUME_NAVI_API_KEY=your-gurume-api-key

# Testing
TEST_SLACK_CHANNEL=C1234567890
TEST_ORGANIZER_USER=U1234567890
TEST_PARTICIPANT_USERS=U1111111111,U2222222222,U3333333333
```

### 3. Initialize Database
```bash
poetry run python scripts/init_firestore.py
```

## Quick Validation Tests

### Test 1: Basic Event Creation (Dining Event)
**User Story**: Organizer creates a dining event with participant mentions

```bash
# Run the integration test
poetry run pytest tests/integration/test_dining_event_workflow.py::test_basic_dining_event -v

# Expected flow:
# 1. Bot receives mention: "@eventbot 今度チームでランチしませんか @user1 @user2 @user3"
# 2. Bot identifies event type as "dining"
# 3. Bot asks organizer about required features and intermediate confirmations
# 4. Bot sends DMs to participants for confirmation
# 5. Bot conducts schedule coordination via DM
# 6. Bot searches for restaurants using Google Places + ぐるなび
# 7. Bot presents venue options to organizer (if intermediate confirmation enabled)
# 8. Bot makes booking attempt (manual fallback expected)
# 9. Bot creates Google Calendar events for participants
# 10. Bot announces final event details in channel
```

**Validation Points**:
- ✅ Slack event parsing and bot mention detection
- ✅ Event type classification (dining)
- ✅ Participant identification from mentions
- ✅ DM-based participant confirmation workflow
- ✅ Schedule coordination with time slot proposals
- ✅ Venue search integration (Google Places + ぐるなび)
- ✅ Manual booking fallback workflow
- ✅ Google Calendar integration with OAuth
- ✅ Final channel announcement

### Test 2: Meeting Room Reservation (Study Event)
**User Story**: Organizer schedules a study session requiring meeting room

```bash
poetry run pytest tests/integration/test_study_event_workflow.py::test_meeting_room_booking -v

# Expected flow:
# 1. Bot receives mention: "@eventbot 来週勉強会をしたいです @channel"
# 2. Bot identifies event type as "study"
# 3. Bot determines required features: scheduling + meeting room booking + calendar
# 4. Bot sends DMs to all channel members for availability
# 5. Bot finds optimal time slots based on responses
# 6. Bot searches available Google Workspace meeting rooms
# 7. Bot books meeting room automatically
# 8. Bot creates calendar events with meeting room resource
# 9. Bot announces event with meeting room details
```

**Validation Points**:
- ✅ @channel mention handling and channel member enumeration
- ✅ Study event type detection and feature determination
- ✅ Mass DM coordination for large participant groups
- ✅ Google Workspace meeting room API integration
- ✅ Automatic meeting room booking without manual intervention
- ✅ Calendar events with room resource booking

### Test 3: Intermediate Confirmation Workflow
**User Story**: Organizer enables intermediate confirmations for schedule and venue

```bash
poetry run pytest tests/integration/test_intermediate_confirmations.py::test_schedule_venue_confirmation -v

# Expected flow:
# 1. Bot asks organizer about intermediate confirmation preferences
# 2. Organizer enables both schedule and venue confirmations
# 3. Bot proposes 10-20 time slot options in thread
# 4. Organizer selects preferred time slot
# 5. Bot completes participant scheduling for selected time
# 6. Bot proposes 5-10 venue options in thread
# 7. Organizer selects preferred venue
# 8. Bot proceeds with booking selected venue
```

**Validation Points**:
- ✅ Thread-based intermediate confirmation UI
- ✅ Schedule option generation (10-20 options)
- ✅ Venue option presentation (5-10 options with details)
- ✅ Organizer selection handling and workflow continuation
- ✅ Context preservation between confirmation steps

### Test 4: Error Handling and Fallback Workflows
**User Story**: External APIs fail and manual fallback is triggered

```bash
poetry run pytest tests/integration/test_error_handling.py::test_api_failure_fallback -v

# Expected flow:
# 1. Venue search APIs fail or return no results
# 2. Bot detects failure and initiates fallback workflow
# 3. Bot notifies organizer in thread with options: [主催者が代わりに行う/スキップ]
# 4. Organizer chooses "主催者が代わりに行う"
# 5. Bot provides manual booking instructions and venue research
# 6. Organizer completes manual booking and reports back to bot
# 7. Bot continues workflow with organizer-provided venue details
```

**Validation Points**:
- ✅ API failure detection and circuit breaker activation
- ✅ Manual fallback workflow initiation
- ✅ Organizer notification and choice presentation
- ✅ Manual task completion tracking
- ✅ Workflow resumption after manual intervention

## Performance Validation

### Load Test: Concurrent Event Coordination
```bash
# Test 10 concurrent events across different channels
poetry run pytest tests/performance/test_concurrent_events.py -v

# Validates:
# - Multi-agent coordination under load
# - Firestore transaction handling
# - API rate limit management
# - Memory usage with multiple active sessions
```

### Response Time Test: API Integration
```bash
# Test API response times within constraints
poetry run pytest tests/performance/test_api_response_times.py -v

# Validates:
# - Google Calendar API calls < 2 seconds
# - Venue search APIs < 3 seconds
# - Slack API calls < 1 second
# - Overall workflow completion < 5 minutes for simple events
```

## Manual Testing Scenarios

### Complete End-to-End Test
1. **Setup**: Create test Slack channel with bot and 3-4 test users
2. **Execute**: Post message: `@eventbot 来週の金曜日にチームビルディングのために飲み会をしませんか？ @user1 @user2 @user3`
3. **Interact**: Respond to all DMs and confirmations as different users
4. **Verify**: Check that final event appears in all participants' Google Calendars
5. **Validate**: Confirm venue booking instructions or confirmation

### Edge Case Testing
1. **No Participant Response**: Test timeout handling when participants don't respond to DMs
2. **Schedule Conflicts**: Test with participants who have conflicting calendar events
3. **Venue Booking Failure**: Test when all venue APIs return errors
4. **OAuth Expiration**: Test calendar integration when user tokens expire

## Success Criteria
All tests must pass with the following metrics:
- ✅ 100% core workflow completion rate
- ✅ < 500ms average API response time
- ✅ < 5% external API failure rate with graceful fallback
- ✅ All calendar events created successfully
- ✅ All manual fallback workflows complete successfully
- ✅ No data loss during error conditions
- ✅ Proper cleanup of test data

## Troubleshooting

### Common Issues
1. **Firestore Connection**: Verify GCP credentials and project ID
2. **Slack Events**: Check bot permissions and Event Subscriptions URL
3. **Google Calendar**: Verify OAuth scopes and domain-wide delegation
4. **API Keys**: Confirm all external API keys are valid and have sufficient quota

### Debug Mode
```bash
export LOG_LEVEL=DEBUG
poetry run pytest tests/integration/ -v -s
```

### Test Data Cleanup
```bash
poetry run python scripts/cleanup_test_data.py
```

## Next Steps
After successful quickstart validation:
1. Run full test suite: `poetry run pytest`
2. Deploy to staging environment
3. Configure production monitoring and alerting
4. Set up CI/CD pipeline for automated testing