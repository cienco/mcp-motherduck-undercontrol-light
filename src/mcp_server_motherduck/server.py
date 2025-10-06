import logging
from pydantic import AnyUrl
from typing import Literal
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from .configs import SERVER_VERSION
from .database import DatabaseClient
from .prompt import PROMPT_TEMPLATE, PIANIFICATORE_UI_PROMPT_NAME, PIANIFICATORE_UI_INITIAL_PROMPT


logger = logging.getLogger("mcp_server_motherduck")


def build_application(
    db_path: str,
    motherduck_token: str | None = None,
    home_dir: str | None = None,
    saas_mode: bool = False,
    read_only: bool = False,
):
    logger.info("Starting MotherDuck MCP Server")
    server = Server("pianificatore_ui")
    db_client = DatabaseClient(
        db_path=db_path,
        motherduck_token=motherduck_token,
        home_dir=home_dir,
        saas_mode=saas_mode,
        read_only=read_only,
    )

    logger.info("Registering handlers")

    @server.list_resources()
    async def handle_list_resources() -> list[types.Resource]:
        """
        List available note resources.
        Each note is exposed as a resource with a custom note:// URI scheme.
        """
        logger.info("No resources available to list")
        return []

    @server.read_resource()
    async def handle_read_resource(uri: AnyUrl) -> str:
        """
        Read a specific note's content by its URI.
        The note name is extracted from the URI host component.
        """
        logger.info(f"Reading resource: {uri}")
        raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

    @server.list_prompts()
    async def handle_list_prompts() -> list[types.Prompt]:
        """
        List available prompts.
        Each prompt can have optional arguments to customize its behavior.
        """
        logger.info("Listing prompts")
        # TODO: Check where and how this is used, and how to optimize this.
        # Check postgres and sqlite servers.
        return [
            types.Prompt(
                name=PIANIFICATORE_UI_PROMPT_NAME,
                description="Contesto iniziale e linee guida per pianificare e allocare risorse su progetti usando DuckDB/MotherDuck; include esempi di INSERT/UPDATE.",
            ),
            # Lasciamo disponibile anche il prompt generico DuckDB/MotherDuck
            types.Prompt(
                name="duckdb-motherduck-initial-prompt",
                description="Prompt iniziale per connettersi a DuckDB/MotherDuck e iniziare a lavorare.",
            ),
        ]

    @server.get_prompt()
    async def handle_get_prompt(
        name: str, arguments: dict[str, str] | None
    ) -> types.GetPromptResult:
        """
        Generate a prompt by combining arguments with server state.
        The prompt includes all current notes and can be customized via arguments.
        """
        logger.info(f"Getting prompt: {name}::{arguments}")
        # TODO: Check where and how this is used, and how to optimize this.
        # Check postgres and sqlite servers.
        if name == PIANIFICATORE_UI_PROMPT_NAME:
            return types.GetPromptResult(
                description="Prompt di avvio per pianificatore_ui: pianificazione risorse, viste, e INSERT/UPDATE consentiti.",
                messages=[
                    types.PromptMessage(
                        role="user",
                        content=types.TextContent(type="text", text=PIANIFICATORE_UI_INITIAL_PROMPT),
                    )
                ],
            )
        elif name == "duckdb-motherduck-initial-prompt":
            return types.GetPromptResult(
                description="Prompt iniziale per interagire con DuckDB/MotherDuck",
                messages=[
                    types.PromptMessage(
                        role="user",
                        content=types.TextContent(type="text", text=PROMPT_TEMPLATE),
                    )
                ],
            )
        else:
            raise ValueError(f"Unknown prompt: {name}")

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        """
        List available tools.
        Each tool specifies its arguments using JSON Schema validation.
        """
        logger.info("Listing tools")
        return [
            types.Tool(
                name="query",
                description="Esegui una query SQL (dialetto DuckDB) su MotherDuck/DuckDB. "
                            "Supporta SELECT/CTE e, se richiesto, anche INSERT/UPDATE sulle tabelle autorizzate.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Query SQL (DuckDB) da eseguire: SELECT/CTE e, se necessario, INSERT/UPDATE.",
                        },
                    },
                    "required": ["query"],
                },
            ),
        ]

    @server.call_tool()
    async def handle_tool_call(
        name: str, arguments: dict | None
    ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """
        Handle tool execution requests.
        Tools can modify server state and notify clients of changes.
        """
        logger.info(f"Calling tool: {name}::{arguments}")
        try:
            if name == "query":
                if arguments is None:
                    return [
                        types.TextContent(type="text", text="Error: No query provided")
                    ]
                tool_response = db_client.query(arguments["query"])
                return [types.TextContent(type="text", text=str(tool_response))]

            return [types.TextContent(type="text", text=f"Unsupported tool: {name}")]

        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}")
            raise ValueError(f"Error executing tool {name}: {str(e)}")

    initialization_options = InitializationOptions(
        server_name="motherduck",
        server_version=SERVER_VERSION,
        capabilities=server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={},
        ),
    )

    return server, initialization_options
