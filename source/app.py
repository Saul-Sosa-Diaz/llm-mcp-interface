"""Chainlit-based LLM assistant with Model Context Protocol integration."""

import logging
import asyncio
import json
import os
from typing import Optional

import chainlit as cl
import httpx
from openai import AsyncOpenAI

from database import init_db, save_message, get_chat_history
from mcp_manager import connect_all_mcps, get_tools, call_tool

# Configuration
logger = logging.getLogger(__name__)

API_KEY = os.getenv("API_KEY", "")
BASE_URL = os.getenv("BASE_URL", "")
MODEL = os.getenv("MODEL", "Qwen/Qwen3-32B")

SYSTEM_PROMPT = """You are an advanced AI assistant with access to external tools via Model Context Protocol (MCP).
You can use available tools to fetch information, execute tasks, and access external services.
Always provide clear, concise responses and explain tool usage when applicable."""

# Initialize LLM client
http_client_config = httpx.Timeout(180.0, connect=30.0)
ai_assistant_client = AsyncOpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
    timeout=http_client_config,
)


class MCPLifecycleManager:
    """Manages MCP server connections during user session."""

    def __init__(self):
        self.stack = None
        self.sessions = []
        self.tools = []

    async def initialize(self) -> None:
        """Connect to MCP servers and discover available tools."""
        try:
            self.stack, self.sessions = await connect_all_mcps()
            self.tools = await get_tools(self.sessions)

            # Remove internal MCP metadata before sending to sever compatible with OpenAI SDK
            self.tools = [
                {k: v for k, v in tool.items() if k != "_mcp_server"}
                for tool in self.tools
            ]

            logger.info(f"MCP initialized with {len(self.tools)} tools")
        except Exception as e:
            logger.error(f"Failed to initialize MCP: {e}")
            self.tools = []

    async def cleanup(self) -> None:
        """Close MCP server connections."""
        if self.stack:
            try:
                await self.stack.aclose()
                logger.info("MCP connections closed")
            except Exception as e:
                logger.error(f"Error closing MCP connections: {e}")


async def _mcp_lifecycle(
    shutdown_event: asyncio.Event, ready_event: asyncio.Event
) -> None:
    """Manage MCP server lifecycle within session context.

    Args:
        shutdown_event: Signal to initiate shutdown.
        ready_event: Signal when initialization is complete.
    """
    lifecycle = MCPLifecycleManager()

    try:
        await lifecycle.initialize()
        cl.user_session.set("mcp_sessions", lifecycle.sessions)
        cl.user_session.set("mcp_tools", lifecycle.tools)
    except Exception as e:
        logger.exception("MCP initialization failed")
        cl.user_session.set("mcp_sessions", [])
        cl.user_session.set("mcp_tools", [])
        cl.user_session.set("mcp_error", str(e))
    finally:
        cl.user_session.set("mcp_lifecycle", lifecycle)
        ready_event.set()

    # Wait for shutdown signal
    await shutdown_event.wait()
    await lifecycle.cleanup()


@cl.on_chat_start
async def on_chat_start() -> None:
    """Initialize chat session with database and MCP tools."""
    # Initialize database
    await init_db()

    # Setup MCP lifecycle
    shutdown_event = asyncio.Event()
    ready_event = asyncio.Event()

    cl.user_session.set("shutdown_event", shutdown_event)

    # Start MCP lifecycle in background
    mcp_task = asyncio.create_task(_mcp_lifecycle(shutdown_event, ready_event))
    cl.user_session.set("mcp_task", mcp_task)

    # Wait for initialization
    await ready_event.wait()

    # Display status
    tools = cl.user_session.get("mcp_tools", [])
    if tools:
        tool_names = ", ".join([t["function"]["name"] for t in tools])
        await cl.Message(
            content=f"✓ MCP initialized with {len(tools)} tools: {tool_names}"
        ).send()
    else:
        error = cl.user_session.get("mcp_error")
        if error:
            await cl.Message(
                content=f"⚠ MCP initialization failed: {error}\nContinuing without tools."
            ).send()
        else:
            await cl.Message(content="✓ Chat ready (no MCP tools available)").send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    """Process user message and generate response using LLM and tools."""
    logger.info(f"Received message: {message.content}")

    session_id = cl.user_session.get("id")
    mcp_sessions = cl.user_session.get("mcp_sessions", [])
    tools = cl.user_session.get("mcp_tools", [])

    # Save user message
    await save_message(session_id, "user", message.content)

    # Retrieve conversation history
    history = await get_chat_history(session_id)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    # Create response placeholder
    response_message = cl.Message(content="")
    await response_message.send()

    try:
        # Call LLM with tools
        logger.debug("Calling LLM for initial response")
        completion = await ai_assistant_client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools if tools else None,
            tool_choice="auto" if tools else None,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )

        assistant_response = completion.choices[0].message
        tool_calls = assistant_response.tool_calls

        # Process tool calls if present
        if tool_calls:
            await _process_tool_calls(
                session_id,
                messages,
                tool_calls,
                mcp_sessions,
                response_message,
                assistant_response,
            )
        else:
            # Direct response without tools
            response_content = assistant_response.content or ""
            response_message.content = response_content
            await response_message.update()
            await save_message(session_id, "assistant", response_content)

    except Exception as e:
        logger.exception("Error processing message")
        error_message = f"Error: {str(e)}"
        response_message.content = error_message
        await response_message.update()


async def _process_tool_calls(
    session_id: str,
    messages: list,
    tool_calls: list,
    mcp_sessions: list,
    response_message: cl.Message,
    assistant_response,
) -> None:
    """Process and execute tool calls from LLM.

    Args:
        session_id: Chat session identifier.
        messages: Conversation message history.
        tool_calls: List of tool calls from LLM.
        mcp_sessions: Active MCP server sessions.
        response_message: Chainlit message to update.
        assistant_response: Original LLM response.
    """
    messages.append(assistant_response)
    await save_message(
        session_id,
        "assistant",
        assistant_response.content,
        tool_calls=[t.model_dump() for t in tool_calls],
    )

    # Execute each tool call
    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        tool_args = json.loads(tool_call.function.arguments)

        # Notify user of tool execution
        await cl.Message(
            author="System",
            content=f"Executing: `{tool_name}` with {json.dumps(tool_args, ensure_ascii=False)}",
        ).send()

        # Execute tool
        tool_result = await call_tool(mcp_sessions, tool_name, tool_args)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_name,
                "content": tool_result,
            }
        )
        await save_message(session_id, "tool", tool_result)

    # Generate final response after tool execution
    logger.debug("Calling LLM for final response after tool execution")
    final_completion = await ai_assistant_client.chat.completions.create(
        model=MODEL,
        messages=messages,
        stream=True,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )

    final_content = ""
    async for chunk in final_completion:
        delta = chunk.choices[0].delta.content
        if delta:
            final_content += delta
            await response_message.stream_token(delta)

    await save_message(session_id, "assistant", final_content)


@cl.on_chat_end
async def on_chat_end() -> None:
    """Clean up resources when chat session ends."""
    shutdown_event = cl.user_session.get("shutdown_event")
    if shutdown_event:
        shutdown_event.set()

    mcp_task = cl.user_session.get("mcp_task")
    if mcp_task:
        try:
            await asyncio.wait_for(mcp_task, timeout=5.0)
        except (asyncio.TimeoutError, Exception) as e:
            logger.debug(f"MCP task cleanup timeout or error: {e}")
