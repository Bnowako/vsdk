#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  CallToolResult,
  Tool,
  ListResourcesRequestSchema,
  ListResourceTemplatesRequestSchema,
  ReadResourceRequestSchema
} from "@modelcontextprotocol/sdk/types.js";

import { Stagehand } from "@browserbasehq/stagehand";
import type { ConstructorParams, LogLine } from "@browserbasehq/stagehand";

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

// Get the directory name for the current module
const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Configure logging
const LOG_DIR = path.join(__dirname, '../logs');
const LOG_FILE = path.join(LOG_DIR, `stagehand-${new Date().toISOString().split('T')[0]}.log`);

// Ensure log directory exists
if (!fs.existsSync(LOG_DIR)) {
  fs.mkdirSync(LOG_DIR, { recursive: true });
}

// Helper function to convert LogLine to string
function logLineToString(logLine: LogLine): string {
  const timestamp = logLine.timestamp ? new Date(logLine.timestamp).toISOString() : new Date().toISOString();
  const level = logLine.level !== undefined ?
    (logLine.level === 0 ? 'DEBUG' :
     logLine.level === 1 ? 'INFO' :
     logLine.level === 2 ? 'ERROR' : 'UNKNOWN') : 'UNKNOWN';
  return `[${timestamp}] [${level}] ${logLine.message || ''}`;
}

// Define Stagehand configuration
const stagehandConfig: ConstructorParams = {
  env:
    process.env.BROWSERBASE_API_KEY && process.env.BROWSERBASE_PROJECT_ID
      ? "BROWSERBASE"
      : "LOCAL",
  apiKey: process.env.BROWSERBASE_API_KEY /* API key for authentication */,
  projectId: process.env.BROWSERBASE_PROJECT_ID /* Project identifier */,
  debugDom: false /* Enable DOM debugging features */,
  headless: false /* Run browser in headless mode */,
  logger: (message: LogLine) =>
    console.error(logLineToString(message)) /* Custom logging function to stderr */,
  domSettleTimeoutMs: 30_000 /* Timeout for DOM to settle in milliseconds */,
  browserbaseSessionCreateParams: {
    projectId: process.env.BROWSERBASE_PROJECT_ID!,
    browserSettings: process.env.CONTEXT_ID ? {
        context: {
          id: process.env.CONTEXT_ID,
          persist: true
        }
    } : undefined
  },
  enableCaching: true /* Enable caching functionality */,
  browserbaseSessionID:
    undefined /* Session ID for resuming Browserbase sessions */,
  modelName: "gpt-4o" /* Name of the model to use */,
  modelClientOptions: {
    apiKey: process.env.OPENAI_API_KEY,
  } /* Configuration options for the model client */,
  useAPI: false,
};

// Define the Stagehand tools
const TOOLS: Tool[] = [
  {
    name: "stagehand_navigate",
    description: "Navigate to a URL in the browser. Only use this tool with URLs you're confident will work and stay up to date. Otheriwse use https://google.com as the starting point",
    inputSchema: {
      type: "object",
      properties: {
        url: { type: "string", description: "The URL to navigate to" },
      },
      required: ["url"],
    },
  },
  {
    name: "stagehand_act",
    description: `Performs an action on a web page element. Act actions should be as atomic and
      specific as possible, i.e. "Click the sign in button" or "Type 'hello' into the search input".
      AVOID actions that are more than one step, i.e. "Order me pizza" or "Send an email to Paul
      asking him to call me". `,
    inputSchema: {
      type: "object",
      properties: {
        action: { type: "string", description: `The action to perform. Should be as atomic and specific as possible,
          i.e. 'Click the sign in button' or 'Type 'hello' into the search input'. AVOID actions that are more than one
          step, i.e. 'Order me pizza' or 'Send an email to Paul asking him to call me'. The instruction should be just as specific as possible,
          and have a strong correlation to the text on the page. If unsure, use observe before using act."` },
        variables: {
          type: "object",
          additionalProperties: true,
          description: `Variables used in the action template. ONLY use variables if you're dealing
            with sensitive data or dynamic content. For example, if you're logging in to a website,
            you can use a variable for the password. When using variables, you MUST have the variable
            key in the action template. For example: {"action": "Fill in the password", "variables": {"password": "123456"}}`,
        },
      },
      required: ["action"],
    },
  },
  {
    name: "stagehand_extract",
    description: `Extracts all of the text from the current page.`,
    inputSchema: {
      type: "object",
      properties: {},
    },
  },
  {
    name: "stagehand_observe",
    description: "Observes elements on the web page. Use this tool to observe elements that you can later use in an action. Use observe instead of extract when dealing with actionable (interactable) elements rather than text. More often than not, you'll want to use extract instead of observe when dealing with scraping or extracting structured text.",
    inputSchema: {
      type: "object",
      properties: {
        instruction: {
          type: "string",
          description: "Instruction for observation (e.g., 'find the login button'). This instruction must be extremely specific.",
        },
      },
      required: ["instruction"],
    },
  },
  {
    name: "screenshot",
    description: "Takes a screenshot of the current page. Use this tool to learn where you are on the page when controlling the browser with Stagehand. Only use this tool when the other tools are not sufficient to get the information you need.",
    inputSchema: {
      type: "object",
      properties: {},
    },
  },
];
// Global state
let stagehand: Stagehand | undefined;
let serverInstance: Server | undefined;
const operationLogs: string[] = [];
const screenshots = new Map<string, string>();

function log(message: string, level: 'info' | 'error' | 'debug' = 'info') {
  const timestamp = new Date().toISOString();
  const logMessage = `[${timestamp}] [${level.toUpperCase()}] ${message}`;
  operationLogs.push(logMessage);

  // Write to file
  fs.appendFileSync(LOG_FILE, logMessage + '\n');

  // Console output to stderr
  if (process.env.DEBUG || level === 'error') {
    console.error(logMessage);
  }

  // Send logging message to client for important events
  if (serverInstance && (level === 'info' || level === 'error')) {
    serverInstance.sendLoggingMessage({
      level: level,
      data: message,
    });
  }
}

function logRequest(type: string, params: any) {
  const requestLog = {
    timestamp: new Date().toISOString(),
    type,
    params,
  };
  log(`REQUEST: ${JSON.stringify(requestLog, null, 2)}`, 'debug');
}

function logResponse(type: string, response: any) {
  const responseLog = {
    timestamp: new Date().toISOString(),
    type,
    response,
  };
  log(`RESPONSE: ${JSON.stringify(responseLog, null, 2)}`, 'debug');
}

// Ensure Stagehand is initialized
async function ensureStagehand() {
  try {
    if (!stagehand) {
      stagehand = new Stagehand(stagehandConfig);
      await stagehand.init();
      return stagehand;
    }

    // Try to perform a simple operation to check if the session is still valid
    try {
      await stagehand.page.evaluate(() => document.title);
      return stagehand;
    } catch (error) {
      // If we get an error indicating the session is invalid, reinitialize
      if (error instanceof Error &&
          (error.message.includes('Target page, context or browser has been closed') ||
           error.message.includes('Session expired') ||
           error.message.includes('context destroyed'))) {
        log('Browser session expired, reinitializing Stagehand...', 'info');
        stagehand = new Stagehand(stagehandConfig);
        await stagehand.init();
        return stagehand;
      }
      throw error; // Re-throw if it's a different type of error
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    log(`Failed to initialize/reinitialize Stagehand: ${errorMsg}`, 'error');
    throw error;
  }
}

function sanitizeMessage(message: any): string {
  try {
    // Ensure the message is properly stringified JSON
    if (typeof message === 'string') {
      JSON.parse(message); // Validate JSON structure
      return message;
    }
    return JSON.stringify(message);
  } catch (error) {
    return JSON.stringify({
      jsonrpc: '2.0',
      error: {
        code: -32700,
        message: 'Parse error',
      },
      id: null,
    });
  }
}

// Handle tool calls
async function handleToolCall(
  name: string,
  args: any
): Promise<CallToolResult> {

  try {
    stagehand = await ensureStagehand();
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    return {
      content: [
        {
          type: "text",
          text: `Failed to initialize Stagehand: ${errorMsg}`,
        },
        {
          type: "text",
          text: `Operation logs:\n${operationLogs.join("\n")}`,
        },
      ],
      isError: true,
    };
  }



  switch (name) {
    case "stagehand_navigate":
      try {
        await stagehand.page.goto(args.url);
        return {
          content: [
            {
              type: "text",
              text: `Navigated to: ${args.url}`,
            },
            {
              type: "text",
              text: `View the live session here: https://browserbase.com/sessions/${stagehand.browserbaseSessionID}`,
            },
          ],
          isError: false,
        };
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error);
        return {
          content: [
            {
              type: "text",
              text: `Failed to navigate: ${errorMsg}`,
            },
            {
              type: "text",
              text: `Operation logs:\n${operationLogs.join("\n")}`,
            },
          ],
          isError: true,
        };
      }

    case "stagehand_act":
      try {
        await stagehand.page.act({
          action: args.action,
          variables: args.variables,
          slowDomBasedAct: false,
        });
        return {
          content: [
            {
              type: "text",
              text: `Action performed: ${args.action}`,
            },
          ],
          isError: false,
        };
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error);
        return {
          content: [
            {
              type: "text",
              text: `Failed to perform action: ${errorMsg}`,
            },
            {
              type: "text",
              text: `Operation logs:\n${operationLogs.join("\n")}`,
            },
          ],
          isError: true,
        };
      }

      case "stagehand_extract": {
        try {
          const bodyText = await stagehand.page.evaluate(() => document.body.innerText);
          const content = bodyText
            .split('\n')
            .map(line => line.trim())
            .filter(line => {
              if (!line) return false;

              if (
                  (line.includes('{') && line.includes('}')) ||
                  line.includes('@keyframes') ||                         // Remove CSS animations
                  line.match(/^\.[a-zA-Z0-9_-]+\s*{/) ||               // Remove CSS lines starting with .className {
                  line.match(/^[a-zA-Z-]+:[a-zA-Z0-9%\s\(\)\.,-]+;$/)  // Remove lines like "color: blue;" or "margin: 10px;"
                ) {
                return false;
              }
              return true;
            })
            .map(line => {
              return line.replace(/\\u([0-9a-fA-F]{4})/g, (_, hex) =>
                String.fromCharCode(parseInt(hex, 16))
              );
            });

          return {
            content: [
              {
                type: "text",
                text: `Extracted content:\n${content.join('\n')}`,
              },
            ],
            isError: false,
          };
        } catch (error) {
          return {
            content: [
              {
                type: "text",
                text: `Failed to extract content: ${(error as Error).message}`,
              },
            ],
            isError: true,
          };
        }
      }

    case "stagehand_observe":
      try {
        const observations = await stagehand.page.observe({
          instruction: args.instruction,
          returnAction: false,
        });
        return {
          content: [
            {
              type: "text",
              text: `Observations: ${JSON.stringify(observations)}`,
            },
          ],
          isError: false,
        };
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error);
        return {
          content: [
            {
              type: "text",
              text: `Failed to observe: ${errorMsg}`,
            },
            {
              type: "text",
              text: `Operation logs:\n${operationLogs.join("\n")}`,
            },
          ],
          isError: true,
        };
      }

    case "screenshot":
      try {

        const screenshotBuffer = await stagehand.page.screenshot({
          fullPage: false
        });

        // Convert buffer to base64 string and store in memory
        const screenshotBase64 = screenshotBuffer.toString('base64');
        const name = `screenshot-${new Date().toISOString().replace(/:/g, '-')}`;
        screenshots.set(name, screenshotBase64);

        //notify the client that the resources changed
        if (serverInstance) {
          serverInstance.notification({
            method: "notifications/resources/list_changed",
          });
        }

        return {
          content: [
            {
              type: "text",
              text: `Screenshot taken with name: ${name}`,
            },
            {
              type: "image",
              data: screenshotBase64,
              mimeType: "image/png",
            },
          ],
          isError: false,
        };
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error);
        return {
          content: [
            {
              type: "text",
              text: `Failed to take screenshot: ${errorMsg}`,
            },
            {
              type: "text",
              text: `Operation logs:\n${operationLogs.join("\n")}`,
            },
          ],
          isError: true,
        };
      }

    default:
      return {
        content: [
          {
            type: "text",
            text: `Unknown tool: ${name}`,
          },
          {
            type: "text",
            text: `Operation logs:\n${operationLogs.join("\n")}`,
          },
        ],
        isError: true,
      };
  }
}

// Create the server
const server = new Server(
  {
    name: "stagehand",
    version: "0.1.0",
  },
  {
    capabilities: {
      resources: {},
      tools: {},
      logging: {},
    },
  }
);

// Store server instance for logging
serverInstance = server;

// Setup request handlers
server.setRequestHandler(ListToolsRequestSchema, async (request) => {
  try {
    logRequest('ListTools', request.params);
    const response = { tools: TOOLS };
    const sanitizedResponse = sanitizeMessage(response);
    logResponse('ListTools', JSON.parse(sanitizedResponse));
    return JSON.parse(sanitizedResponse);
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    return {
      error: {
        code: -32603,
        message: `Internal error: ${errorMsg}`,
      },
    };
  }
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  try {
    logRequest('CallTool', request.params);
    operationLogs.length = 0; // Clear logs for new operation

    if (!request.params?.name || !TOOLS.find(t => t.name === request.params.name)) {
      throw new Error(`Invalid tool name: ${request.params?.name}`);
    }

    const result = await handleToolCall(
      request.params.name,
      request.params.arguments ?? {}
    );

    const sanitizedResult = sanitizeMessage(result);
    logResponse('CallTool', JSON.parse(sanitizedResult));
    return JSON.parse(sanitizedResult);
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    return {
      error: {
        code: -32603,
        message: `Internal error: ${errorMsg}`,
      },
    };
  }
});


server.setRequestHandler(ListResourcesRequestSchema, async (request) => {
  try {
    logRequest('ListResources', request.params);
    const response = {
      resources: [
        ...Array.from(screenshots.keys()).map((name) => ({
          uri: `screenshot://${name}`,
          mimeType: "image/png",
          name: `Screenshot: ${name}`,
        })),
      ]
    };
    const sanitizedResponse = sanitizeMessage(response);
    logResponse('ListResources', JSON.parse(sanitizedResponse));
    return JSON.parse(sanitizedResponse);
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    return {
      error: {
        code: -32603,
        message: `Internal error: ${errorMsg}`,
      },
    };
  }
});

server.setRequestHandler(ListResourceTemplatesRequestSchema, async (request) => {
  try {
    logRequest('ListResourceTemplates', request.params);
    // Return an empty list since we don't have any resource templates defined
    const response = { resourceTemplates: [] };
    const sanitizedResponse = sanitizeMessage(response);
    logResponse('ListResourceTemplates', JSON.parse(sanitizedResponse));
    return JSON.parse(sanitizedResponse);
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    return {
      error: {
        code: -32603,
        message: `Internal error: ${errorMsg}`,
      },
    };
  }
});

server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
  const uri = request.params.uri.toString();

  if (uri.startsWith("screenshot://")) {
    const name = uri.split("://")[1];
    const screenshot = screenshots.get(name);
    if (screenshot) {
      return {
        contents: [
          {
            uri,
            mimeType: "image/png",
            blob: screenshot,
          },
        ],
      };
    }
  }

  throw new Error(`Resource not found: ${uri}`);
});

// Run the server
async function runServer() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  server.sendLoggingMessage({
    level: "info",
    data: "Stagehand MCP server is ready to accept requests",
  });
}

runServer().catch((error) => {
  const errorMsg = error instanceof Error ? error.message : String(error);
  console.error(errorMsg);
});
