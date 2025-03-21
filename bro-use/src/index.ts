import express, { Request, Response } from 'express';
import dotenv from 'dotenv';
import { BrowserContext, Page, Stagehand } from '@browserbasehq/stagehand';
import StagehandConfig from './stagehand.config';
import { z } from 'zod';
import { clearOverlays, drawObserveOverlay } from './utils';
import { WebSocketServer } from 'ws';


export type BaseMessage = {
  type: "human" | "ai"  | "tool",
  content: string,
  conversation_id: string,
  tool_calls?: {
      name: string,
      args: Record<string, unknown>,
  }[],
}
dotenv.config();

const app = express();
const PORT = process.env.PORT || 3333;

app.use(express.json());

const stagehand = new Stagehand({
  ...StagehandConfig,
});

async function main() {
  try {
    await stagehand.init();
    const page = stagehand.page;
    const context = stagehand.context;
    await page.goto("https://bnowako.com");

    const server = app.listen(PORT, () => {
      console.log(`Server running on http://localhost:${PORT}`);
    });

    // Create WebSocket server
    const wss = new WebSocketServer({ server });

    wss.on('connection', (ws) => {
      console.log('New WebSocket connection');

      // Send initial message
      ws.send(JSON.stringify({ hello: "world" }));

      ws.on('message', (message) => {
        console.log('received: %s', message);
        const parsed = JSON.parse(message.toString()) as BaseMessage;

        // Echo back the message
        ws.send(JSON.stringify({
          type: "human",
          content: parsed.content,
          conversation_id: "123",
        } as BaseMessage));

        ws.send(JSON.stringify({
          type: "ai",
          content: "content",
          conversation_id: "123",
        } as BaseMessage));
      });

      ws.on('close', () => {
        console.log('Client disconnected');
      });
    });

    app.post('/', async (req: Request, res: Response) => {
      console.log(req.body);
      const { action } = req.body;

      await clearOverlays(page);
      const result = await page.act({action: action});
      res.send(JSON.stringify(result));
    });

    app.get('/describe', async (req: Request, res: Response) => {
      // return page.screenshot as a base64 string
      const observation = await page.observe("Describe this page to a blind person. Explicitly general things that could be done on this page. Buttons and links.");
      await drawObserveOverlay(page, observation); // Highlight the search box
      console.log("observation", observation);

      const extraction = await page.extract({
        instruction: "Describe this page to a blind person. Explicitly general things that could be done on this page.",
        schema: z.object({
          description: z.string(),
        }),
      });

      res.send(JSON.stringify(extraction));
    });

  } catch (err) {
    console.error('Stagehand initialization failed', err);
    process.exit(1);
  }
}

main();
