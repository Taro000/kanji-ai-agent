"""
Unit tests for agent coordination logic
Tests the core multi-agent communication and workflow orchestration
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from typing import List, Dict, Any
from unittest.mock import Mock, AsyncMock, patch

# Import project modules
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from src.agents.base_agent import BaseAgent, AgentMessage, MessageType, AgentCapability
from src.agents.coordination_agent import CoordinationAgent
from src.agents.participant_agent import ParticipantAgent
from src.agents.scheduling_agent import SchedulingAgent
from src.agents.venue_agent import VenueAgent
from src.agents.calendar_agent import CalendarAgent
from src.models.event import Event, EventType, EventStatus
from src.models.participant import Participant, ParticipationStatus
from src.models.coordination_session import CoordinationSession, CoordinationPhase, CoordinationStatus


class TestAgentCommunication:
    """Test agent communication protocols and message passing"""

    @pytest.fixture
    def coordination_agent(self):
        """Create coordination agent instance"""
        return CoordinationAgent()

    @pytest.fixture
    def participant_agent(self):
        """Create participant agent instance"""
        return ParticipantAgent()

    @pytest.fixture
    def test_message(self):
        """Create test message"""
        return AgentMessage(
            sender_id="test_sender",
            recipient_id="test_recipient",
            message_type=MessageType.EVENT_COORDINATION_START,
            conversation_id="test_conversation",
            payload={"test": "data"}
        )

    def test_agent_message_creation(self, test_message):
        """Test AgentMessage creation and validation"""
        assert test_message.sender_id == "test_sender"
        assert test_message.recipient_id == "test_recipient"
        assert test_message.message_type == MessageType.EVENT_COORDINATION_START
        assert test_message.conversation_id == "test_conversation"
        assert test_message.payload == {"test": "data"}
        assert isinstance(test_message.timestamp, datetime)

    def test_agent_capabilities(self, coordination_agent):
        """Test agent capabilities registration"""
        assert len(coordination_agent.capabilities) > 0

        # Verify coordination agent has required capabilities
        capability_names = [cap.name for cap in coordination_agent.capabilities]
        assert "event_workflow_orchestration" in capability_names
        assert "agent_communication_management" in capability_names

    @pytest.mark.asyncio
    async def test_message_routing(self, coordination_agent, test_message):
        """Test message routing between agents"""
        # Mock message handler
        mock_handler = AsyncMock(return_value=AgentMessage(
            sender_id="test_recipient",
            recipient_id="test_sender",
            message_type=MessageType.TASK_COMPLETED,
            conversation_id="test_conversation",
            payload={"status": "completed"}
        ))

        coordination_agent.message_handlers[MessageType.EVENT_COORDINATION_START] = mock_handler

        # Send message
        response = await coordination_agent.handle_message(test_message)

        # Verify handler was called
        mock_handler.assert_called_once_with(test_message)

        # Verify response
        assert response.sender_id == "test_recipient"
        assert response.message_type == MessageType.TASK_COMPLETED
        assert response.payload["status"] == "completed"

    @pytest.mark.asyncio
    async def test_message_serialization(self, test_message):
        """Test message serialization and deserialization"""
        # Serialize to dict
        message_dict = test_message.dict()

        # Verify all fields present
        required_fields = ["sender_id", "recipient_id", "message_type", "conversation_id", "payload", "timestamp"]
        for field in required_fields:
            assert field in message_dict

        # Deserialize back to object
        reconstructed = AgentMessage(**message_dict)

        # Verify reconstruction
        assert reconstructed.sender_id == test_message.sender_id
        assert reconstructed.message_type == test_message.message_type
        assert reconstructed.payload == test_message.payload


class TestWorkflowOrchestration:
    """Test multi-agent workflow orchestration"""

    @pytest.fixture
    def coordination_session(self):
        """Create test coordination session"""
        event = Event(
            event_id="test_event_001",
            title="Test Event",
            event_type=EventType.DINING,
            organizer_id="organizer_001",
            participants=[],
            status=EventStatus.PLANNING,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        return CoordinationSession(
            session_id="test_session_001",
            event_id="test_event_001",
            event=event,
            current_phase=CoordinationPhase.PARTICIPANT_CONFIRMATION,
            status=CoordinationStatus.IN_PROGRESS,
            agent_states={},
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

    @pytest.fixture
    def agents_system(self):
        """Create complete multi-agent system"""
        return {
            "coordination": CoordinationAgent(),
            "participant": ParticipantAgent(),
            "scheduling": SchedulingAgent(),
            "venue": VenueAgent(),
            "calendar": CalendarAgent()
        }

    @pytest.mark.asyncio
    async def test_workflow_phase_transitions(self, coordination_session, agents_system):
        """Test workflow phase transitions"""
        coordination_agent = agents_system["coordination"]

        # Mock phase completion
        with patch.object(coordination_agent, '_execute_participant_phase', new_callable=AsyncMock) as mock_participant:
            mock_participant.return_value = {"success": True, "confirmed_participants": 5}

            # Execute participant phase
            result = await coordination_agent._execute_coordination_phase(
                coordination_session, CoordinationPhase.PARTICIPANT_CONFIRMATION
            )

            assert result["success"] is True
            mock_participant.assert_called_once()

    @pytest.mark.asyncio
    async def test_agent_dependency_ordering(self, agents_system):
        """Test correct agent dependency ordering"""
        coordination_agent = agents_system["coordination"]

        # Test dependency graph
        dependencies = coordination_agent._get_agent_dependencies()

        # Verify coordination is root
        assert "coordination_agent" not in dependencies

        # Verify scheduling depends on participant
        assert "participant_agent" in dependencies.get("scheduling_agent", [])

        # Verify venue depends on scheduling
        assert "scheduling_agent" in dependencies.get("venue_agent", [])

        # Verify calendar depends on venue
        assert "venue_agent" in dependencies.get("calendar_agent", [])

    @pytest.mark.asyncio
    async def test_error_propagation(self, coordination_session, agents_system):
        """Test error handling and propagation between agents"""
        coordination_agent = agents_system["coordination"]

        # Mock agent failure
        with patch.object(coordination_agent, '_execute_scheduling_phase', new_callable=AsyncMock) as mock_scheduling:
            mock_scheduling.side_effect = Exception("Scheduling service unavailable")

            # Execute phase with error
            result = await coordination_agent._execute_coordination_phase(
                coordination_session, CoordinationPhase.SCHEDULE_COORDINATION
            )

            assert result["success"] is False
            assert "error" in result
            assert "Scheduling service unavailable" in result["error"]

    @pytest.mark.asyncio
    async def test_fallback_mechanisms(self, coordination_session, agents_system):
        """Test fallback mechanisms when agents fail"""
        venue_agent = agents_system["venue"]

        # Mock primary API failure with successful fallback
        with patch.object(venue_agent, '_search_google_places', new_callable=AsyncMock) as mock_google:
            with patch.object(venue_agent, '_search_gurume_navi', new_callable=AsyncMock) as mock_gurume:
                mock_google.side_effect = Exception("Google Places API error")
                mock_gurume.return_value = {"success": True, "results": [{"name": "Fallback Restaurant"}]}

                # Execute venue search
                from src.agents.base_agent import AgentMessage, MessageType
                message = AgentMessage(
                    sender_id="coordination_agent",
                    recipient_id="venue_agent",
                    message_type=MessageType.VENUE_SEARCH,
                    conversation_id="test_conversation",
                    payload={"event_type": "dining", "participant_count": 5}
                )

                response = await venue_agent.handle_message(message)

                # Verify fallback was used
                assert response.payload["success"] is True
                assert len(response.payload["venues"]) > 0


class TestPerformanceAndResilience:
    """Test performance characteristics and system resilience"""

    @pytest.fixture
    def performance_test_data(self):
        """Generate test data for performance testing"""
        participants = []
        for i in range(50):  # Test with 50 participants
            participant = Participant(
                participant_id=f"user_{i:03d}",
                name=f"Test User {i}",
                email=f"user{i}@example.com",
                slack_user_id=f"U{1000+i:04d}",
                status=ParticipationStatus.INVITED,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            participants.append(participant)

        return participants

    @pytest.mark.asyncio
    async def test_response_time_target(self, performance_test_data):
        """Test 500ms response time target"""
        coordination_agent = CoordinationAgent()

        # Create test event
        event = Event(
            event_id="perf_test_event",
            title="Performance Test Event",
            event_type=EventType.DINING,
            organizer_id="organizer_perf",
            participants=performance_test_data[:10],  # Limit to 10 for performance test
            status=EventStatus.PLANNING,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        # Mock fast responses from all agents
        with patch.object(coordination_agent, '_execute_participant_phase', new_callable=AsyncMock) as mock_participant:
            with patch.object(coordination_agent, '_execute_scheduling_phase', new_callable=AsyncMock) as mock_scheduling:
                with patch.object(coordination_agent, '_execute_venue_phase', new_callable=AsyncMock) as mock_venue:
                    with patch.object(coordination_agent, '_execute_calendar_phase', new_callable=AsyncMock) as mock_calendar:

                        # Configure mock responses
                        mock_participant.return_value = {"success": True, "confirmed_participants": 8}
                        mock_scheduling.return_value = {"success": True, "selected_schedule": {"start": datetime.now()}}
                        mock_venue.return_value = {"success": True, "selected_venue": {"name": "Test Venue"}}
                        mock_calendar.return_value = {"success": True, "calendar_event": {"id": "test_event"}}

                        # Measure coordination time
                        start_time = datetime.now()

                        session = CoordinationSession(
                            session_id="perf_test_session",
                            event_id=event.event_id,
                            event=event,
                            current_phase=CoordinationPhase.PARTICIPANT_CONFIRMATION,
                            status=CoordinationStatus.IN_PROGRESS,
                            agent_states={},
                            created_at=datetime.now(),
                            updated_at=datetime.now()
                        )

                        result = await coordination_agent._execute_full_coordination_workflow(session)

                        end_time = datetime.now()
                        response_time = (end_time - start_time).total_seconds() * 1000  # Convert to milliseconds

                        # Verify performance target
                        assert response_time < 500, f"Response time {response_time:.2f}ms exceeds 500ms target"
                        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_concurrent_coordination(self):
        """Test handling multiple concurrent coordination sessions"""
        coordination_agent = CoordinationAgent()

        # Create multiple concurrent sessions
        sessions = []
        for i in range(10):  # Test 10 concurrent sessions
            event = Event(
                event_id=f"concurrent_event_{i}",
                title=f"Concurrent Test Event {i}",
                event_type=EventType.DINING,
                organizer_id=f"organizer_{i}",
                participants=[],
                status=EventStatus.PLANNING,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )

            session = CoordinationSession(
                session_id=f"concurrent_session_{i}",
                event_id=event.event_id,
                event=event,
                current_phase=CoordinationPhase.PARTICIPANT_CONFIRMATION,
                status=CoordinationStatus.IN_PROGRESS,
                agent_states={},
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            sessions.append(session)

        # Mock agent responses for all sessions
        with patch.object(coordination_agent, '_execute_participant_phase', new_callable=AsyncMock) as mock_participant:
            mock_participant.return_value = {"success": True, "confirmed_participants": 5}

            # Execute all sessions concurrently
            start_time = datetime.now()

            tasks = [
                coordination_agent._execute_coordination_phase(session, CoordinationPhase.PARTICIPANT_CONFIRMATION)
                for session in sessions
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            end_time = datetime.now()
            total_time = (end_time - start_time).total_seconds()

            # Verify all sessions completed successfully
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    pytest.fail(f"Session {i} failed with exception: {result}")
                assert result["success"] is True

            # Verify concurrent processing was efficient
            assert total_time < 2.0, f"Concurrent processing took {total_time:.2f}s, expected < 2.0s"

    @pytest.mark.asyncio
    async def test_memory_efficiency(self, performance_test_data):
        """Test memory usage with large datasets"""
        import tracemalloc

        # Start memory tracking
        tracemalloc.start()

        coordination_agent = CoordinationAgent()

        # Process large participant list
        event = Event(
            event_id="memory_test_event",
            title="Memory Test Event",
            event_type=EventType.DINING,
            organizer_id="organizer_memory",
            participants=performance_test_data,  # All 50 participants
            status=EventStatus.PLANNING,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        session = CoordinationSession(
            session_id="memory_test_session",
            event_id=event.event_id,
            event=event,
            current_phase=CoordinationPhase.PARTICIPANT_CONFIRMATION,
            status=CoordinationStatus.IN_PROGRESS,
            agent_states={},
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        # Mock processing
        with patch.object(coordination_agent, '_execute_participant_phase', new_callable=AsyncMock) as mock_participant:
            mock_participant.return_value = {"success": True, "confirmed_participants": 40}

            await coordination_agent._execute_coordination_phase(session, CoordinationPhase.PARTICIPANT_CONFIRMATION)

        # Check memory usage
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Verify reasonable memory usage (< 100MB peak)
        peak_mb = peak / 1024 / 1024
        assert peak_mb < 100, f"Memory usage {peak_mb:.2f}MB exceeds 100MB limit"

    @pytest.mark.asyncio
    async def test_error_recovery(self):
        """Test system recovery from various error conditions"""
        coordination_agent = CoordinationAgent()

        # Test network timeout recovery
        with patch.object(coordination_agent, '_execute_venue_phase', new_callable=AsyncMock) as mock_venue:
            mock_venue.side_effect = [
                asyncio.TimeoutError("Network timeout"),
                {"success": True, "selected_venue": {"name": "Recovered Venue"}}
            ]

            session = CoordinationSession(
                session_id="recovery_test_session",
                event_id="recovery_test_event",
                event=Event(
                    event_id="recovery_test_event",
                    title="Recovery Test Event",
                    event_type=EventType.DINING,
                    organizer_id="organizer_recovery",
                    participants=[],
                    status=EventStatus.PLANNING,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                ),
                current_phase=CoordinationPhase.VENUE_SELECTION,
                status=CoordinationStatus.IN_PROGRESS,
                agent_states={},
                created_at=datetime.now(),
                updated_at=datetime.now()
            )

            # Should retry and succeed
            result = await coordination_agent._execute_coordination_phase_with_retry(
                session, CoordinationPhase.VENUE_SELECTION, max_retries=2
            )

            assert result["success"] is True
            assert mock_venue.call_count == 2  # Initial call + 1 retry


class TestIntegrationBoundaries:
    """Test integration points and boundary conditions"""

    @pytest.mark.asyncio
    async def test_agent_isolation(self):
        """Test that agents are properly isolated and don't share state"""
        agent1 = ParticipantAgent("participant_1")
        agent2 = ParticipantAgent("participant_2")

        # Modify state in agent1
        agent1._internal_state = {"test": "data"}

        # Verify agent2 is not affected
        assert not hasattr(agent2, '_internal_state') or agent2._internal_state != agent1._internal_state

    @pytest.mark.asyncio
    async def test_message_validation(self):
        """Test message validation and sanitization"""
        coordination_agent = CoordinationAgent()

        # Test invalid message type
        invalid_message = AgentMessage(
            sender_id="test_sender",
            recipient_id="coordination_agent",
            message_type="INVALID_TYPE",  # Invalid message type
            conversation_id="test_conversation",
            payload={}
        )

        with pytest.raises(ValueError):
            # Should raise validation error for invalid message type
            await coordination_agent.handle_message(invalid_message)

    @pytest.mark.asyncio
    async def test_payload_size_limits(self):
        """Test handling of large message payloads"""
        coordination_agent = CoordinationAgent()

        # Create large payload (simulate edge case)
        large_payload = {"data": "x" * 10000}  # 10KB payload

        message = AgentMessage(
            sender_id="test_sender",
            recipient_id="coordination_agent",
            message_type=MessageType.EVENT_COORDINATION_START,
            conversation_id="test_conversation",
            payload=large_payload
        )

        # Should handle large payloads gracefully
        response = await coordination_agent.handle_message(message)

        # Verify response is valid (not truncated or corrupted)
        assert isinstance(response, AgentMessage)
        assert response.conversation_id == "test_conversation"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])