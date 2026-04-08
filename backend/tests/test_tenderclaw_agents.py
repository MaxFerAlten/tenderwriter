"""Tests for orchestration agents."""

import pytest

from backend.orchestration.agents import AgentRegistry, AgentResult

import backend.orchestration.agents.sisyphus
import backend.orchestration.agents.prometheus
import backend.orchestration.agents.hephaestus
import backend.orchestration.agents.oracle
import backend.orchestration.agents.explore
import backend.orchestration.agents.librarian
import backend.orchestration.agents.atlas
import backend.orchestration.agents.metis
import backend.orchestration.agents.momus


class TestAgentRegistry:
    """Tests for agent registry."""

    def test_list_agents(self):
        """Test listing registered agents."""
        agents = AgentRegistry.list_agents()
        assert "sisyphus" in agents
        assert "prometheus" in agents
        assert "hephaestus" in agents
        assert "oracle" in agents

    def test_get_agent(self):
        """Test getting an agent by name."""
        sisyphus = AgentRegistry.get("sisyphus")
        assert sisyphus is not None
        assert sisyphus.name == "sisyphus"

    def test_get_unknown_agent(self):
        """Test getting an unknown agent raises error."""
        with pytest.raises(ValueError, match="Unknown agent"):
            AgentRegistry.get("unknown-agent")


class TestSisyphusAgent:
    """Tests for Sisyphus agent."""

    @pytest.mark.asyncio
    async def test_execute(self):
        """Test Sisyphus execution."""
        sisyphus = AgentRegistry.get("sisyphus")
        result = await sisyphus.execute("Test task")
        assert isinstance(result, AgentResult)
        assert result.success is True


class TestPrometheusAgent:
    """Tests for Prometheus agent."""

    @pytest.mark.asyncio
    async def test_execute(self):
        """Test Prometheus execution."""
        prometheus = AgentRegistry.get("prometheus")
        result = await prometheus.execute("Plan a feature")
        assert isinstance(result, AgentResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_interview_mode(self):
        """Test Prometheus interview mode."""
        prometheus = AgentRegistry.get("prometheus")
        result = await prometheus.execute(
            "Plan a feature",
            context={"interview": True}
        )
        assert isinstance(result, AgentResult)
        assert "Interview questions" in result.content


class TestHephaestusAgent:
    """Tests for Hephaestus agent."""

    @pytest.mark.asyncio
    async def test_execute(self):
        """Test Hephaestus execution."""
        hephaestus = AgentRegistry.get("hephaestus")
        result = await hephaestus.execute("Implement a feature")
        assert isinstance(result, AgentResult)
        assert result.success is True


class TestOracleAgent:
    """Tests for Oracle agent."""

    @pytest.mark.asyncio
    async def test_execute(self):
        """Test Oracle execution."""
        oracle = AgentRegistry.get("oracle")
        result = await oracle.execute("Review this code")
        assert isinstance(result, AgentResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_code_review(self):
        """Test Oracle code review."""
        oracle = AgentRegistry.get("oracle")
        result = await oracle.execute(
            "Review this code",
            context={"type": "code"}
        )
        assert isinstance(result, AgentResult)
        assert "Code Review" in result.content
