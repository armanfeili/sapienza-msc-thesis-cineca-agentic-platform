"""
Tools repository for PostgreSQL CRUD operations.

Provides database access layer for tools, tool_invocations, and tool_audit_events
with idempotency, pagination, and audit trail support.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, exc, or_
from sqlalchemy.orm import Session

from db.postgres_control.models.tool import Tool
from db.postgres_control.models.tool_audit_event import ToolAuditEvent
from db.postgres_control.models.tool_invocation import ToolInvocation


class ToolsRepository:
    """Repository for tools CRUD operations with PostgreSQL."""

    def __init__(self, db: Session):
        """
        Initialize repository with database session.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    # ===== Tool Management =====

    @staticmethod
    def generate_tool_id() -> str:
        """
        Generate unique tool ID (UUID).

        Returns:
            Tool ID string (UUID)
        """
        return str(uuid.uuid4())

    @staticmethod
    def compute_tool_etag(tool: Tool) -> str:
        """
        Compute stable ETag from tool data.

        Args:
            tool: Tool model instance

        Returns:
            ETag string (quoted hex hash)
        """
        data = f"{tool.id}:{tool.updated_at.isoformat()}:{tool.version_number}"
        hash_digest = hashlib.sha256(data.encode()).hexdigest()[:16]
        return f'"{hash_digest}"'

    def create_tool(
        self,
        name: str,
        version: str,
        input_schema: dict[str, Any],
        owner_tenant_id: str,
        description: str | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> tuple[Tool, bool]:
        """
        Create a new tool with idempotency support.

        If tool with same (name, version) exists:
        - If all fields match: returns (existing_tool, False) [idempotent]
        - If fields differ: raises ValueError

        Args:
            name: Tool name
            version: Tool version (semver)
            input_schema: JSON schema for inputs
            owner_tenant_id: Owning tenant ID
            description: Tool description (optional)
            output_schema: JSON schema for outputs (optional)

        Returns:
            Tuple of (tool, created)

        Raises:
            ValueError: If tool exists with different configuration
        """
        # Check for existing tool
        existing = self.get_tool_by_name_version(name, version)

        if existing:
            # Check idempotency
            conflicts = {}

            if existing.input_schema != input_schema:
                conflicts["input_schema"] = {"existing": existing.input_schema, "requested": input_schema}

            if existing.output_schema != output_schema:
                conflicts["output_schema"] = {"existing": existing.output_schema, "requested": output_schema}

            if existing.description != description:
                conflicts["description"] = {"existing": existing.description, "requested": description}

            if existing.owner_tenant_id != owner_tenant_id:
                conflicts["owner_tenant_id"] = {"existing": existing.owner_tenant_id, "requested": owner_tenant_id}

            if conflicts:
                raise ValueError(
                    f"Tool '{name}' version '{version}' already exists with different configuration", conflicts
                )

            return existing, False

        # Create new tool
        tool_id = self.generate_tool_id()
        new_tool = Tool(
            id=tool_id,
            name=name,
            version=version,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            owner_tenant_id=owner_tenant_id,
        )

        try:
            self.db.add(new_tool)
            self.db.commit()
            self.db.refresh(new_tool)
            return new_tool, True
        except exc.IntegrityError as e:
            self.db.rollback()
            # Race condition - re-check
            existing = self.get_tool_by_name_version(name, version)
            if existing:
                # Validate idempotency again
                conflicts = {}
                if existing.input_schema != input_schema:
                    conflicts["input_schema"] = {"existing": existing.input_schema, "requested": input_schema}
                if existing.output_schema != output_schema:
                    conflicts["output_schema"] = {"existing": existing.output_schema, "requested": output_schema}
                if existing.description != description:
                    conflicts["description"] = {"existing": existing.description, "requested": description}
                if existing.owner_tenant_id != owner_tenant_id:
                    conflicts["owner_tenant_id"] = {"existing": existing.owner_tenant_id, "requested": owner_tenant_id}

                if conflicts:
                    raise ValueError(
                        f"Tool '{name}' version '{version}' already exists with different configuration", conflicts
                    )
                return existing, False

            raise ValueError(f"Database integrity error: {e}")

    def get_tool_by_id(self, tool_id: str) -> Tool | None:
        """
        Retrieve tool by ID.

        Args:
            tool_id: Tool identifier

        Returns:
            Tool model or None
        """
        return self.db.query(Tool).filter(Tool.id == tool_id).first()

    def get_tool_by_name_version(self, name: str, version: str) -> Tool | None:
        """
        Retrieve tool by name and version.

        Args:
            name: Tool name
            version: Tool version

        Returns:
            Tool model or None
        """
        return self.db.query(Tool).filter(Tool.name == name, Tool.version == version).first()

    def list_tools(
        self, owner_tenant_id: str | None = None, page_size: int = 100, page_token: str | None = None
    ) -> tuple[list[Tool], str | None, int]:
        """
        List tools with pagination.

        Args:
            owner_tenant_id: Filter by owner tenant (optional)
            page_size: Number of items per page
            page_token: Pagination token

        Returns:
            Tuple of (items, next_page_token, total_count)
        """
        # Base query
        query = self.db.query(Tool)

        if owner_tenant_id:
            query = query.filter(Tool.owner_tenant_id == owner_tenant_id)

        # Total count
        total = query.count()

        # Order by created_at DESC, id ASC
        query = query.order_by(Tool.created_at.desc(), Tool.id.asc())

        # Pagination (keyset)
        if page_token:
            try:
                parts = page_token.split("|", 1)
                if len(parts) == 2:
                    last_created_str, last_id = parts
                    last_created = datetime.fromisoformat(last_created_str)

                    query = query.filter(
                        or_(Tool.created_at < last_created, and_(Tool.created_at == last_created, Tool.id > last_id))
                    )
            except (ValueError, AttributeError):
                pass

        items = query.limit(page_size + 1).all()
        has_more = len(items) > page_size
        if has_more:
            items = items[:page_size]
            last = items[-1]
            next_token = f"{last.created_at.isoformat()}|{last.id}"
        else:
            next_token = None

        return items, next_token, total

    def update_tool(
        self,
        tool_id: str,
        description: str | None = None,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> Tool | None:
        """
        Update tool fields.

        Args:
            tool_id: Tool identifier
            description: New description (optional)
            input_schema: New input schema (optional)
            output_schema: New output schema (optional)

        Returns:
            Updated tool or None
        """
        tool = self.get_tool_by_id(tool_id)
        if not tool:
            return None

        if description is not None:
            tool.description = description
        if input_schema is not None:
            tool.input_schema = input_schema
        if output_schema is not None:
            tool.output_schema = output_schema

        try:
            self.db.commit()
            self.db.refresh(tool)
            return tool
        except exc.IntegrityError as e:
            self.db.rollback()
            raise ValueError(f"Update failed: {e}")

    def delete_tool(self, tool_id: str) -> bool:
        """
        Delete tool by ID.

        Args:
            tool_id: Tool identifier

        Returns:
            True if deleted, False if not found
        """
        tool = self.get_tool_by_id(tool_id)
        if not tool:
            return False

        self.db.delete(tool)
        self.db.commit()
        return True

    # ===== Tool Invocation Management =====

    @staticmethod
    def generate_invocation_eid() -> str:
        """
        Generate unique execution ID (UUID).

        Returns:
            Execution ID string
        """
        return str(uuid.uuid4())

    @staticmethod
    def compute_invocation_etag(invocation: ToolInvocation) -> str:
        """
        Compute stable ETag from invocation data.

        Args:
            invocation: ToolInvocation model instance

        Returns:
            ETag string (quoted hex hash)
        """
        data = f"{invocation.eid}:{invocation.status}:{invocation.started_at.isoformat()}"
        if invocation.completed_at:
            data += f":{invocation.completed_at.isoformat()}"
        hash_digest = hashlib.sha256(data.encode()).hexdigest()[:16]
        return f'"{hash_digest}"'

    def create_invocation(
        self,
        tool_name: str,
        tool_version: str,
        tenant_id: str,
        params: dict[str, Any],
        requested_by: str | None = None,
        idempotency_key: str | None = None,
        request_headers: dict[str, Any] | None = None,
    ) -> tuple[ToolInvocation, bool]:
        """
        Create tool invocation with idempotency support.

        If idempotency_key is provided and exists:
        - If params match: returns (existing, False) [idempotent]
        - If params differ: raises ValueError (409 conflict)

        Args:
            tool_name: Tool name
            tool_version: Tool version
            tenant_id: Tenant ID
            params: Tool input parameters
            requested_by: User/service that requested invocation
            idempotency_key: Client idempotency key (optional)
            request_headers: Request headers (optional)

        Returns:
            Tuple of (invocation, created)

        Raises:
            ValueError: If idempotency key exists with different params
        """
        # Check idempotency
        if idempotency_key:
            existing = self.get_invocation_by_idempotency_key(idempotency_key)
            if existing:
                # Validate params match
                if existing.params_json != params:
                    raise ValueError(
                        f"Idempotency key '{idempotency_key}' already used with different parameters",
                        {"existing_params": existing.params_json, "requested_params": params},
                    )
                return existing, False

        # Create new invocation
        eid = self.generate_invocation_eid()
        new_invocation = ToolInvocation(
            eid=eid,
            tool_name=tool_name,
            tool_version=tool_version,
            tenant_id=tenant_id,
            status="pending",
            params_json=params,
            requested_by=requested_by,
            idempotency_key=idempotency_key,
            request_headers=request_headers,
        )

        try:
            self.db.add(new_invocation)
            self.db.commit()
            self.db.refresh(new_invocation)

            # Append audit event
            self.append_audit_event(
                eid=eid,
                event_type="invocation_created",
                payload={
                    "tool_name": tool_name,
                    "tool_version": tool_version,
                    "tenant_id": tenant_id,
                    "requested_by": requested_by,
                },
            )

            return new_invocation, True
        except exc.IntegrityError as e:
            self.db.rollback()
            # Race condition on idempotency_key
            if idempotency_key:
                existing = self.get_invocation_by_idempotency_key(idempotency_key)
                if existing:
                    if existing.params_json != params:
                        raise ValueError(
                            f"Idempotency key '{idempotency_key}' already used with different parameters",
                            {"existing_params": existing.params_json, "requested_params": params},
                        )
                    return existing, False

            raise ValueError(f"Database integrity error: {e}")

    def get_invocation_by_eid(self, eid: str) -> ToolInvocation | None:
        """
        Retrieve invocation by execution ID.

        Args:
            eid: Execution ID

        Returns:
            ToolInvocation model or None
        """
        return self.db.query(ToolInvocation).filter(ToolInvocation.eid == eid).first()

    def get_invocation_by_idempotency_key(self, idempotency_key: str) -> ToolInvocation | None:
        """
        Retrieve invocation by idempotency key.

        Args:
            idempotency_key: Idempotency key

        Returns:
            ToolInvocation model or None
        """
        return self.db.query(ToolInvocation).filter(ToolInvocation.idempotency_key == idempotency_key).first()

    def list_invocations(
        self,
        tenant_id: str | None = None,
        tool_name: str | None = None,
        status: str | None = None,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> tuple[list[ToolInvocation], str | None, int]:
        """
        List invocations with filtering and pagination.

        Args:
            tenant_id: Filter by tenant (optional)
            tool_name: Filter by tool name (optional)
            status: Filter by status (optional)
            page_size: Number of items per page
            page_token: Pagination token

        Returns:
            Tuple of (items, next_page_token, total_count)
        """
        query = self.db.query(ToolInvocation)

        if tenant_id:
            query = query.filter(ToolInvocation.tenant_id == tenant_id)
        if tool_name:
            query = query.filter(ToolInvocation.tool_name == tool_name)
        if status:
            query = query.filter(ToolInvocation.status == status)

        total = query.count()

        # Order by started_at DESC, eid ASC
        query = query.order_by(ToolInvocation.started_at.desc(), ToolInvocation.eid.asc())

        # Pagination
        if page_token:
            try:
                parts = page_token.split("|", 1)
                if len(parts) == 2:
                    last_started_str, last_eid = parts
                    last_started = datetime.fromisoformat(last_started_str)

                    query = query.filter(
                        or_(
                            ToolInvocation.started_at < last_started,
                            and_(ToolInvocation.started_at == last_started, ToolInvocation.eid > last_eid),
                        )
                    )
            except (ValueError, AttributeError):
                pass

        items = query.limit(page_size + 1).all()
        has_more = len(items) > page_size
        if has_more:
            items = items[:page_size]
            last = items[-1]
            next_token = f"{last.started_at.isoformat()}|{last.eid}"
        else:
            next_token = None

        return items, next_token, total

    def update_invocation_status(
        self,
        eid: str,
        status: str,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        latency_ms: int | None = None,
    ) -> ToolInvocation | None:
        """
        Update invocation status and result.

        Args:
            eid: Execution ID
            status: New status
            result: Result data (optional)
            error: Error data (optional)
            latency_ms: Execution latency (optional)

        Returns:
            Updated invocation or None
        """
        invocation = self.get_invocation_by_eid(eid)
        if not invocation:
            return None

        old_status = invocation.status
        invocation.status = status

        if result is not None:
            invocation.result_json = result
        if error is not None:
            invocation.error_json = error
        if latency_ms is not None:
            invocation.latency_ms = latency_ms

        # Set completed_at for terminal states
        if status in ("finished", "failed", "cancelled"):
            invocation.completed_at = datetime.now(UTC)

        try:
            self.db.commit()
            self.db.refresh(invocation)

            # Append audit event
            self.append_audit_event(
                eid=eid,
                event_type="status_changed",
                payload={
                    "old_status": old_status,
                    "new_status": status,
                    "latency_ms": latency_ms,
                },
            )

            return invocation
        except exc.IntegrityError as e:
            self.db.rollback()
            raise ValueError(f"Update failed: {e}")

    # ===== Audit Events =====

    def append_audit_event(self, eid: str, event_type: str, payload: dict[str, Any]) -> ToolAuditEvent:
        """
        Append audit event for invocation.

        Args:
            eid: Execution ID
            event_type: Event type (e.g., "invocation_created", "status_changed")
            payload: Event data

        Returns:
            Created audit event
        """
        event = ToolAuditEvent(
            eid=eid,
            event_type=event_type,
            payload_json=payload,
        )

        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)

        return event

    def get_audit_events(self, eid: str) -> list[ToolAuditEvent]:
        """
        Retrieve audit events for invocation.

        Args:
            eid: Execution ID

        Returns:
            List of audit events (ordered by created_at ASC)
        """
        return (
            self.db.query(ToolAuditEvent)
            .filter(ToolAuditEvent.eid == eid)
            .order_by(ToolAuditEvent.created_at.asc())
            .all()
        )


__all__ = ["ToolsRepository"]
