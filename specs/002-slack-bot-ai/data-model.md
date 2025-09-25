# Data Model: Enhanced Slack Bot Event Organizer AI Agent

## Core Entities

### Event
Represents a planned gathering with coordination workflow state.

**Fields**:
- `event_id`: str (UUID) - Unique event identifier
- `channel_id`: str - Slack channel where event was initiated
- `organizer_id`: str - Slack user ID of the organizer
- `event_type`: EventType - Type of event (DINING, STUDY, MEETING)
- `purpose`: str - Free-form description of event purpose
- `status`: EventStatus - Current coordination status
- `participants`: List[Participant] - List of invited participants
- `scheduled_datetime`: Optional[datetime] - Finalized event date/time
- `venue`: Optional[Venue] - Selected venue information
- `calendar_entries`: List[CalendarEntry] - Google Calendar event references
- `coordination_preferences`: CoordinationPreferences - User-selected workflow options
- `created_at`: datetime - Event creation timestamp
- `updated_at`: datetime - Last modification timestamp

**Relationships**:
- One-to-many with Participant
- One-to-one with Venue (optional)
- One-to-many with CalendarEntry
- One-to-one with CoordinationPreferences

**State Transitions**:
```
CREATED → COLLECTING_PARTICIPANTS → SCHEDULING → VENUE_SEARCH →
CALENDAR_BOOKING → FINAL_CONFIRMATION → ANNOUNCED → COMPLETED
```

**Validation Rules**:
- event_type must be valid EventType enum value
- organizer_id must be valid Slack user ID
- scheduled_datetime must be in the future when set
- At least one participant required for scheduling phase

### Participant
Represents a person invited to an event with their availability and preferences.

**Fields**:
- `participant_id`: str (UUID) - Unique participant identifier
- `event_id`: str - Reference to parent event
- `slack_user_id`: str - Slack user ID
- `participation_status`: ParticipationStatus - Confirmed, declined, or pending
- `available_time_slots`: List[TimeSlot] - User's available times
- `dietary_restrictions`: Optional[str] - Special dietary requirements
- `google_calendar_email`: Optional[str] - Email for calendar integration
- `oauth_token`: Optional[str] - Encrypted OAuth token for calendar access
- `dm_thread_ts`: Optional[str] - Slack DM thread timestamp for context
- `confirmed_at`: Optional[datetime] - When participation was confirmed
- `last_contacted_at`: Optional[datetime] - Last DM interaction timestamp

**Relationships**:
- Many-to-one with Event
- One-to-many with TimeSlot

**Validation Rules**:
- participation_status must be valid enum value
- google_calendar_email must be valid email format when provided
- oauth_token must be encrypted before storage

### Venue
Represents a restaurant, meeting room, or event location.

**Fields**:
- `venue_id`: str (UUID) - Unique venue identifier
- `event_id`: str - Reference to parent event
- `venue_type`: VenueType - Restaurant, meeting room, or external location
- `name`: str - Venue name
- `address`: str - Full address
- `google_places_id`: Optional[str] - Google Places API reference
- `gurume_id`: Optional[str] - ぐるなびAPI reference
- `capacity`: int - Maximum occupancy
- `booking_status`: BookingStatus - Pending, confirmed, or failed
- `booking_details`: Optional[str] - Confirmation numbers, special instructions
- `contact_phone`: Optional[str] - Venue contact information
- `menu_url`: Optional[str] - Menu or facility information URL
- `estimated_cost_per_person`: Optional[int] - Cost estimate in yen
- `booking_deadline`: Optional[datetime] - Last chance to modify booking

**Relationships**:
- One-to-one with Event

**Validation Rules**:
- venue_type must be valid VenueType enum value
- capacity must be positive integer
- estimated_cost_per_person must be non-negative when provided

### CalendarEntry
Represents a Google Calendar event created for the coordinated event.

**Fields**:
- `calendar_entry_id`: str (UUID) - Unique entry identifier
- `event_id`: str - Reference to parent event
- `google_event_id`: str - Google Calendar event ID
- `calendar_email`: str - Target calendar email address
- `event_title`: str - Calendar event title
- `event_description`: str - Detailed event description
- `start_time`: datetime - Event start time
- `end_time`: datetime - Event end time
- `location`: str - Event location (venue address)
- `attendee_emails`: List[str] - List of invited attendee emails
- `meeting_room_resource`: Optional[str] - Google Workspace meeting room resource ID
- `creation_status`: CalendarStatus - Success, failed, or pending
- `created_at`: datetime - Calendar entry creation timestamp

**Relationships**:
- Many-to-one with Event

**Validation Rules**:
- start_time must be before end_time
- calendar_email must be valid email format
- attendee_emails must contain valid email addresses

### CoordinationSession
Tracks the complete workflow instance and agent coordination state.

**Fields**:
- `session_id`: str (UUID) - Unique session identifier
- `event_id`: str - Reference to parent event
- `current_phase`: CoordinationPhase - Current workflow phase
- `active_agents`: List[str] - Currently running agent instances
- `intermediate_confirmations`: Dict[str, bool] - User preferences for confirmations
- `conversation_context`: Dict[str, Any] - Serialized conversation state
- `error_log`: List[ErrorEntry] - Failed operations and recovery actions
- `thread_ts`: str - Slack thread timestamp for organizer communication
- `last_activity`: datetime - Last agent activity timestamp
- `workflow_data`: Dict[str, Any] - Phase-specific data storage

**Relationships**:
- One-to-one with Event

**Validation Rules**:
- current_phase must be valid CoordinationPhase enum value
- thread_ts must be valid Slack timestamp format

### IntermediateConfirmation
Represents organizer approval checkpoints during coordination.

**Fields**:
- `confirmation_id`: str (UUID) - Unique confirmation identifier
- `event_id`: str - Reference to parent event
- `confirmation_type`: ConfirmationType - Schedule or venue confirmation
- `proposed_options`: List[Dict[str, Any]] - Options presented to organizer
- `selected_option`: Optional[Dict[str, Any]] - Organizer's choice
- `status`: ConfirmationStatus - Pending, approved, or rejected
- `thread_ts`: str - Slack thread where confirmation was requested
- `requested_at`: datetime - When confirmation was requested
- `responded_at`: Optional[datetime] - When organizer responded
- `feedback`: Optional[str] - Additional organizer feedback

**Relationships**:
- Many-to-one with Event

## Enums

### EventType
```python
class EventType(Enum):
    DINING = "dining"      # 飲み会・ランチ
    STUDY = "study"        # 勉強会
    MEETING = "meeting"    # 会議・MTG
```

### EventStatus
```python
class EventStatus(Enum):
    CREATED = "created"
    COLLECTING_PARTICIPANTS = "collecting_participants"
    SCHEDULING = "scheduling"
    VENUE_SEARCH = "venue_search"
    CALENDAR_BOOKING = "calendar_booking"
    FINAL_CONFIRMATION = "final_confirmation"
    ANNOUNCED = "announced"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"
```

### ParticipationStatus
```python
class ParticipationStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
    NO_RESPONSE = "no_response"
```

### VenueType
```python
class VenueType(Enum):
    RESTAURANT = "restaurant"
    MEETING_ROOM = "meeting_room"
    EXTERNAL = "external"
```

### BookingStatus
```python
class BookingStatus(Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    MANUAL_REQUIRED = "manual_required"
```

### CoordinationPhase
```python
class CoordinationPhase(Enum):
    INITIALIZATION = "initialization"
    PARTICIPANT_COLLECTION = "participant_collection"
    SCHEDULE_COORDINATION = "schedule_coordination"
    VENUE_COORDINATION = "venue_coordination"
    CALENDAR_INTEGRATION = "calendar_integration"
    FINAL_CONFIRMATION = "final_confirmation"
    ANNOUNCEMENT = "announcement"
    COMPLETED = "completed"
```

## Data Storage Strategy

### Firestore Collections

**events**: Primary event collection
- Document ID: event_id
- Subcollections: participants, calendar_entries, confirmations

**coordination_sessions**: Active workflow state
- Document ID: session_id
- TTL: 30 days for automatic cleanup

**user_preferences**: Cached user preferences and OAuth tokens
- Document ID: slack_user_id
- Encrypted storage for sensitive data

### Data Access Patterns

**By Event ID**: Primary lookup pattern for all event-related data
**By Channel ID**: Find active events in a specific Slack channel
**By Organizer ID**: Find events organized by a specific user
**By Participant ID**: Find events where user is a participant
**By Status**: Query events in specific coordination phases

### Data Consistency

**Strong Consistency**: Required for event state transitions and booking confirmations
**Eventual Consistency**: Acceptable for participant status updates and conversation logs
**Transactions**: Use Firestore transactions for critical state changes (booking confirmations, final event creation)

## Security Considerations

**PII Protection**: Encrypt participant email addresses and OAuth tokens
**Access Control**: Implement row-level security based on Slack workspace membership
**Data Retention**: Automatic cleanup of completed events after 90 days
**Audit Trail**: Log all data modifications with timestamp and initiating agent