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

    app.post('/navigate', async (req: Request, res: Response) => {
      try {
        const { url } = req.body;
        await page.goto(url);
        res.json({
          message: `Navigated to: ${url}`,
        });
      } catch (err) {
        res.status(500).json({
          error: err instanceof Error ? err.message : 'Failed to navigate'
        });
      }
    });

    app.post('/act', async (req: Request, res: Response) => {
      try {
        const { action, variables } = req.body;
        await page.act({
          action,
          variables,
          slowDomBasedAct: false,
        });
        res.json({ message: `Action performed: ${action}` });
      } catch (err) {
        res.status(500).json({
          error: err instanceof Error ? err.message : 'Failed to perform action'
        });
      }
    });

    app.get('/extract', async (req: Request, res: Response) => {
      try {
        const bodyText = await page.evaluate(() => document.body.innerText);
        const content = bodyText
          .split('\n')
          .map(line => line.trim())
          .filter(line => {
            if (!line) return false;
            if (
              (line.includes('{') && line.includes('}')) ||
              line.includes('@keyframes') ||
              line.match(/^\.[a-zA-Z0-9_-]+\s*{/) ||
              line.match(/^[a-zA-Z-]+:[a-zA-Z0-9%\s\(\)\.,-]+;$/)
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

        res.json({ content: content.join('\n') });
      } catch (err) {
        res.status(500).json({
          error: err instanceof Error ? err.message : 'Failed to extract content'
        });
      }
    });

    app.post('/observe', async (req: Request, res: Response) => {
      try {
        const { instruction } = req.body;
        const observations = await page.observe({
          instruction,
          returnAction: false,
        });
        res.json({ observations });
      } catch (err) {
        res.status(500).json({
          error: err instanceof Error ? err.message : 'Failed to observe'
        });
      }
    });

    app.get('/screenshot', async (req: Request, res: Response) => {
      try {
        const screenshotBuffer = await page.screenshot({
          fullPage: false
        });
        const screenshotBase64 = screenshotBuffer.toString('base64');
        const name = `screenshot-${new Date().toISOString().replace(/:/g, '-')}`;

        res.json({
          name,
          screenshot: screenshotBase64,
          message: `Screenshot taken with name: ${name}`
        });
      } catch (err) {
        res.status(500).json({
          error: err instanceof Error ? err.message : 'Failed to take screenshot'
        });
      }
    });

  } catch (err) {
    console.error('Stagehand initialization failed', err);
    process.exit(1);
  }
}

main();
