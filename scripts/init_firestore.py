#!/usr/bin/env python3
"""
Initialize Firestore database schema for Slack Bot Event Organizer.

This script creates the necessary collections, indexes, and security rules
for the event coordination system.
"""

import asyncio
import logging
import os
from typing import Any, Dict, List

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FirestoreSchemaInitializer:
    """Initialize Firestore database schema and indexes."""

    def __init__(self, project_id: str | None = None) -> None:
        """Initialize with GCP project ID."""
        self.project_id = project_id or os.getenv("GCP_PROJECT_ID")
        if not self.project_id:
            raise ValueError("GCP_PROJECT_ID environment variable must be set")

        self.db = firestore.Client(project=self.project_id)

    def create_collections(self) -> None:
        """Create main collections with initial documents."""
        collections = [
            "events",
            "coordination_sessions",
            "user_preferences",
            "audit_logs"
        ]

        for collection_name in collections:
            # Create collection with a placeholder document
            doc_ref = self.db.collection(collection_name).document("_placeholder")
            doc_ref.set({
                "created_at": firestore.SERVER_TIMESTAMP,
                "description": f"Placeholder document for {collection_name} collection",
                "delete_after_first_real_document": True
            })
            logger.info(f"Created collection: {collection_name}")

    def create_indexes(self) -> None:
        """Create composite indexes for efficient queries."""
        # Note: Composite indexes must be created via gcloud CLI or Firebase Console
        # This method documents the required indexes

        required_indexes = [
            {
                "collection": "events",
                "fields": [
                    {"field": "channel_id", "order": "ASCENDING"},
                    {"field": "status", "order": "ASCENDING"},
                    {"field": "created_at", "order": "DESCENDING"}
                ]
            },
            {
                "collection": "events",
                "fields": [
                    {"field": "organizer_id", "order": "ASCENDING"},
                    {"field": "status", "order": "ASCENDING"},
                    {"field": "updated_at", "order": "DESCENDING"}
                ]
            },
            {
                "collection": "coordination_sessions",
                "fields": [
                    {"field": "event_id", "order": "ASCENDING"},
                    {"field": "current_phase", "order": "ASCENDING"},
                    {"field": "last_activity", "order": "DESCENDING"}
                ]
            }
        ]

        logger.info("Required composite indexes (create via gcloud CLI):")
        for idx in required_indexes:
            fields_str = ", ".join([f"{f['field']} {f['order']}" for f in idx["fields"]])
            logger.info(f"  {idx['collection']}: {fields_str}")

    def create_security_rules(self) -> None:
        """Document Firestore security rules."""
        rules = """
        rules_version = '2';
        service cloud.firestore {
          match /databases/{database}/documents {
            // Events collection - workspace-based access
            match /events/{eventId} {
              allow read, write: if request.auth != null
                && resource.data.workspace_id == request.auth.token.workspace_id;
            }

            // User preferences - user-specific access
            match /user_preferences/{userId} {
              allow read, write: if request.auth != null
                && request.auth.uid == userId;
            }

            // Coordination sessions - event-based access
            match /coordination_sessions/{sessionId} {
              allow read, write: if request.auth != null
                && exists(/databases/$(database)/documents/events/$(resource.data.event_id))
                && get(/databases/$(database)/documents/events/$(resource.data.event_id)).data.workspace_id == request.auth.token.workspace_id;
            }

            // Audit logs - read-only for authorized users
            match /audit_logs/{logId} {
              allow read: if request.auth != null;
              allow write: if false; // Only server can write audit logs
            }
          }
        }
        """

        logger.info("Firestore Security Rules (deploy via Firebase Console):")
        logger.info(rules)

    def setup_ttl_policies(self) -> None:
        """Document TTL (Time To Live) policies for automatic cleanup."""
        ttl_policies = [
            {
                "collection": "coordination_sessions",
                "field": "expires_at",
                "description": "Auto-delete sessions after 30 days of inactivity"
            },
            {
                "collection": "events",
                "field": "completed_at",
                "description": "Auto-delete completed events after 90 days"
            },
            {
                "collection": "audit_logs",
                "field": "created_at",
                "description": "Auto-delete audit logs after 1 year"
            }
        ]

        logger.info("TTL Policies (configure via GCP Console):")
        for policy in ttl_policies:
            logger.info(f"  {policy['collection']}.{policy['field']}: {policy['description']}")

    def validate_connection(self) -> bool:
        """Validate Firestore connection and permissions."""
        try:
            # Test write permission
            test_doc = self.db.collection("_test").document("connection_test")
            test_doc.set({"timestamp": firestore.SERVER_TIMESTAMP})

            # Test read permission
            doc = test_doc.get()
            if not doc.exists:
                logger.error("Failed to read test document")
                return False

            # Cleanup test document
            test_doc.delete()
            logger.info("Firestore connection validated successfully")
            return True

        except Exception as e:
            logger.error(f"Firestore connection validation failed: {e}")
            return False

    def initialize_schema(self) -> bool:
        """Run complete schema initialization."""
        logger.info(f"Initializing Firestore schema for project: {self.project_id}")

        try:
            # Validate connection first
            if not self.validate_connection():
                return False

            # Create collections
            self.create_collections()

            # Document required indexes
            self.create_indexes()

            # Document security rules
            self.create_security_rules()

            # Document TTL policies
            self.setup_ttl_policies()

            logger.info("Firestore schema initialization completed successfully")
            logger.info("Remember to:")
            logger.info("1. Create composite indexes via gcloud CLI")
            logger.info("2. Deploy security rules via Firebase Console")
            logger.info("3. Configure TTL policies via GCP Console")

            return True

        except Exception as e:
            logger.error(f"Schema initialization failed: {e}")
            return False


def main() -> None:
    """Main entry point for schema initialization."""
    import sys

    # Check for required environment variables
    project_id = os.getenv("GCP_PROJECT_ID")
    if not project_id:
        logger.error("GCP_PROJECT_ID environment variable must be set")
        sys.exit(1)

    # Initialize schema
    initializer = FirestoreSchemaInitializer(project_id)
    success = initializer.initialize_schema()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()